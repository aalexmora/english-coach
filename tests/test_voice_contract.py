"""Voice recovery contracts against the existing public Saver environment."""
import asyncio
import hashlib
import json
import pytest
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from saver.server import create_app
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.methodologist import Worker, TestProvider
from english_coach.versions import VersionConflict, version_alias
from test_coach import env, attempt, goal
from test_speaking import begin, update


def started(c):
    s = c.start('start')
    sid = s['session']['id']
    c.transition('begin', sid, s['coach_version'], 'begin_item', 'step-clarify')
    return sid


def test_runtime_names_original_and_coach_versions(env):
    _, m, c = env
    sid = started(c)
    versions = c.context('runtime')['lesson_runtime']['versions']
    assert versions['session_version'] == 1
    assert versions['coach_version'] == 2
    assert 'session' not in versions
    assert c.get_session(sid)['session_version'] == 1
    assert c.get_session(sid)['coach_version'] == 2


def test_conflict_retry_same_key_commits_once_and_keeps_attribution(env):
    _, m, c = env
    sid = started(c)
    a = attempt('voice-answer')
    with pytest.raises(VersionConflict) as error:
        c.save('voice-save', sid, 2, [a], review=True, expected_coach_version=2)
    conflict = error.value.payload
    assert conflict['object'] == 'session'
    assert conflict['expected_version'] == 2 and conflict['current_version'] == 1
    assert conflict['retry'] == dict(expected_session_version=1)
    assert conflict['saved'] is False
    assert c.legacy.observations() == [] and c.documents('coach-job-') == []
    result = c.save('voice-save', sid, 1, [a], review=True, expected_coach_version=2)
    assert c.save('voice-save', sid, 1, [a], review=True, expected_coach_version=2) == result
    assert (result['session_version'], result['coach_version']) == (2, 3)
    assert result['next_action']['item_id'] == 'step-clarify'
    assert result['review_status'] == 'queued' and not result['review_applied']
    assert len(c.legacy.observations()) == len(c.documents('coach-job-')) == 1
    assert m.get('coach-session-'+sid)['value']['usages'][0]['attempt_ids'] == result['attempt_ids']
    # The same successful command remains a stable receipt after later changes.
    c.transition('later', sid, 3, 'begin_item', 'step-negotiate')
    assert c.save('voice-save', sid, 1, [a], review=True, expected_coach_version=2) == result


def test_omitted_session_version_resolves_inside_transaction(env):
    _, m, c = env
    sid = started(c)
    a = attempt()
    result = c.save('automatic-token', sid, None, [a], expected_coach_version=2,
                    item_id='step-clarify')
    assert result['session_version'] == 2 and result['coach_version'] == 3
    assert c.save('automatic-token', sid, None, [a], expected_coach_version=2, item_id='step-clarify') == result
    with pytest.raises(VersionConflict) as error:
        c.save('stale-coach', sid, None, [attempt('second')], expected_coach_version=2)
    assert error.value.payload['object'] == 'coach'
    assert len(c.legacy.observations()) == 1


def test_lightweight_state_never_loads_ledger_or_mutates(env, monkeypatch):
    _, m, c = env
    sid = started(c)
    before = m.history('coach-session-'+sid)
    def forbidden(*args, **kwargs):
        pytest.fail('Lightweight cursor loaded full legacy history')
    for name in ('get', 'progress', 'observations'):
        monkeypatch.setattr(c.legacy, name, forbidden)
    state = c.session_state(sid)
    assert state['session_version'] == 1 and state['coach_version'] == 2
    assert state['next_item']['id'] == 'step-clarify'
    assert not {'attempts','plan','settings','due_items'} & state.keys()
    assert len(json.dumps(state).encode()) < 2500
    assert m.history('coach-session-'+sid) == before


