import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import base64
import io
import json
import time
from urllib.parse import parse_qs, urlencode, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa
import httpx
import jwt
import pytest

from english_coach import chatgpt_auth as auth
from english_coach.methodologist import ChatGPTProvider, ProviderResultError, from_env


def credentials(path, **patch):
    value = dict(issuer=auth.ISSUER, subject='synthetic-subject', client_id='oaiapp_synthetic',
                 ext_agent_host_id='urn:uuid:bb5b01ad-7617-422f-b555-ac390d46da1e',
                 access_token='synthetic-access', refresh_token='synthetic-refresh',
                 scopes=sorted(auth.PLAN_SCOPES), expires_at=time.time()+3600)
    value.update(patch)
    auth.private_write(path, value)
    return value


def event(kind, **fields):
    return 'data: '+json.dumps(dict(type=kind, **fields))+'\n\n'


def completed(value):
    return event('response.completed', response=dict(status='completed', error=None,
        output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(value))])]))


@pytest.mark.parametrize('with_content_type', [True, False])
def test_chatgpt_review_and_material_use_public_contract(monkeypatch, tmp_path, with_content_type):
    path=tmp_path/'auth.json'
    credentials(path)
    original=httpx.AsyncClient
    requests=[]
    def respond(request):
        data=json.loads(request.content)
        requests.append(data)
        assert str(request.url)=='https://api.openai.com/v1/responses'
        assert request.headers['Authorization']=='Bearer synthetic-access'
        assert data['store'] is False and data['stream'] is True
        assert data['input'][0]['role']=='user'
        assert 'JSON' in data['input'][0]['content']
        assert data['text']['format']=={'type':'json_object'}
        assert 'Required JSON schema' in data['instructions']
        assert not {'messages','max_tokens','max_output_tokens','background','previous_response_id','metadata'} & set(data)
        value={'findings':[],'changes':[]} if len(requests)==1 else {'materials':[]}
        content=event('response.output_text.delta', delta='untrusted partial')+completed(value)
        headers={'content-type':'text/event-stream'} if with_content_type else {}
        return httpx.Response(200, headers=headers, content=content)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    provider=ChatGPTProvider('synthetic-model',path,2)
    assert asyncio.run(provider.review({}))=={'findings':[],'changes':[]}
    assert asyncio.run(provider.analyze_material({'text':'Synthetic only'}))=={'materials':[]}
    monkeypatch.setenv('COACH_PROVIDER','chatgpt')
    monkeypatch.setenv('COACH_MODEL','synthetic-model')
    monkeypatch.setenv('COACH_AUTH_FILE',str(path))
    monkeypatch.delenv('COACH_API_KEY',raising=False)
    assert isinstance(from_env()[0],ChatGPTProvider)


@pytest.mark.parametrize('stream,category',[
    (event('response.output_text.delta', delta='{"findings":[],"changes":[]}'),'truncated'),
    (event('response.output_text.delta', delta='{}')+event('response.failed',response={'error':{'message':'sensitive model text'}}),'transport'),
    (event('response.incomplete',response={}), 'truncated'),
    (event('response.refusal.delta',delta='sensitive refusal'), 'refusal'),
    ('data: invalid-json\n\n','schema'),
    (event('response.completed',response={'status':'in_progress','output':[]}), 'truncated'),
    (completed([]),'invalid_json'),
])
def test_chatgpt_partial_or_failed_stream_never_becomes_review(monkeypatch,tmp_path,stream,category):
    path=tmp_path/'auth.json'; credentials(path)
    original=httpx.AsyncClient
    def respond(_):
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=stream)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    with pytest.raises(ProviderResultError) as caught:
        asyncio.run(ChatGPTProvider('synthetic-model',path,2).review({}))
    assert caught.value.category==category
    assert 'sensitive' not in str(caught.value) and 'synthetic-access' not in str(caught.value)


