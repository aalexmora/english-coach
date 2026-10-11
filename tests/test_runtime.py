from copy import deepcopy
from datetime import datetime,timezone,timedelta
import json
import pytest
from test_coach import env,attempt
from test_speaking import begin,update
from english_coach.runtime import compact,lesson_runtime,health,check_turn
from english_coach.models import TeachingTurn
from english_coach.speaking import project


def test_compact_context_preserves_authority_without_mutation(env):
    _,m,c=env
    s=c.start('start');sid=s['session']['id']
    before=m.get('coach-session-'+sid)
    value=deepcopy(before['value']);value['items'][0]['status']='carried'
    m.put(before['key'],value,before['version'])
    before=m.get(before['key'])
    result=c.context('runtime');r=result['lesson_runtime']
    assert r['next_action']['kind']=='begin_item'
    assert r['state_authority']['issues']==[]
    assert 'usages' not in r and 'jobs' not in result and 'observations' not in r
    assert len(json.dumps(result,ensure_ascii=False).encode())<=24576
    assert m.get(before['key'])==before
    assert c.profile()['value']['plan'][0]['status']=='pending'


def test_orphan_pointer_blocks_instead_of_guessing(env):
    _,m,c=env;s=c.start('start')['coach'];v=deepcopy(s['value']);v['current_item_id']='missing'
    m.put(s['key'],v,s['version'])
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='resolve_state'


def test_repair_wins_over_due_and_waiting_reuse_does_not_block(env):
    _,m,c=env;sid,p=begin(c)
    p=update(c,sid,p,'wrong',a=attempt('wrong',outcome='incorrect'))
    ctx=c.context();ctx['speaking']['queue']=[dict(pattern_id='past_simple_questions',skill_id='clarify',reasons=['scheduled_due'],evidence_ids=[])]
    action=lesson_runtime(ctx)['next_action']
    assert action['kind']=='continue_practice' and action['stage']=='repair'
    p=update(c,sid,p,'hint',a=attempt('hint','hint'))
    p=update(c,sid,p,'reproduce',a=attempt('reproduce','immediate_repeat'))
    r=c.context('runtime')['lesson_runtime']
    assert r['next_action']['kind']=='begin_item'
    assert r['next_action']['item_id']=='step-negotiate'
    assert r['verification'][0]['practice_id']==p['key']


def test_due_check_on_task_boundary_keeps_return(env):
    _,m,c=env;c.start('start');ctx=c.context()
    ctx['speaking']['queue']=[dict(pattern_id='past_simple_questions',skill_id='clarify',reasons=['scheduled_due'],evidence_ids=[])]
    r=lesson_runtime(ctx)
    assert r['next_action']['kind']=='prepare_cold_check'
    assert r['next_action']['return_to']=='step-clarify'
    assert r['next_action']['prompt'] is None


def test_paused_driving_and_hands_free_are_explicit(env):
    _,m,c=env;s=c.start('start');sid=s['session']['id']
    assert c.context('runtime','hands_free')['lesson_runtime']['next_action']['delivery'].startswith('One short')
    assert c.context('runtime','driving')['lesson_runtime']['next_action']['kind']=='defer_until_safe'
    assert c.required('coach-session-'+sid)['value']['phase']=='active'
    c.transition('pause',sid,s['coach']['version'],'pause')
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='await_resume'


def test_oversized_core_context_requests_full_not_silent_truncation(env):
    _,m,c=env;c.start('start');ctx=c.context();ctx['profile']['value']['settings']['instructions']='я'*20000
    result=compact(ctx)
    assert result['full_context_required'] and 'lesson_runtime' not in result


def test_completed_plan_never_ends_without_learner(env):
    _,m,c=env;s=c.start('start');sid=s['session']['id']
    for item in s['coach']['value']['items']:
        c.transition('complete-'+item['id'],sid,c.required('coach-session-'+sid)['version'],'complete_item',item['id'])
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='free_practice'
    with pytest.raises(ValueError,match='explicit learner end'):
        c.transition('auto-end',sid,c.required('coach-session-'+sid)['version'],'finish')
    c.transition('explicit-end',sid,c.required('coach-session-'+sid)['version'],'finish',explicit_end=True)


