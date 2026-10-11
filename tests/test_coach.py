import asyncio
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import sqlite3
import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.methodologist import Worker, TestProvider


def goal():
    return dict(outcome='Negotiate delivery and explain decisions at work', minutes=20,
                milestones=['Clarify constraints', 'Negotiate a tradeoff', 'Explain a decision independently'],
                skills=[dict(id='clarify', outcome='Ask a clarification question', pattern_ids=['past_simple_questions']),
                        dict(id='negotiate', outcome='Offer an alternative and justify it', pattern_ids=[])])

@pytest.fixture
def env(tmp_path):
    store=Store(tmp_path/'memory.sqlite', tmp_path/'export')
    memory=MemoryAPI(store,'owner','english',['english'])
    coach=Coach(memory, LegacyEnglishAPI(store,'owner',['english']))
    coach.configure('configure',goal(),confirmed=True)
    return store, memory, coach


def attempt(key='a', assistance='independent', outcome='correct'):
    return dict(idempotency_key=key, pattern_id='past_simple_questions', occurred_at=datetime.now(timezone.utc).isoformat(),
                outcome=outcome, assistance=assistance, context='delivery negotiation', mode='free', observation='Supplied observed response')


def save_review(coach, attempts=None, feedback=None):
    session=coach.start('start')
    for a in attempts or []:
        a['occurred_at']=datetime.now(timezone.utc).isoformat()
    saved=coach.save('save',session['session']['id'],session['session']['version'],attempts or [],review=True,feedback=feedback)
    return session,saved


def run(worker):
    return asyncio.run(worker.run_once())


def test_context_resume_save_without_finish_and_atomic_retry(env):
    store,memory,c=env
    s=c.start('start'); sid=s['session']['id']; a=attempt()
    r=c.save('save',sid,1,[a],review=True)
    assert c.save('save',sid,1,[a],review=True)==r
    assert len(c.legacy.observations())==1
    assert len(c.documents('coach-job-'))==1
    assert c.get_session(sid)['session']['status']=='active'
    new_store=Store(store.path,store.export_root)
    again=Coach(MemoryAPI(new_store,'owner','english',['english']),LegacyEnglishAPI(new_store,'owner',['english']))
    assert again.context()['unfinished']==c.context()['unfinished']
    assert again.start('resume')['session']['id']==sid
    assert again.context()['profile']['value']['goal']==goal()
    assert again.context()['skills']['clarify']['independent_total']==1
    assert all(i['mechanic']=='roleplay' for i in c.context()['unfinished'])
    with pytest.raises(ValueError): c.save('save',sid,1,[],review=True)


def test_atomic_rollback_after_observation_if_discovery_bad(env):
    _,m,c=env
    s=c.start('start')['session']
    bad=dict(id='d',scope='personal',skill_id='missing',cue='cue',context='lesson',evidence_ids=[],reuse_trigger='next time',explicit_save=True)
    with pytest.raises(ValueError): c.save('bad',s['id'],1,[attempt()],review=True,discoveries=[bad])
    assert c.legacy.observations()==[]
    assert c.legacy.get(s['id'])['session']['version']==1
    assert c.documents('coach-job-')==[]
    assert c.required('coach-session-'+s['id'])['version']==1


def test_checkpoint_does_not_enqueue_and_observation_dedup(env):
    _,m,c=env
    s=c.start('s')['session']; a=attempt()
    c.save('cp',s['id'],1,[a])
    c.save('cp2',s['id'],2,[a])
    assert len(c.legacy.observations())==1
    assert c.documents('coach-job-')==[]


