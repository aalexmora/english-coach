"""Official Sign in with ChatGPT credentials; separate from learner storage."""
import argparse
import asyncio
import base64
import fcntl
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import stat
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from uuid import UUID, uuid4

import httpx
import jwt

ISSUER = 'https://auth.openai.com'
RESOURCE = 'https://api.openai.com/v1'
AUTHORIZE = ISSUER + '/api/accounts/authorize'
TOKEN = ISSUER + '/api/accounts/oauth/token'
JWKS = ISSUER + '/.well-known/jwks.json'
PLAN_SCOPES = {'chatgpt.tokens.use.direct', 'resource.invoke'}
SCOPES = 'openid profile email offline_access resource.invoke chatgpt.tokens.use.direct'


class ChatGPTAuthError(ValueError):
    category = 'auth'


def private_write(path, value):
    """Replace a credential record with one owner-only, durable file."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.chatgpt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def private_read(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
                raise ChatGPTAuthError('ChatGPT credentials require owner-only permissions')
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, ChatGPTAuthError):
            raise
        raise ChatGPTAuthError('ChatGPT credentials are missing or invalid') from None


def granted_scopes(value):
    if isinstance(value, str):
        return set(value.split())
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    raise ChatGPTAuthError('ChatGPT permissions are invalid')


def client_id_valid(value):
    return (isinstance(value, str) and 1 < len(value) <= 200 and
            value != 'dynamic_agent_client' and
            all(character.isalnum() or character in '_-' for character in value))


def verify_identity(client, token, client_id, nonce=None):
    """Verify the issued ID token; decoded access-token claims are not identity."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256':
            raise ValueError()
        response = client.get(JWKS)
        response.raise_for_status()
        keys = response.json()['keys']
        key = next(key for key in keys if key.get('kid') == header.get('kid'))
        claims = jwt.decode(token, jwt.PyJWK.from_dict(key).key,
                            algorithms=['RS256'], audience=client_id, issuer=ISSUER,
                            options={'require': ['iss', 'aud', 'exp', 'iat', 'sub']})
        if nonce is not None and not secrets.compare_digest(claims.get('nonce', ''), nonce):
            raise ValueError()
        if not isinstance(claims['sub'], str) or not claims['sub']:
            raise ValueError()
        return claims
    except (jwt.PyJWTError, ValueError, KeyError, TypeError, StopIteration, httpx.HTTPError):
        raise ChatGPTAuthError('ChatGPT account verification failed') from None


def token_record(client, response, client_id, host_id, nonce=None, previous=None):
    if not client_id_valid(client_id):
        raise ChatGPTAuthError('ChatGPT registration is incomplete')
    if not isinstance(response, dict):
        raise ChatGPTAuthError('ChatGPT token response is invalid')
    scopes = granted_scopes(response.get('scope', previous.get('scopes') if previous else None))
    plan_authorized = PLAN_SCOPES <= scopes
    access = response.get('access_token')
    refresh = response.get('refresh_token', previous.get('refresh_token') if previous else None)
    if plan_authorized and (response.get('token_type', '').lower() != 'bearer' or
            not isinstance(access, str) or not access or not isinstance(refresh, str) or not refresh):
        raise ChatGPTAuthError('ChatGPT token response is incomplete')
    try:
        expires_in = float(response.get('expires_in', 3600) if not plan_authorized else response['expires_in'])
        if not 0 < expires_in <= 31536000:
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise ChatGPTAuthError('ChatGPT token expiry is invalid') from None
    identity = dict(previous or {})
    if response.get('id_token'):
        claims = verify_identity(client, response['id_token'], client_id, nonce)
        if previous and claims['sub'] != previous['subject']:
            raise ChatGPTAuthError('ChatGPT account changed; credentials were not replaced')
        identity.update(subject=claims['sub'], email=claims.get('email'), id_token=response['id_token'])
    elif not previous or nonce is not None:
        raise ChatGPTAuthError('ChatGPT account verification is missing')
    timestamp = time.time()
    identity.update(issuer=ISSUER, client_id=client_id, ext_agent_host_id=host_id,
                    access_token=access, refresh_token=refresh, token_type='Bearer',
                    scopes=sorted(scopes), expires_in=expires_in, saved_at=timestamp,
                    expires_at=timestamp + expires_in, plan_authorized=plan_authorized)
    return identity