def test_teaching_turn_gate_and_stale_versions(env):
    _,m,c=env;s=c.start('start');sid=s['session']['id'];saved=c.save('a',sid,1,[attempt('a',outcome='incorrect')])
    v=c.required('coach-session-'+sid)['version']
    turn=TeachingTurn(attempt_id=saved['attempt_ids'][0],praises_correctness=True,independent_check=True,reveals_answer=True,ends_lesson=True,meaning_preserved='no',question_count=2).model_dump()
    result=check_turn(c,sid,v,turn)
    assert not result['allowed'] and len(result['violations'])==5
    with pytest.raises(ValueError,match='Stale'):check_turn(c,sid,v-1,turn)
    assert check_turn(c,sid,v,TeachingTurn().model_dump())['semantic_review_required']


def test_job_health_uses_time_and_recovery_not_old_failure():
    def job(key,at,status):return dict(key=key,created_at=at,updated_at=at,value=dict(status=status,error=None))
    r=health([job('z','2026-10-01','failed'),job('a','2026-10-06','applied')])
    assert r['state']=='ok' and r['latest']['id']=='a' and r['last_failure']['id']=='z'


def test_recent_metrics_ignore_old_assisted_and_ambiguous(env):
    _,m,c=env
    at=datetime.now(timezone.utc)
    p=dict(id='past_simple_questions',text='Ask',next_review=None)
    def obs(i,days,outcome='incorrect',assistance='independent',context='one',cold=False):
        return dict(id=str(i),pattern_id=p['id'],session_id=str(i),occurred_at=(at-timedelta(days=days)).isoformat(),outcome=outcome,assistance=assistance,context=context,mode='free',before_warmup=cold)
    aa=[obs(1,30),obs(2,29),obs(3,28),obs(4,3,'correct',context='two'),obs(5,2,'correct',context='three'),obs(6,1,'ambiguous'),obs(7,.5,'incorrect','hint'),obs(8,0,'incorrect',cold=True)]
    row=project([p],aa,[],c.profile()['value']['goal'],at)['patterns'][0]
    assert row['recent']['independent_total']==3
    assert row['recent']['independent_errors']==1
    assert row['recent']['cold_total']==1 and row['recent']['cold_failure_rate']==1
    assert not row['recurring_error'] and row['needs_practice'] and row['verification_needed']
    assert row['retention_evidence']=='observed_on_later_date' and row['mastery']=='not_certified'


def test_unreviewed_work_exercise_not_offered_as_model(env):
    _,m,c=env;c.start('start');ctx=c.context()
    exercise=dict(id='x',skill_id='clarify',first_prompt='Ask about the owner',source_id='source',teaching_eligible=False)
    ctx['lesson_brief']=[exercise]
    ctx['reviewed_lesson_brief']=[exercise]
    assert lesson_runtime(ctx)['work_exercises']==[]
    exercise['teaching_eligible']=True
    r=lesson_runtime(ctx)
    assert r['next_action']['work_exercise_id']=='x'


def test_ready_reuse_survives_next_lesson_without_current_pointer(env):
    _,m,c=env;sid,p=begin(c)
    p=update(c,sid,p,'first',a=attempt('first'))
    assert p['value']['stage']=='awaiting_reuse'
    c.transition('finish',sid,c.required('coach-session-'+sid)['version'],'finish',explicit_end=True)
    c.start('next-lesson')
    a=c.context('runtime')['lesson_runtime']['next_action']
    assert a['kind']=='prepare_transfer' and a['practice_id']==p['key']
    assert a['item_id']=='step-clarify'


def test_waiting_reuse_pointer_does_not_conflict_with_explicit_next_item(env):
    _,m,c=env;sid,p=begin(c)
    update(c,sid,p,'correct',a=attempt('correct'))
    c.transition('next-item',sid,c.required('coach-session-'+sid)['version'],'begin_item','step-negotiate')
    r=c.context('runtime')['lesson_runtime']
    assert r['state_authority']['issues']==[]
    assert r['next_action']['kind']=='continue_item' and r['next_action']['item_id']=='step-negotiate'
    assert r['verification'][0]['practice_id']==p['key']