def test_branch_guard_explicit_finish_carry_and_scheduler(env):
    _,m,c=env
    s=c.start('s'); sid=s['session']['id']; first=s['coach']['value']['items'][0]['id']
    b=c.transition('b',sid,1,'branch',note='Useful detour, then return to the pending exercise')
    assert b['value']['branch']['return_to']==first
    with pytest.raises(ValueError): c.transition('bad',sid,2,'complete_item',first)
    r=c.transition('r',sid,2,'return')
    c.save('cp',sid,1,[attempt()])
    with pytest.raises(ValueError): c.transition('early',sid,4,'finish')
    done=c.transition('done',sid,4,'finish',explicit_end=True)
    assert done['value']['phase']=='finished'
    assert c.legacy.progress()['patterns'][next(i for i,p in enumerate(c.legacy.progress()['patterns']) if p['id']=='past_simple_questions')]['stage']==0
    newer=c.start('new')
    assert newer['session']['id']!=sid
    assert all(i['status']=='carried' for i in newer['coach']['value']['items'])
    assert len(newer['coach']['value']['items'])==2


def test_pause_resume_and_invalid_transition(env):
    _,m,c=env
    s=c.start('s')['session']
    c.transition('pause',s['id'],1,'pause',note='Wait here')
    with pytest.raises(ValueError): c.save('bad',s['id'],1,[],review=True)
    with pytest.raises(ValueError): c.transition('bad2',s['id'],2,'branch',note='x')
    r=c.transition('resume',s['id'],2,'resume')
    assert r['value']['phase']=='active'


def test_model_failure_progress_durable_and_retry_bound(env):
    _,m,c=env
    s,r=save_review(c,[attempt()])
    class Broken:
        async def review(self,snapshot): raise RuntimeError('SECRET must not reach logs')
    worker=Worker(c,Broken(),retry_seconds=0,max_attempts=2)
    assert run(worker)['value']['status']=='queued'
    failed=run(worker)['value']
    assert failed['status']=='failed' and failed['attempts']==2
    assert 'SECRET' not in failed['error']
    assert run(worker) is None
    assert len(c.legacy.observations())==1
    assert c.profile()['version']==1


def test_timeout(env):
    _,m,c=env
    save_review(c)
    class Slow:
        async def review(self,snapshot): await asyncio.sleep(60)
    job=run(Worker(c,Slow(),timeout=.01,max_attempts=1))
    assert job['value']['status']=='failed'
    assert 'Timeout' in job['value']['error']


def test_restart_lease_recovery_and_double_apply(env):
    store,m,c=env
    s,r=save_review(c,[attempt()])
    first=Worker(c,TestProvider(),max_attempts=3)
    claimed=first.claim()
    assert claimed['value']['status']=='running'
    assert first.claim() is None
    j=deepcopy(claimed['value']); j['lease_until']='2000-01-01T00:00:00+00:00'
    m.put(claimed['key'],j,claimed['version'])
    new_store=Store(store.path,store.export_root)
    resumed=Coach(MemoryAPI(new_store,'owner','english',['english']),LegacyEnglishAPI(new_store,'owner',['english']))
    worker=Worker(resumed,TestProvider())
    applied=run(worker)
    assert applied['value']['status']=='applied'
    assert applied['value']['attempts']==2
    version=resumed.profile()['version']
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    first.finish(claimed,raw)
    assert resumed.profile()['version']==version
    assert run(worker) is None


@pytest.mark.parametrize('change',['settings','checkpoint','plan_state'])
def test_stale_results_never_overwrite(env,change):
    _,m,c=env
    s,r=save_review(c,[attempt()])
    worker=Worker(c,TestProvider()); claimed=worker.claim()
    if change=='settings': c.settings('settings',1,dict(preferred_mechanic='contrast'),True)
    elif change=='checkpoint': c.save('cp',s['session']['id'],2,[])
    else: c.transition('branch',s['session']['id'],2,'branch',note='detour')
    before=c.profile()
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    assert worker.finish(claimed,raw)['value']['status']=='stale'
    assert c.profile()==before


