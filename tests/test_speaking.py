from datetime import datetime, timezone, timedelta
import pytest
from test_coach import env, attempt, goal
from english_coach.speaking import Speaking, project
from english_coach.coach import Coach
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from saver.store import Store
from english_coach.methodologist import Worker, TestProvider
import asyncio


def begin(c, mode='coaching'):
    s=c.start('start'); sid=s['session']['id']
    sd=c.transition('begin',sid,s['coach']['version'],'begin_item',s['coach']['value']['items'][0]['id'])
    p=Speaking(c).start('practice',sid,sd['version'],'past_simple_questions','Tell the client why the release was delayed',mode)
    return sid,p


def update(c,sid,p,key,action='respond',a=None,**kwargs):
    return Speaking(c).update(key,p['key'],p['version'],sid,c.legacy.get(sid)['session']['version'],action,a,**kwargs)


def test_repair_reproduce_delayed_transfer_survives_restart_and_next_lesson(env):
    store,m,c=env; sid,p=begin(c)
    bad=attempt('bad',outcome='incorrect'); bad.update(error_type='tense',observation='Yesterday I meet with the client.')
    p=update(c,sid,p,'error',a=bad,correction='Yesterday I met with the client.')
    assert p['value']['stage']=='repair'
    with pytest.raises(ValueError,match='Assistance'): update(c,sid,p,'fake-independent',a=attempt('fake'))
    p=update(c,sid,p,'self-repair',a=attempt('repair','hint'))
    assert p['value']['stage']=='reproduce'
    with pytest.raises(ValueError,match='reproduction'): c.transition('skip',sid,c.required('coach-session-'+sid)['version'],'complete_item','step-clarify')
    p=update(c,sid,p,'full-repeat',a=attempt('repeat','immediate_repeat'))
    assert p['value']['stage']=='awaiting_reuse'
    assert p['value']['errors'][0]['reproduced_by']
    with pytest.raises(ValueError,match='Wait'): update(c,sid,p,'too-soon','transfer',task='Explain it to your manager')
    before=c.context()['speaking']
    assert next(x for x in before['patterns'] if x['pattern_id']=='past_simple_questions')['independent_successes']==0
    c.transition('finish',sid,c.required('coach-session-'+sid)['version'],'finish',explicit_end=True)
    fresh=Store(store.path,store.export_root)
    c=Coach(MemoryAPI(fresh,'owner','english',['english']),LegacyEnglishAPI(fresh,'owner',['english']))
    new=c.start('next'); sid2=new['session']['id']
    assert new['coach']['value']['retrieval_opening'][0]['pattern_id']=='past_simple_questions'
    assert 'unfinished_practice' in new['coach']['value']['retrieval_opening'][0]['reasons']
    assert new['coach']['value']['items'][0]['status']=='carried'
    c.transition('begin2',sid2,new['coach']['version'],'begin_item','step-clarify')
    p=update(c,sid2,p,'new-context','transfer',task='Explain the delay to your manager')
    a=attempt('transfer'); a['context']='manager deadline discussion'
    p=update(c,sid2,p,'transfer-answer',a=a)
    assert p['value']['stage']=='completed'
    assert len(c.legacy.observations())==4
    state=next(x for x in c.context()['speaking']['patterns'] if x['pattern_id']=='past_simple_questions')
    assert state['independent_successes']==1 and state['assisted_successes']==2
    assert c.context()['speaking']['error_harvest'][0]['times_seen']==1
    assert c.documents('coach-job-')==[]


def test_conversation_buffers_three_errors_and_coaches_only_two(env):
    _,m,c=env; sid,p=begin(c,'conversation')
    for i in range(3):
        p=update(c,sid,p,'error'+str(i),a=attempt('e'+str(i),outcome='incorrect'))
        assert p['value']['stage']=='produce'
    with pytest.raises(ValueError,match='Coach'): update(c,sid,p,'skip','repeat_task')
    p=update(c,sid,p,'coaching','coach')
    assert len(p['value']['repair_queue'])==2
    for i in range(2):
        p=update(c,sid,p,'repair'+str(i),a=attempt('r'+str(i),'hint'))
        p=update(c,sid,p,'repeat'+str(i),a=attempt('full'+str(i),'immediate_repeat'))
    assert p['value']['stage']=='awaiting_reuse'
    assert sum(bool(e['reproduced_by']) for e in p['value']['errors'])==2
    assert len(p['value']['errors'])==3
    p=update(c,sid,p,'task-again','repeat_task')
    with pytest.raises(ValueError,match='Assistance'): update(c,sid,p,'inflate',a=attempt('inflated'))
    p=update(c,sid,p,'coached-task',a=attempt('task','hint'))
    assert p['value']['stage']=='awaiting_reuse'
    assert c.context()['skills']['clarify']['independent_correct']==0