class CredentialStore:
    """Serialize rotating refreshes across the worker and material requests."""
    def __init__(self, path, timeout=30):
        self.path, self.timeout = Path(path), min(timeout, 30)

    def identity(self):
        record = private_read(self.path)
        if (record.get('issuer') != ISSUER or not client_id_valid(record.get('client_id')) or
                not isinstance(record.get('subject'), str) or not record['subject'] or
                not isinstance(record.get('ext_agent_host_id'), str)):
            raise ChatGPTAuthError('ChatGPT account credentials are invalid; sign in again')
        return record

    def read(self):
        record = self.identity()
        if (not PLAN_SCOPES <= granted_scopes(record.get('scopes')) or
                not isinstance(record.get('access_token'), str) or not record['access_token'] or
                not isinstance(record.get('refresh_token'), str) or not record['refresh_token'] or
                not isinstance(record.get('expires_at'), (int, float))):
            raise ChatGPTAuthError('ChatGPT plan credentials are invalid; sign in again')
        return record

    def access_token(self):
        record = self.read()
        if record['expires_at'] > time.time() + 120:
            return record['access_token']
        fd = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
            started = time.monotonic()
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - started > self.timeout:
                        raise ChatGPTAuthError('ChatGPT token renewal is busy; retry later')
                    time.sleep(0.05)
            record = self.read()
            if record['expires_at'] > time.time() + 120:
                return record['access_token']
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=True) as client:
                    response = client.post(TOKEN, data=dict(grant_type='refresh_token',
                        client_id=record['client_id'], refresh_token=record['refresh_token'],
                        resource=RESOURCE))
                    response.raise_for_status()
                    replacement = token_record(client, response.json(), record['client_id'],
                                               record['ext_agent_host_id'], previous=record)
                    if not replacement['plan_authorized']:
                        raise ChatGPTAuthError('ChatGPT plan usage is no longer authorized')
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                raise ChatGPTAuthError('ChatGPT token renewal failed; sign in again') from None
            private_write(self.path, replacement)
            return replacement['access_token']
        finally:
            os.close(fd)

    async def token(self):
        return await asyncio.to_thread(self.access_token)


def host_identity(path, supplied=None):
    path = Path(path).with_name('host-id.json')
    if path.exists():
        existing = private_read(path)['ext_agent_host_id']
        if supplied and supplied != existing:
            raise ChatGPTAuthError('Existing ChatGPT host identity differs')
        return existing
    value = supplied or 'urn:uuid:' + str(uuid4())
    try:
        UUID(value.removeprefix('urn:uuid:'))
        if not value.startswith('urn:uuid:'):
            raise ValueError()
    except (ValueError, AttributeError):
        raise ChatGPTAuthError('ChatGPT host identity must be an opaque UUID URI') from None
    private_write(path, dict(ext_agent_host_id=value))
    return value


def login(path, port=14551, host_id=None, deadline=900):
    """Loopback PKCE flow; the user completes OpenAI's own consent screen."""
    host_id = host_identity(path, host_id)
    previous = CredentialStore(path).identity() if Path(path).exists() else None
    state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    redirect = f'http://127.0.0.1:{port}/auth/callback'
    client_id = previous['client_id'] if previous else 'dynamic_agent_client'
    params = dict(client_id=client_id, ext_agent_host_id=host_id,
                  response_type='code', redirect_uri=redirect, scope=SCOPES,
                  resource=RESOURCE, state=state, nonce=nonce,
                  code_challenge_method='S256', code_challenge=challenge)
    if not previous:
        params['agent_name_hint'] = 'English Coach'
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # The callback URL contains a one-time authorization code.

        def do_GET(self):
            query = parse_qs(urlsplit(self.path).query)
            valid = (urlsplit(self.path).path == '/auth/callback' and
                     len(query.get('state', [])) == 1 and
                     secrets.compare_digest(query['state'][0], state))
            if valid:
                for name in ('code', 'client_id', 'error'):
                    values = query.get(name, [])
                    if len(values) == 1:
                        received[name] = values[0]
                received['returned'] = True
            self.send_response(200 if valid else 400)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(('Return to English Coach to see the sign-in result.' if valid
                              else 'Invalid sign-in callback.').encode())

    with HTTPServer(('127.0.0.1', port), Callback) as server:
        server.timeout = 1
        print(json.dumps(dict(event='login_ready', authorization_url=AUTHORIZE+'?'+urlencode(params))), flush=True)
        until = time.monotonic() + deadline
        while not received.get('returned') and time.monotonic() < until:
            server.handle_request()
    if not received.get('returned') or received.get('error') or not received.get('code'):
        raise ChatGPTAuthError('ChatGPT sign-in was not completed')
    issued = received.get('client_id', client_id if previous else None)
    if not client_id_valid(issued) or (previous and issued != client_id):
        raise ChatGPTAuthError('ChatGPT registration differs; credentials were not replaced')
    with httpx.Client(timeout=30, follow_redirects=False, trust_env=True) as client:
        response = client.post(TOKEN, data=dict(grant_type='authorization_code',
            client_id=issued, code=received['code'], code_verifier=verifier,
            redirect_uri=redirect, resource=RESOURCE))
        response.raise_for_status()
        record = token_record(client, response.json(), issued, host_id, nonce, previous)
    private_write(path, record)
    print(json.dumps(dict(event='login_complete', identity_verified=True,
                          chatgpt_plan_authorized=record['plan_authorized'], credentials_saved=True)), flush=True)


def main():
    parser = argparse.ArgumentParser(description='Continue with ChatGPT for English Coach')
    parser.add_argument('--file', required=True, help='Private credential file outside source control')
    parser.add_argument('--port', type=int, default=14551)
    parser.add_argument('--host-id', help='Existing opaque host ID for the self-hosted runtime')
    args = parser.parse_args()
    try:
        login(args.file, args.port, args.host_id)
    except (ChatGPTAuthError, httpx.HTTPError, OSError, ValueError):
        print(json.dumps(dict(event='login_failed', error='ChatGPT sign-in was not completed or verified')), flush=True)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