@pytest.mark.parametrize('corruption',['bad_ref','overconfidence','unknown_skill','drop_item','invent_completion','preference_without_consent','extra_sql'])
def test_invalid_model_result_not_applied(env,corruption):
    _,m,c=env
    save_review(c,[attempt(assistance='hint')])
    worker=Worker(c,TestProvider()); claimed=worker.claim()
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    if corruption=='bad_ref': raw['findings'][0]['evidence_ids']=['fake']
    elif corruption=='overconfidence': raw['findings'][0]['uncertainty']='low'
    elif corruption=='unknown_skill': raw['findings'][0]['skill_id']='made_up'
    elif corruption=='drop_item': raw['changes'][-1]['plan'].pop()
    elif corruption=='invent_completion': raw['changes'][-1]['plan'][0]['status']='done'
    elif corruption=='preference_without_consent': raw['changes'].append(dict(kind='preference',mechanic='contrast',why='assumed',evidence_ids=[],uncertainty='high',verify='test'))
    else: raw['sql']='DROP TABLE attempts'
    assert worker.finish(claimed,raw)['value']['status']=='failed'
    assert c.profile()['version']==1


@pytest.mark.parametrize('case',['little_data','repeated_errors','boredom','explicit_change','hinted_success'])
def test_pedagogical_scenarios(env,case):
    _,m,c=env
    aa=[]; feedback=[]
    if case=='repeated_errors': aa=[attempt(str(i),outcome='incorrect') for i in range(3)]
    if case=='hinted_success': aa=[attempt(assistance='hint')]
    if case=='boredom': feedback=[dict(id='f',kind='boredom',text='This format is boring')]
    if case=='explicit_change': feedback=[dict(id='f',kind='change_exercise',text='Please use cold retrieval',mechanic='retrieval')]
    save_review(c,aa,feedback)
    done=run(Worker(c,TestProvider()))
    assert done['value']['status']=='applied'
    review=done['value']['result']; p=c.profile()['value']; skill=c.context()['skills']['clarify']
    assert all(f['verify'] and f['hypothesis'] for f in review['findings'])
    if case=='little_data':
        assert skill['state']=='insufficient_data'
        assert review['findings'][0]['uncertainty']=='high'
        assert 'diagnose' in review['findings'][0]['hypothesis']
    elif case=='repeated_errors':
        assert p['plan'][0]['mechanic']=='contrast'
        assert 'transfer' in p['plan'][0]['task']
        assert skill['independent_correct']==0
    elif case=='boredom':
        assert p['plan'][0]['mechanic']=='contrast'
        assert p['settings']['preferred_mechanic']=='roleplay'  # no fabricated durable preference
        assert skill['independent_total']==0
    elif case=='explicit_change':
        assert p['plan'][0]['mechanic']=='retrieval'
        assert p['settings']['preferred_mechanic']=='retrieval'
        assert skill['state']=='insufficient_data'
    elif case=='hinted_success':
        assert p['plan'][0]['mechanic']=='retrieval'
        assert skill['independent_total']==0 and skill['assisted_total']==1
        assert 'unverified' in review['findings'][0]['hypothesis']


def test_settings_actual_versions_restore_and_new_session(env):
    _,m,c=env
    s=c.start('s'); sid=s['session']['id']; item=s['coach']['value']['items'][0]['id']
    c.transition('begin',sid,1,'begin_item',item_id=item)
    c.save('cp',sid,1,[attempt()])
    switched=c.switch('switch',sid,3,item,'retrieval',True)
    c.save('cp2',sid,2,[attempt('b')])
    sd=c.required('coach-session-'+sid)
    assert [u['mechanic'] for u in sd['value']['usages']]==['roleplay','retrieval']
    assert all(u['version']==1 for u in sd['value']['usages'])
    c.transition('end',sid,5,'finish',explicit_end=True)
    new=c.start('new')
    assert new['coach']['value']['settings_snapshot']['preferred_mechanic']=='retrieval'
    restored=c.restore('restore',2,1,'settings',True)
    assert restored['version']==3
    assert restored['value']['settings']['preferred_mechanic']=='roleplay'
    assert len(c.history())==3
    assert len(c.legacy.observations())==2


