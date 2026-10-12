"""Methodology changes are personal, versioned, reversible, and not skill evidence."""
import asyncio
from copy import deepcopy
import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.management import Management,DRAFT,TRIAL
from english_coach.admin import AdminRead,AdminAction
from english_coach.methodologist import Worker,TestProvider,validate_review,ReviewRuleError
from english_coach.instructions import contract

@pytest.fixture
def setup(tmp_path):
    store=Store(tmp_path/'memory.sqlite',tmp_path/'export')
    def make(uid):
        store.register_user(uid)
        c=Coach(MemoryAPI(store,uid,'english',['english']),LegacyEnglishAPI(store,uid,['english']))
        c.configure('goal',dict(outcome='Простые вопросы',minutes=15,milestones=['Прошедшее'],skills=[dict(id='past',outcome='Спросить о вчерашнем дне',pattern_ids=['past_simple_questions'] if uid=='owner' else [])]),confirmed=True)
        return c
    return make('owner'),make('learner-family')

def data(c,**updates):
    cfg=Management(c).current_config()
    result=dict(policy_id=cfg['policy']['id'],grammar_exercises=cfg['policy']['grammar_exercises'],settings=cfg['settings'],minutes=cfg['goal']['minutes'])
    result['settings']['prompt_style']='guided';result.update(updates);return result

def draft(c,key='draft',**updates):
    m=Management(c);d=c.memory.get(DRAFT)
    return m.save_draft(key,c.profile()['version'],d['version'] if d else 0,data(c,**updates))['draft']

def publish(c,mode='future'):
    d=c.required(DRAFT);return Management(c).publish('publish-'+str(d['version']),c.profile()['version'],d['version'],mode)


def test_draft_read_and_reload_do_not_change_learning_history(setup):
    c,k=setup;before=deepcopy(c.profile());d=draft(c)
    again=Management(Coach(c.memory,c.legacy)).read()
    assert again['draft']==d and again['future']==contract(before['value']['teaching_policy'],before['value']['settings'])
    for page in ('home','methodology','roadmap','decisions'):assert AdminRead(c).read(page)['management']['draft']==d
    assert c.profile()==before and c.legacy.observations()==[] and c.legacy.sessions()==[]
    assert k.memory.get(DRAFT) is None
    assert d['value']['preview']['model_called'] is False


def test_draft_cas_and_invalid_rules_leave_no_draft(setup):
    c,_=setup;m=Management(c);bad=data(c);bad['settings']['instructions']='давай сложные слова'
    assert m.save_draft('invalid',1,0,bad)['ok'] is False
    assert c.memory.get(DRAFT) is None
    bad['settings']['instructions']='не давай сложные слова'
    assert m.save_draft('valid',1,0,bad)['ok']
    with pytest.raises(ValueError):m.save_draft('conflict',1,0,data(c))
    bad=data(c);bad['settings']['instructions']='заканчивай урок через 10 минут'
    assert m.save_draft('autoend',1,1,bad)['ok'] is False


def test_future_change_preserves_current_snapshot_and_rollback_is_new_version(setup):
    c,_=setup;s=c.start('s');sid=s['session']['id'];old=deepcopy(c.required('coach-session-'+sid));d=draft(c)
    r=publish(c);assert r['ok'] and c.profile()['version']==2
    m=Management(c).read();assert m['current']['snapshot']==old['value']['instruction_snapshot']
    assert m['future']['settings']['prompt_style']=='guided'
    assert c.context('runtime')['lesson_runtime']['teaching_instructions']==old['value']['instruction_snapshot']['teacher']['exact']
    assert c.required('coach-session-'+sid)==old
    r=Management(c).restore('restore',2,r['change']['key']);assert r['ok'] and r['profile_version']==3
    assert c.profile()['value']['settings']['prompt_style']=='brief'
    assert len(Management(c).read()['history'])==2 and c.legacy.observations()==[]


def test_trial_is_one_new_session_pause_resume_no_automatic_keep(setup):
    c,_=setup;s=c.start('existing');draft(c);assert publish(c,'trial')['ok']
    assert c.start('resume')['session']['id']==s['session']['id']
    assert c.required(TRIAL)['value']['status']=='waiting'
    c.transition('finish-existing',s['session']['id'],s['coach']['version'],'finish',explicit_end=True)
    t=c.start('trial-start');sid=t['session']['id'];assert t['coach']['value']['settings_snapshot']['prompt_style']=='guided'
    assert c.profile()['value']['settings']['prompt_style']=='brief'
    paused=c.transition('pause-trial',sid,t['coach']['version'],'pause',explicit_end=True)
    assert c.required(TRIAL)['value']['status']=='running'
    resumed=c.start('trial-resume');assert resumed['session']['id']==sid
    c.transition('finish-trial',sid,resumed['coach']['version'],'finish',explicit_end=True)
    td=c.required(TRIAL);assert td['value']['status']=='finished'
    next_lesson=c.start('ordinary');assert next_lesson['coach']['value']['settings_snapshot']['prompt_style']=='brief'
    before=deepcopy(next_lesson['coach'])
    assert Management(c).trial_decision('keep',c.profile()['version'],td['version'],True)['ok']
    assert c.profile()['value']['settings']['prompt_style']=='guided'
    assert c.required(before['key'])==before