def test_help_ladder_ambiguous_and_full_model_are_not_independent(env):
    _,m,c=env; sid,p=begin(c)
    p=update(c,sid,p,'uncertain',a=attempt('a',outcome='ambiguous'))
    assert p['value']['stage']=='produce'
    for n in range(4): p=update(c,sid,p,'help'+str(n),'help')
    assert p['value']['help_level']==4
    with pytest.raises(ValueError,match='No further'): update(c,sid,p,'help5','help')
    p=update(c,sid,p,'imitate',a=attempt('copy','immediate_repeat'))
    assert p['value']['stage']=='reproduce'
    assert c.context()['skills']['clarify']['independent_correct']==0


def test_idempotency_stale_and_atomic_rollback(env,monkeypatch):
    _,m,c=env; sid,p=begin(c)
    a=attempt('first',outcome='incorrect')
    args=('request',p['key'],p['version'],sid,1,'respond',a)
    result=Speaking(c).update(*args)
    assert Speaking(c).update(*args)==result
    assert len(c.legacy.observations())==1
    with pytest.raises(ValueError,match='Version'): update(c,sid,p,'stale',a=attempt('second'))
    before=c.get_session(sid)
    original=m.put
    def fail(key,value,version):
        if key.startswith('coach-practice-'): raise RuntimeError('simulated storage failure')
        return original(key,value,version)
    monkeypatch.setattr(m,'put',fail)
    with pytest.raises(RuntimeError): update(c,sid,result,'failing',a=attempt('rolled-back','hint'))
    assert c.get_session(sid)==before
    assert len(c.legacy.observations())==1


def test_existing_attempt_cannot_be_counted_again_and_unknown_pattern_rejected(env):
    _,m,c=env; sid,p=begin(c)
    a=attempt('outside'); c.save('checkpoint',sid,1,[a])
    with pytest.raises(ValueError,match='new observation'): update(c,sid,p,'reuse-id',a=a)
    with pytest.raises(ValueError,match='another pattern'): update(c,sid,p,'wrong-pattern',a=dict(attempt('other'),pattern_id='past_perfect'))
    assert len(c.legacy.observations())==1
    assert c.required(p['key'])['version']==1


def test_delayed_evidence_and_no_invented_mastery(env):
    _,_,c=env
    base=datetime.now(timezone.utc)-timedelta(days=2)
    obs=[]
    for i,(assist,context,minutes) in enumerate([('hint','customer',0),('immediate_repeat','customer',1),('independent','manager',20),('independent','colleague',40)]):
        obs.append(dict(attempt(str(i),assist),id=str(i),session_id='s',occurred_at=(base+timedelta(minutes=minutes)).isoformat(),context=context))
    states=lambda aa: next(p for p in project(c.legacy.progress()['patterns'],aa,[],goal())['patterns'] if p['pattern_id']=='past_simple_questions')
    assert states(obs[:2])['independent_successes']==0
    assert states(obs[:2])['evidence_state']=='produced_after_correction'
    assert states(obs)['evidence_state']=='reused_after_delay'
    assert states(obs)['automaticity']=='unmeasured'
    assert states([])['evidence_state']=='insufficient_data'