def test_chatgpt_review_retains_existing_schema_repair(monkeypatch,tmp_path):
    path=tmp_path/'auth.json'; credentials(path)
    original=httpx.AsyncClient
    requests=[]
    def respond(request):
        requests.append(json.loads(request.content))
        value={'findings':[],'changes':[]}
        if len(requests)==1:value['unexpected']='bad schema'
        return httpx.Response(200,headers={'content-type':'text/event-stream'},content=completed(value))
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    assert asyncio.run(ChatGPTProvider('synthetic-model',path,2).review({}))=={'findings':[],'changes':[]}
    assert len(requests)==2
    assert 'previous JSON failed' in requests[1]['instructions']


def test_chatgpt_completed_stream_with_lean_final_event(monkeypatch,tmp_path):
    path=tmp_path/'auth.json'; credentials(path)
    original=httpx.AsyncClient
    value='{"findings":[],"changes":[]}'
    content=(event('response.output_text.delta',delta=value[:12],output_index=0,content_index=0)+
             event('response.output_text.delta',delta=value[12:],output_index=0,content_index=0)+
             event('response.output_text.done',text=value,output_index=0,content_index=0)+
             event('response.completed',response=dict(status='completed',output=[])))
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(
        lambda _:httpx.Response(200,content=content)),**kw))
    assert asyncio.run(ChatGPTProvider('synthetic-model',path,2).review({}))=={'findings':[],'changes':[]}


def test_identity_only_credentials_never_send_inference(tmp_path):
    path=tmp_path/'auth.json'; credentials(path,scopes=['openid','profile','offline_access'])
    with pytest.raises(auth.ChatGPTAuthError,match='plan credentials'):
        asyncio.run(ChatGPTProvider('synthetic-model',path,2).review({}))
    path.chmod(0o644)
    with pytest.raises(auth.ChatGPTAuthError,match='owner-only'):
        auth.CredentialStore(path).read()


def test_chatgpt_http_error_remains_inspectable_after_stream_closes(monkeypatch,tmp_path):
    path=tmp_path/'auth.json'; credentials(path)
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(
        lambda _:httpx.Response(400,json={'error':{'code':'invalid_request_error'}})),**kw))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        asyncio.run(ChatGPTProvider('synthetic-model',path,2).review({}))
    assert caught.value.response.json()['error']['code']=='invalid_request_error'


@pytest.fixture
def signed_identity():
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    public=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid='synthetic-key',alg='RS256',use='sig')
    def sign(**patch):
        now=int(time.time())
        claims=dict(iss=auth.ISSUER,aud='oaiapp_synthetic',sub='synthetic-subject',
                    exp=now+3600,iat=now,nonce='synthetic-nonce')
        claims.update(patch)
        return jwt.encode(claims,key,algorithm='RS256',headers={'kid':'synthetic-key'})
    return public,sign


@pytest.mark.parametrize('patch',[
    {'aud':'oaiapp_other'}, {'nonce':'wrong-nonce'}, {'iss':'https://untrusted.example'},
    {'exp':1},
])
def test_login_rejects_wrong_identity_signature_context(signed_identity,patch):
    public,sign=signed_identity
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'keys':[public]}))) as client:
        with pytest.raises(auth.ChatGPTAuthError,match='verification failed'):
            auth.verify_identity(client,sign(**patch),'oaiapp_synthetic','synthetic-nonce')


def test_login_verifies_identity_and_keeps_declined_plan_disabled(signed_identity,tmp_path):
    public,sign=signed_identity
    with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'keys':[public]}))) as client:
        response=dict(id_token=sign(),scope='openid profile email',expires_in=3600)
        record=auth.token_record(client,response,'oaiapp_synthetic',auth.host_identity(tmp_path/'auth.json'),'synthetic-nonce')
    assert record['plan_authorized'] is False
    auth.private_write(tmp_path/'auth.json',record)
    assert auth.CredentialStore(tmp_path/'auth.json').identity()['client_id']=='oaiapp_synthetic'
    with pytest.raises(auth.ChatGPTAuthError):auth.CredentialStore(tmp_path/'auth.json').read()