def test_trial_rejects_goal_or_policy_change_and_can_cancel(setup):
    c,_=setup;draft(c,minutes=20);assert publish(c,'trial')['ok'] is False
    d=draft(c,'replace');assert publish(c,'trial')['ok']
    t=c.required(TRIAL);assert Management(c).trial_decision('cancel',1,t['version'],False)['ok']
    assert c.profile()['version']==1 and c.required(TRIAL)['value']['status']=='returned'


def test_cross_profile_actions_and_unconfirmed_or_extra_fields_rejected(setup):
    c,k=setup;draft(c);r=publish(c)
    with pytest.raises((ValueError,KeyError)):Management(k).restore('steal',1,r['change']['key'])
    action=AdminAction(c);args=dict(idempotency_key='x',learner_confirmed=False,expected_profile_version=2,kind='hard',text='')
    with pytest.raises(ValueError):action.execute('method_feedback',args)
    args.update(learner_confirmed=True,subject='family')
    with pytest.raises(ValueError):action.execute('method_feedback',args)
    assert Management(k).read()['feedback']==[]


def test_feedback_response_is_required_and_applied_only_with_fresh_snapshot(setup):
    c,_=setup;s=c.start('s');f=Management(c).feedback('feedback',1,'hard','Поясни проще')['feedback']
    assert c.legacy.observations()==[]
    j=Management(c).review_feedback('review',1);w=Worker(c,TestProvider());claimed=w.claim();snap=claimed['value']['snapshot']
    assert snap['methodology_feedback'][0]['id']==f['key']
    raw=asyncio.run(TestProvider().review(snap));assert raw['methodology_responses']
    missing=deepcopy(raw);missing['methodology_responses']=[]
    with pytest.raises(ReviewRuleError):validate_review(snap,missing)
    unknown=deepcopy(raw);unknown['methodology_responses'][0]['feedback_id']='other'
    with pytest.raises(ReviewRuleError):validate_review(snap,unknown)
    false_change=deepcopy(raw);false_change['methodology_responses'][0]['decision']='changed'
    with pytest.raises(ReviewRuleError):validate_review(snap,false_change)
    assert w.finish(claimed,raw)['value']['status']=='applied'
    assert c.required(f['key'])['value']['status']=='answered'
    assert c.legacy.observations()==[] and c.legacy.get(s['session']['id'])['session']['status']=='active'


def test_stale_review_does_not_answer_feedback(setup):
    c,_=setup;c.start('s');f=Management(c).feedback('f',1,'explain','')['feedback']
    Management(c).review_feedback('review',1);w=Worker(c,TestProvider());claim=w.claim();raw=asyncio.run(TestProvider().review(claim['value']['snapshot']))
    draft(c);publish(c)
    assert w.finish(claim,raw)['value']['status']=='stale'
    assert c.required(f['key'])['value']['status']=='pending'


def test_old_session_is_not_falsely_marked_as_delivered_or_verified(setup):
    c,_=setup;s=c.start('s');doc=c.required(s['coach']['key']);v=deepcopy(doc['value']);del v['instruction_snapshot'];c.memory.put(doc['key'],v,doc['version'])
    m=Management(c).read();assert m['current']['recorded'] is False and m['current']['snapshot'] is None
    assert m['verification']['status']=='not_recorded'


def test_waiting_trial_becomes_outdated_only_on_new_start(setup):
    c,_=setup;draft(c);publish(c,'trial');p=c.profile();v=deepcopy(p['value']);v['settings']['instructions']='Поясняй проще';c.memory.put(p['key'],v,p['version'])
    assert Management(c).read()['trial']['value']['status']=='waiting'
    s=c.start('s');assert s['coach']['value']['method_trial_id'] is None
    assert c.required(TRIAL)['value']['status']=='outdated'


def test_comparison_uses_recorded_instructions_and_does_not_claim_effectiveness(setup):
    c,_=setup;s=c.start('s');draft(c);publish(c)
    v=AdminRead(c).read('roadmap',days=0)['method_comparison']
    assert v['comparable'] and not v['sufficient']
    assert v['before']['independent']['total']==v['after']['independent']['total']==0
    assert c.legacy.observations()==[]


def test_conversation_permissions_and_trial_goal_controls_are_strict(setup):
    c,_=setup
    c.configure('conversation',c.profile()['value']['goal'],expected_version=1,confirmed=True,policy_id='conversation')
    m=Management(c);v=data(c);v['settings']['instructions']='давай грамматические задания'
    assert m.validate(v)['ok'] is False
    v['grammar_exercises']=True
    assert m.validate(v)['ok']
    v['settings']['instructions']='use advanced words';v['grammar_exercises']=False
    assert m.validate(v)['ok']
    v['settings']['preferred_mechanic']='contrast'
    assert m.validate(v)['ok'] is False