def test_goal_load_proposals_require_approval(env):
    _,m,c=env
    save_review(c)
    worker=Worker(c,TestProvider()); claimed=worker.claim()
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    raw['changes'].append(dict(kind='load',minutes=40,why='Try more practice',evidence_ids=[],uncertainty='high',verify='Ask about burden'))
    j=worker.finish(claimed,raw)
    assert c.profile()['value']['goal']['minutes']==20
    assert j['value']['proposals'][0]['status']=='proposed'
    with pytest.raises(ValueError): c.decide('bad',j['key'],1,2,True,False)
    result=c.decide('approve',j['key'],1,2,True,True)
    assert result['value']['goal']['minutes']==40
    assert c.decide('approve',j['key'],1,2,True,True)==result


def test_discoveries_explicit_priority_recall_and_isolation(env):
    store,m,c=env
    s=c.start('s')['session']
    discovery=dict(id='d',scope='personal',skill_id='clarify',cue='Recall your delivery analogy',context='negotiation',evidence_ids=[],reuse_trigger='asking for clarification',explicit_save=True)
    c.save('save',s['id'],1,[],discoveries=[discovery])
    cue=c.context()['discoveries'][0]
    assert cue['cue']==discovery['cue'] and cue['explicit_save']
    assert 'recall cues' in c.context()['guidance']
    for project in ('kids','b2b'):
        other=MemoryAPI(store,'owner',project,[project])
        assert other.get('coach-discovery-d') is None
        assert other.list('coach-')==[]
    with pytest.raises(ValueError): MemoryAPI(store,'other','english',['english'])
    with pytest.raises(ValueError): MemoryAPI(store,'owner','english',['kids'])


def test_adopt_existing_legacy_session_without_copying_or_inventing_attempts(env):
    store,m,c=env
    old=store.start_session('owner',['english'],'legacy','Historical goal')
    a=attempt()
    store.checkpoint('owner',['english'],'legacy-cp',old['id'],1,[a])
    before=store.get_session('owner',['english'],old['id'])
    adopted=c.start('adopt')
    assert adopted['session']['id']==old['id']
    assert adopted['coach']['value']['adopted_legacy']
    assert sum(i['id'].startswith('legacy-') for i in adopted['coach']['value']['items'])==3
    assert c.legacy.get(old['id'])==before
    assert len(c.legacy.observations())==1


def test_provider_runs_outside_sqlite_transaction(env):
    store,m,c=env
    save_review(c)
    class Probe:
        async def review(self,snapshot):
            other=Store(store.path,store.export_root)
            MemoryAPI(other,'owner','b2b',['b2b']).put('probe',{'ok':True},0)
            return await TestProvider().review(snapshot)
    assert run(Worker(c,Probe()))['value']['status']=='applied'


def test_plan_load_cannot_be_smuggled_into_automatic_change(env):
    _,m,c=env
    save_review(c)
    worker=Worker(c,TestProvider()); claimed=worker.claim()
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    raw['changes'][0]['plan'][0]['minutes']=120
    assert worker.finish(claimed,raw)['value']['status']=='failed'
    assert c.profile()['value']['goal']['minutes']==20


def test_observation_without_explicit_item_does_not_invent_mechanic_usage(env):
    _,m,c=env
    s=c.start('s')['session']
    a=attempt()
    c.save('cp',s['id'],1,[a])
    assert c.required('coach-session-'+s['id'])['value']['usages']==[]
    sd=c.required('coach-session-'+s['id'])
    item=sd['value']['items'][0]['id']
    c.transition('begin',s['id'],2,'begin_item',item_id=item)
    c.save('cp2',s['id'],2,[attempt('b')])
    c.save('cp3',s['id'],3,[a])
    # The old observation must not be retroactively assigned to a mechanic at retry time.
    usage=c.required('coach-session-'+s['id'])['value']['usages']
    assert len(usage)==1