def test_save_completion_moves_cursor_atomically_without_ending(env):
    _, m, c = env
    sid = started(c)
    result = c.save('done-and-save', sid, 1, [attempt()], expected_coach_version=2,
                    item_id='step-clarify', completed_item_ids=['step-clarify'])
    assert result['next_action']['kind'] == 'begin_item'
    assert result['next_item']['id'] == 'step-negotiate'
    assert result['phase'] == result['session_status'] == 'active'
    assert m.get('coach-session-'+sid)['value']['current_item_id'] is None
    assert c.context('runtime')['lesson_runtime']['next_action']['item_id'] == 'step-negotiate'


@pytest.mark.parametrize('completion,coach_version,item_id', [
    (['missing'], 2, 'step-clarify'),
    (['step-clarify'], None, 'step-clarify'),
    (['step-clarify'], 2, 'step-negotiate'),
    (['step-clarify','step-clarify'], 2, 'step-clarify'),
])
def test_bad_completion_rolls_back_observations_and_job(env, completion, coach_version, item_id):
    _, m, c = env
    sid = started(c)
    before = m.get('coach-session-'+sid)
    with pytest.raises(ValueError):
        c.save('invalid', sid, 1, [attempt()], review=True, expected_coach_version=coach_version,
               item_id=item_id, completed_item_ids=completion)
    assert c.legacy.observations() == [] and c.documents('coach-job-') == []
    assert c.legacy.metadata(sid)['version'] == 1
    assert m.get('coach-session-'+sid) == before


def test_completion_cannot_skip_repair(env):
    _, m, c = env
    sid, practice = begin(c)
    update(c, sid, practice, 'wrong', a=attempt('wrong', outcome='incorrect'))
    before = c.version_state(sid)
    with pytest.raises(ValueError, match='repair/reproduction'):
        c.save('skip', sid, before['session_version'], [attempt('new')], review=True,
               expected_coach_version=before['coach_version'], completed_item_ids=['step-clarify'])
    assert c.version_state(sid) == before
    assert len(c.legacy.observations()) == 1 and c.documents('coach-job-') == []


@pytest.mark.parametrize('terminal', ['applied', 'failed', 'stale'])
def test_compact_review_job_lifecycle_and_applied_plan(env, terminal):
    _, m, c = env
    sid = started(c)
    receipt = c.save('review', sid, 1, [attempt()], review=True)
    job_id = receipt['review_job']
    profile = c.profile()
    assert c.review(job_id)['status'] == 'queued'
    worker = Worker(c, TestProvider(), max_attempts=1)
    claimed = worker.claim()
    assert c.review(job_id)['status'] == 'running'
    if terminal == 'stale':
        c.save('new-checkpoint', sid, 2, [])
    raw = asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    worker.finish(claimed, raw, error='provider unavailable' if terminal == 'failed' else None)
    before = m.history(job_id)
    small = c.review(job_id)
    assert small['status'] == terminal and small['terminal']
    assert small['applied'] is (terminal == 'applied')
    assert small['plan_is_current'] is (terminal == 'applied')
    assert 'snapshot' not in small['value']
    assert 'observations' not in json.dumps(small)
    full = c.review(job_id, 'full')
    assert 'snapshot' in full['value'] and m.history(job_id) == before
    if terminal == 'applied':
        assert small['applied_profile_version'] == profile['version'] + 1
        c.settings('later-settings', c.profile()['version'], {'preferred_mechanic':'contrast'}, True)
        assert c.review(job_id)['applied'] and not c.review(job_id)['plan_is_current']
    else:
        assert c.profile() == profile


def test_small_reads_deny_foreign_session_and_job(env):
    store, m, c = env
    sid = started(c)
    saved = c.save('review', sid, 1, [], review=True)
    store.register_user('other')
    other = Coach(MemoryAPI(store,'other','english',['english']), LegacyEnglishAPI(store,'other',['english']))
    with pytest.raises(ValueError): other.session_state(sid)
    with pytest.raises(ValueError): other.review(saved['review_job'])
    with pytest.raises(ValueError): other.legacy.metadata(sid)