def test_rotating_refresh_is_serialized_and_atomic(monkeypatch,tmp_path):
    path=tmp_path/'auth.json'; original_record=credentials(path,expires_at=1)
    original=httpx.Client
    requests=[]
    def respond(request):
        data=parse_qs(request.content.decode())
        requests.append(data)
        assert str(request.url)==auth.TOKEN
        assert data['resource']==[auth.RESOURCE]
        assert data['refresh_token']==['synthetic-refresh']
        assert 'scope' not in data
        time.sleep(.05)
        return httpx.Response(200,json=dict(access_token='synthetic-renewed',refresh_token='synthetic-rotated',
                                           token_type='Bearer',expires_in=3600))
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    with ThreadPoolExecutor(max_workers=2) as workers:
        values=list(workers.map(lambda _:auth.CredentialStore(path,2).access_token(),range(2)))
    assert values==['synthetic-renewed']*2 and len(requests)==1
    record=auth.private_read(path)
    assert record['refresh_token']=='synthetic-rotated'
    assert record['subject']==original_record['subject']
    assert record['ext_agent_host_id']==original_record['ext_agent_host_id']
    assert path.stat().st_mode & 0o777==0o600


def test_failed_refresh_keeps_original_credentials_and_hides_token(monkeypatch,tmp_path):
    path=tmp_path/'auth.json'; record=credentials(path,expires_at=1)
    original=httpx.Client
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(
        lambda _:httpx.Response(400,json={'error':'invalid_grant','message':'synthetic-refresh'})),**kw))
    with pytest.raises(auth.ChatGPTAuthError) as caught:auth.CredentialStore(path,2).access_token()
    assert 'synthetic-refresh' not in str(caught.value)
    assert auth.private_read(path)==record


def test_loopback_login_uses_pkce_and_ignores_wrong_state(monkeypatch,tmp_path,signed_identity,capsys):
    public,sign=signed_identity
    params={}
    attempts=[]
    class Server:
        def __init__(self,address,handler):
            assert address==('127.0.0.1',14551)
            self.handler=handler
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def handle_request(self):
            if not params:
                ready=json.loads(capsys.readouterr().out)
                params.update(parse_qs(urlsplit(ready['authorization_url']).query))
            callback=dict(code='synthetic-code',client_id='oaiapp_synthetic',
                          state='wrong' if not attempts else params['state'][0])
            handler=object.__new__(self.handler)
            handler.path='/auth/callback?'+urlencode(callback)
            handler.wfile=io.BytesIO()
            handler.send_response=lambda status:attempts.append(status)
            handler.send_header=lambda *_:None
            handler.end_headers=lambda:None
            handler.do_GET()
    original=httpx.Client
    def respond(request):
        if request.method=='GET':return httpx.Response(200,json={'keys':[public]})
        body=parse_qs(request.content.decode())
        verifier=body['code_verifier'][0]
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        assert params['code_challenge']==[challenge]
        assert params['client_id']==['dynamic_agent_client']
        assert params['agent_name_hint']==['English Coach']
        assert body['client_id']==['oaiapp_synthetic']
        assert body['redirect_uri']==['http://127.0.0.1:14551/auth/callback']
        assert set(params['scope'][0].split()) >= auth.PLAN_SCOPES
        return httpx.Response(200,json=dict(token_type='Bearer',access_token='synthetic-access',
            refresh_token='synthetic-refresh',id_token=sign(nonce=params['nonce'][0]),
            scope=auth.SCOPES,expires_in=3600))
    monkeypatch.setattr(auth,'HTTPServer',Server)
    monkeypatch.setattr(httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    path=tmp_path/'auth.json'
    auth.login(path)
    assert attempts==[400,200]
    assert auth.CredentialStore(path).read()['client_id']=='oaiapp_synthetic'
    assert 'synthetic-access' not in capsys.readouterr().out
    host=auth.host_identity(path)
    assert auth.host_identity(path)==host
    with pytest.raises(auth.ChatGPTAuthError):auth.host_identity(path,'urn:uuid:'+str(__import__('uuid').uuid4()))