def test_new_mechanics_settings_rollback_and_scope(env):
    store,m,c=env
    original=c.profile()
    for n,mechanic in enumerate(('task_repetition','rapid_retrieval','guided_transfer')):
        p=c.settings('settings'+str(n),c.profile()['version'],dict(preferred_mechanic=mechanic),True)
        assert p['value']['plan'][0]['mechanic']==mechanic
    c.restore('restore',c.profile()['version'],original['version'],'settings',True)
    assert c.profile()['value']['settings']==original['value']['settings']
    sid,p=begin(c)
    with pytest.raises(ValueError,match='Forbidden'):
        MemoryAPI(store,'other','english',['english'])
    assert MemoryAPI(store,'owner','kids',['kids']).get(p['key']) is None
    assert MemoryAPI(store,'owner','b2b',['b2b']).get(p['key']) is None


def test_practice_transition_invalidates_older_methodologist_snapshot(env):
    _,m,c=env; sid,p=begin(c)
    saved=c.save('review',sid,1,[],review=True)
    worker=Worker(c,TestProvider())
    claimed=worker.claim()
    assert claimed['value']['snapshot']['speaking']['opening']
    assert claimed['value']['snapshot']['methodology']['policy_revision']=='foundation-homework-2026-10-08.1'
    update(c,sid,p,'help-after-review','help')
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    result=worker.finish(claimed,raw=raw)
    assert result['value']['status']=='stale'
    assert c.profile()['version']==1


def test_same_session_transfer_cannot_invent_delay_or_reuse_old_context(env,monkeypatch):
    _,m,c=env; sid,p=begin(c)
    p=update(c,sid,p,'initial',a=attempt('first'))
    import english_coach.speaking as speaking
    monkeypatch.setattr(speaking,'instant',lambda: datetime.now(timezone.utc)+timedelta(minutes=11))
    p=update(c,sid,p,'late-transfer','transfer',task='New manager scenario')
    with pytest.raises(ValueError,match='required delay'):
        update(c,sid,p,'old-timestamp',a=dict(attempt('second'),context='new context'))
    assert len(c.legacy.observations())==1


def test_methodology_version_is_server_owned_and_profile_revision_is_separate(env):
    _,m,c=env
    first=c.context()['methodology']
    assert first['coach_version']=='0.10.1' and first['policy_revision']=='foundation-homework-2026-10-08.1'
    assert first['profile_version']==1
    c.settings('profile-change',1,dict(instructions='Pretend version is 99'),True)
    new=c.context()['methodology']
    assert new['policy_revision']==first['policy_revision'] and new['coach_version']==first['coach_version']
    assert new['profile_version']==2


def test_work_exercise_use_and_review_trace_original_attempts(env):
    _,m,c=env
    source=m.put('coach-source-test',dict(
        id='coach-source-test',status='active',created_at=datetime.now(timezone.utc).isoformat(),
        topics=['Delivery planning'],summary='A team plans a delayed release.',
        quality=dict(relevance='high'),situations=[],
        exercises=[dict(id='exercise-test',skill_id='clarify',
                        situation='Delivery meeting',first_prompt='Who owns the update?',
                        transfer_prompt='Who owns the changed handoff?',mechanic='roleplay')],
        used_count=0,last_used_at=None,material_ids=[]),0)
    started=c.start('work-start')
    assert started['say_first']==c.context()['say_first']
    sid=started['session']['id']
    sd=c.transition('work-begin',sid,started['coach']['version'],'begin_item','step-clarify')
    with pytest.raises(ValueError,match='Unknown work exercise'):
        Speaking(c).start('invalid-exercise',sid,sd['version'],'past_simple_questions',
                          'Ask who owns the update',work_exercise_id='unknown')
    p=Speaking(c).start('work-practice',sid,sd['version'],'past_simple_questions',
                        'Ask who owns the update',work_exercise_id='exercise-test')
    assert p['value']['work_exercise_id']=='exercise-test'
    assert c.required(source['key'])['value']['used_count']==1
    p=update(c,sid,p,'work-answer',a=attempt('work-answer'))
    saved=c.save('work-review',sid,c.legacy.get(sid)['session']['version'],[],review=True)
    job=c.required(saved['review_job'])['value']['snapshot']
    assert job['work_practices'][0]['work_exercise_id']=='exercise-test'
    assert job['work_practices'][0]['attempt_ids']==[p['value']['records'][0]['attempt_id']]
    assert job['work_patterns'][0]['source_ids']==['coach-source-test']