def test_version_alias_rejects_ambiguity():
    assert version_alias(1,None,'expected_session_version') == 1
    assert version_alias(None,2,'expected_coach_version') == 2
    with pytest.raises(ValueError, match='disagree'): version_alias(1,2,'expected_session_version')


def test_voice_recovery_through_authenticated_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv('SAVER_ENGLISH_COACH','1')
    monkeypatch.setenv('COACH_PROVIDER','disabled')
    base='http://localhost:8000'
    app=create_app(tmp_path/'data',tmp_path/'export',base,hashlib.sha256(b'synthetic-code').hexdigest())
    service=app
    while hasattr(service,'app'): service=service.app
    token=service.state.provider.issue('test',['memory:english'],base+'/mcp','owner').access_token
    async def run():
        async with service.router.lifespan_context(service):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),headers={'Authorization':'Bearer '+token}) as http:
                async with streamable_http_client(base+'/mcp',http_client=http) as (read,write,_):
                    async with ClientSession(read,write) as client:
                        await client.initialize()
                        async def call(name,args):
                            result=await client.call_tool(name,args)
                            assert not result.isError, result
                            return result.structuredContent
                        catalog={t.name:t.inputSchema for t in (await client.list_tools()).tools}
                        for name in ('save_english_progress','save_checkpoint','finalize_english_lesson','request_english_review'):
                            assert 'expected_session_version' in catalog[name]['properties']
                        assert 'expected_coach_version' in catalog['update_english_session']['properties']
                        await call('configure_english',dict(idempotency_key='setup',goal=goal(),learner_confirmed=True))
                        s=await call('start_coach_session',dict(idempotency_key='start'))
                        sid=s['session']['id']
                        await call('update_english_session',dict(idempotency_key='begin',session_id=sid,expected_coach_version=1,
                                   action='begin_item',item_id='step-clarify'))
                        runtime=await call('get_english_context',{})
                        assert runtime['lesson_runtime']['versions']['session_version'] == 1
                        assert runtime['lesson_runtime']['versions']['coach_version'] == 2
                        args=dict(idempotency_key='save',session_id=sid,expected_version=2,expected_coach_version=2,
                                  attempts=[attempt('mcp-answer')],item_id='step-clarify')
                        failed=await client.call_tool('save_english_progress',args)
                        assert failed.isError
                        text='\n'.join(x.text for x in failed.content if x.type=='text')
                        conflict=json.loads(text.split('Version conflict: ',1)[1])
                        assert conflict['object']=='session' and conflict['current_version']==1
                        args.pop('expected_version');args.update(conflict['retry'])
                        saved=await call('save_english_progress',args)
                        assert await call('save_english_progress',args) == saved
                        assert saved['session_version']==2 and saved['coach_version']==3
                        contradictory=await client.call_tool('save_english_progress',dict(args,idempotency_key='bad-alias',expected_version=9))
                        assert contradictory.isError
                        state=await call('get_english_session_state',dict(session_id=sid))
                        assert state['next_item']['id']=='step-clarify'
                        review=await call('get_english_review',dict(job_id=saved['review_job']))
                        assert 'snapshot' not in review['value'] and not review['applied']
                        checkpoint=await call('save_checkpoint',dict(idempotency_key='completion',session_id=sid,attempts=[],
                                        expected_coach_version=3,completed_item_ids=['step-clarify']))
                        assert checkpoint['result']['session_version']==3
                        assert checkpoint['result']['next_item']['id']=='step-negotiate'
                        await call('request_english_review',dict(idempotency_key='fresh-review',session_id=sid,
                                   expected_session_version=3,expected_coach_version=4))
                        finished=await call('finalize_english_lesson',dict(idempotency_key='finish',session_id=sid,
                                    expected_session_version=3,expected_coach_version=4,explicit_end=True))
                        assert finished['finished'] and finished['next_action']['kind']=='await_start'
                        assert finished['session_version']==5
    asyncio.run(run())
