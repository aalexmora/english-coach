"""Policy selection across real public APIs, without live pedagogical claims."""
import asyncio
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.models import TeachingTurn
from english_coach.runtime import check_turn
from english_coach.speaking import Speaking
from english_coach.vocabulary import Vocabulary
from english_coach.homework import Homework
from english_coach.material import MaterialIntake
from english_coach.methodologist import Worker,TestProvider,HTTPProvider,provider_system
from english_coach import policies

@pytest.fixture
def pair(tmp_path):
    store=Store(tmp_path/'memory.sqlite',tmp_path/'export'); store.register_user('learner-c')
    def make(user): return Coach(MemoryAPI(store,user,'english',['english']),LegacyEnglishAPI(store,user,['english']))
    a,b=make('owner'),make('learner-c')
    a.configure('goal',dict(outcome='Ask basic questions',minutes=15,milestones=['Ask about yesterday'],
        skills=[dict(id='events',outcome='Ask about an event',pattern_ids=['past_simple_questions'])]),confirmed=True)
    p=b.legacy.add_pattern('pattern','Discuss an experience and give a reason')
    b.configure('goal',dict(outcome='Speak freely and correctly',minutes=15,milestones=['Develop an idea'],
        skills=[dict(id='events',outcome='Discuss an experience',pattern_ids=[p['id']]),
                dict(id='opinion',outcome='Explain an opinion',pattern_ids=[])]),confirmed=True,policy_id='conversation')
    return store,a,b,p['id']


def observed(pid,key='answer',outcome='incorrect',text='I have been there last year.',assistance='independent',context='a trip'):
    return dict(idempotency_key=key,pattern_id=pid,occurred_at=datetime.now(timezone.utc).isoformat(),
                outcome=outcome,assistance=assistance,context=context,mode='free',observation=text)


def begin(c,pid):
    s=c.start('start'); sid=s['session']['id']
    sd=c.transition('begin',sid,s['coach']['version'],'begin_item',s['coach']['value']['items'][0]['id'])
    return sid,Speaking(c).start('practice',sid,sd['version'],pid,'Tell me about a trip you remember.')


def respond(c,sid,p,a,correction=''):
    return Speaking(c).update('respond-'+a['idempotency_key'],p['key'],p['version'],sid,
        c.legacy.get(sid)['session']['version'],'respond',a,correction=correction)


def test_policy_versions_read_only_and_two_profiles(pair):
    _,a,b,pid=pair; before=deepcopy(a.context()); profile=b.profile()
    ctx=b.context('runtime'); policy=ctx['methodology']['policy']
    assert policy['id']=='conversation' and policy['version']=='1.0.0'
    assert 'C1' in policy['instructions'] and not policy['grammar_exercises']
    assert ctx['lesson_runtime']['vocabulary_policy']['level']=='natural'
    assert 'basic_vocabulary' not in ctx['methodology']['capabilities']
    assert 'after_turn_correction' in ctx['methodology']['capabilities']
    assert 'contrast' not in b.context()['mechanics']
    assert b.profile()==profile and a.context()==before
    assert a.context()['vocabulary']['level']=='basic'
    assert b.profile()['value']['settings']['homework_minutes']==0
    assert all(x['mechanic']=='conversation' for x in b.profile()['value']['plan'])
    catalog=policies.catalog(); assert {x['id'] for x in catalog}=={'foundation','conversation'}
    assert all(x['changes'][0]['version']==x['version'] for x in catalog)
    s=b.start('start')['coach']; historical=deepcopy(s)
    b.settings('future-settings',profile['version'],dict(homework_minutes=8),True)
    assert b.required(s['key'])==historical
    assert b.context('runtime')['lesson_runtime']['settings']['homework_minutes']==0
    malformed=deepcopy(s)
    malformed['value']['grammar_permissions']['step-events']='yes'
    with pytest.raises(ValueError,match='permission'):
        policies.session_selection(malformed,'step-events')
    assert b.context('runtime')['lesson_runtime']['future_settings']['homework_minutes']==8
    with pytest.raises(ValueError): b.configure('bad-policy',b.profile()['value']['goal'],b.profile()['version'],True,'foundation')
    assert a.context()==before


def test_conversation_correction_keeps_dialogue_and_imitation_is_assisted(pair):
    _,a,c,pid=pair; owner=deepcopy(a.context()); sid,p=begin(c,pid)
    assert p['value']['mode']=='conversation'
    p=respond(c,sid,p,observed(pid),correction='I went there last year.')
    assert p['value']['stage']=='produce' and not p['value']['repair_queue']
    with pytest.raises(ValueError,match='assisted'):
        respond(c,sid,p,observed(pid,'imitate-independent','correct','I went there last year.'))
    p=respond(c,sid,p,observed(pid,'imitate-assisted','correct','I went there last year.','immediate_repeat'))
    assert c.legacy.progress()['accuracy']['independent']['correct']==0
    assert c.legacy.progress()['accuracy']['immediate_repeat']['correct']==1
    with pytest.raises(ValueError): Speaking(c).update('drill',p['key'],p['version'],sid,c.legacy.get(sid)['session']['version'],'coach')
    with pytest.raises(ValueError): Speaking(c).update('transfer-too-soon',p['key'],p['version'],sid,c.legacy.get(sid)['session']['version'],'transfer',task='Tell me about a different event.')
    assert c.context('runtime')['lesson_runtime']['next_action']['stage']=='produce'
    p=Speaking(c).update('continue-topic',p['key'],p['version'],sid,c.legacy.get(sid)['session']['version'],'continue',task='What would you like to discuss next?')
    assert p['value']['stage']=='completed' and c.legacy.get(sid)['session']['status']=='active'
    assert len(c.legacy.observations())==2 and a.context()==owner


def test_guard_uses_scoped_permission_and_brief_corrections(pair):
    _,_,c,pid=pair;sid,_=begin(c,pid);sd=c.required('coach-session-'+sid)
    turn=TeachingTurn(activity='grammar_drill',requires_repetition=True,correction_count=3,correction_timing='interrupt').model_dump()
    r=check_turn(c,sid,sd['version'],turn)
    assert set(r['violations'])=={'grammar_permission_required','compulsory_repetition_disabled','one_important_correction_per_turn','let_learner_finish_thought'}
    allowed=TeachingTurn(correction_count=1,correction_timing='interrupt',meaning_blocked=True).model_dump()
    assert check_turn(c,sid,sd['version'],allowed)['allowed']
    with pytest.raises(ValueError): c.grammar_permission('unconfirmed',sd['version'],True,False,'item',sid,'step-events')
    sd=c.grammar_permission('one-block',sd['version'],True,True,'item',sid,'step-events')
    assert not c.policy()['grammar_exercises']
    assert check_turn(c,sid,sd['version'],TeachingTurn(activity='grammar_drill',requires_repetition=True).model_dump())['allowed']
    sd=c.switch('use-drill',sid,sd['version'],'step-events','contrast',True)
    assert c.profile()['value']['settings']['preferred_mechanic']=='conversation'
    # Explicitly start a drill on this one permitted block.
    practice=c.documents('coach-practice-')[0]
    value=deepcopy(practice['value']);value.update(stage='repair',mode='coaching',repair_queue=['pending'])
    c.memory.put(practice['key'],value,practice['version'])
    sd=c.grammar_permission('cancel-block',sd['version'],False,True,'item',sid,'step-events')
    assert sd['value']['items'][0]['mechanic']=='conversation'
    assert c.required(practice['key'])['value']['stage']=='produce'
    assert not c.required(practice['key'])['value']['repair_queue']
    practice=c.required(practice['key'])
    Speaking(c).update('next-topic',practice['key'],practice['version'],sid,1,'continue',task='Discuss another idea.')
    sd=c.transition('other-item',sid,c.required(sd['key'])['version'],'begin_item','step-opinion')
    assert not check_turn(c,sid,sd['version'],TeachingTurn(activity='grammar_drill').model_dump())['allowed']
    assert c.legacy.observations()==[]


def test_future_permission_does_not_change_active_session_or_old_snapshots(pair):
    _,a,c,pid=pair;sid,_=begin(c,pid);current=deepcopy(c.required('coach-session-'+sid))
    c.save('review',sid,1,[],review=True); w=Worker(c,TestProvider()); claimed=w.claim()
    old_snapshot=deepcopy(claimed['value']['snapshot'])
    future=c.grammar_permission('future',c.profile()['version'],True,True)
    assert future['value']['teaching_policy']['grammar_exercises']
    assert not c.policy(sid)['grammar_exercises']
    raw=asyncio.run(TestProvider().review(old_snapshot))
    assert w.finish(claimed,raw)['value']['status']=='stale'
    assert c.required(claimed['key'])['value']['snapshot']==old_snapshot
    c.grammar_permission('disable',c.profile()['version'],False,True)
    assert not c.policy()['grammar_exercises']
    assert a.policy()['grammar_exercises']


def test_homework_default_none_and_agreed_preparation_uses_no_worksheet(pair):
    _,a,c,pid=pair;s=c.start('first')['session']
    result=c.finalize('finish-first',s['id'],s['version'],1,[observed(pid)],True)
    assert result['homework'] is None and c.documents('coach-homework-')==[]
    c.settings('agree-preparation',c.profile()['version'],dict(homework_minutes=8),True)
    s=c.start('next')['session'];sd=c.required('coach-session-'+s['id'])
    result=c.finalize('finish-next',s['id'],s['version'],sd['version'],[observed(pid,'next-answer')],True)
    hw=result['homework']; assert hw['value']['optional'] and hw['value']['minutes']==8
    assert hw['value']['kind']=='conversation_preparation'
    brief=c.context('runtime')['homework']
    assert brief['optional'] and brief['kind']=='conversation_preparation'
    assert all(i['kind']=='free' and 'accepted' not in i for i in hw['value']['items'])
    check=Homework(c).submit('prepare-answer',hw['key'],hw['version'],[dict(item_id='1',text='I enjoyed the trip because I met my friends.',meaning='preserved',grammar='correct',lexis='acceptable',reason='Meaning clear; the chosen focus is correct.')])
    assert c.legacy.observations()[-1]['mode']=='free'
    assert len(c.legacy.observations())==3
    assert a.documents('coach-homework-')==[]


def test_lexical_limits_are_per_policy_and_keep_evidence_delay(pair):
    _,a,c,pid=pair;sa=a.start('start')['coach'];sc=c.start('start')['coach']
    phrase='From my own point of view'
    with pytest.raises(ValueError): Vocabulary(a).teach('too-long',sa['value']['session_id'],sa['version'],phrase,'По моему мнению',True)
    doc=Vocabulary(c).teach('natural-phrase',sc['value']['session_id'],sc['version'],phrase,'По моему мнению',True)
    assert doc['value']['source']=='teacher_natural_language_review'
    assert Vocabulary(c).context()['level']=='natural'
    c.save('one-use',sc['value']['session_id'],1,[observed(pid,'phrase-use','correct',phrase)])
    aid=c.legacy.observations()[0]['id']
    with pytest.raises(ValueError,match='exposed recently'):
        Vocabulary(c).record('premature',doc['key'],doc['version'],aid,'independent','a talk',True)
    assert a.documents('coach-lexical-')==[]

@pytest.mark.parametrize('bad',['mechanic','worksheet','activity'])
def test_review_rejects_grammar_suggestions_without_permission(pair,bad):
    _,_,c,pid=pair;sid,_=begin(c,pid)
    saved=c.save('review',sid,1,[observed(pid)],review=True); w=Worker(c,TestProvider()); claimed=w.claim()
    raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    item=raw['changes'][0]['plan'][0]
    if bad=='mechanic': item['mechanic']='contrast'
    elif bad=='worksheet': item['task']='Fill in the blank: I ___ there.'
    else: item['activity']='grammar_drill'
    result=w.finish(claimed,raw)
    assert result['value']['status']=='failed' and c.profile()['version']==1

@pytest.mark.parametrize('where',['session','profile','job'])
def test_unknown_policy_version_blocks_model(pair,where):
    _,_,c,pid=pair;sid,_=begin(c,pid);saved=c.save('review',sid,1,[],review=True)
    doc=c.required(saved['review_job']);v=deepcopy(doc['value'])
    if where=='job': v['snapshot']['teaching_policy']['version']='99.0.0'
    else: v['snapshot'][where]['value']['teaching_policy']['version']='99.0.0'
    c.memory.put(doc['key'],v,doc['version'])
    class NoCall:
        async def review(self,snapshot): pytest.fail('Unknown policy reached model')
    result=asyncio.run(Worker(c,NoCall()).run_once())
    assert result['value']['status']=='failed' and result['value']['error_category']=='policy'


def test_material_and_real_provider_adapter_use_conversation_contract(pair,monkeypatch):
    _,a,c,pid=pair; text='A colleague explains a proposal and asks the team to discuss their reasons. This is synthetic material.'
    class Extraction:
        def __init__(self,bad=False): self.bad=bad;self.snapshot=None
        async def analyze_material(self,snapshot):
            self.snapshot=snapshot
            return dict(summary='Discussing a proposal',exercises=[dict(skill_id='events',situation='Discuss a proposal',
                first_prompt='Fill in the blank: We ___ agree.' if self.bad else 'What would make this proposal useful?',
                response_goal='Explain a reason',success_criterion='Develop a clear idea',transfer_prompt='Discuss a different proposal tomorrow.',
                mechanic='conversation',why='Diagnostic conversation',activity='communicative')])
    good=Extraction();asyncio.run(MaterialIntake(c,good,1).submit('source',text))
    assert good.snapshot['teaching_policy']['id']=='conversation'
    assert 'C1' in good.snapshot['teaching_contract']['instructions']
    with pytest.raises(ValueError): asyncio.run(MaterialIntake(c,Extraction(True),1).submit('bad',text+' A new sample.'))
    source=c.documents('coach-source-')[0]; assert source['value']['teaching_policy']['id']=='conversation'
    assert all(e['mechanic']=='conversation' for e in source['value']['exercises'])
    assert a.documents('coach-source-')==[]
    sid,_=begin(c,pid);c.save('review',sid,1,[],review=True);job=c.documents('coach-job-')[0]
    captured=[]
    async def complete(self,system,snapshot,schema,name):
        captured.append(system)
        return await TestProvider().review(snapshot) if name=='english_review' else dict(materials=[],exercises=[])
    monkeypatch.setattr(HTTPProvider,'_complete',complete)
    adapter=HTTPProvider('https://test.example/completion','test','test-only-key',1,2500)
    asyncio.run(adapter.review(job['value']['snapshot']))
    asyncio.run(adapter.analyze_material(good.snapshot))
    assert all('C1' in system and 'FOUNDATION PRIORITY' not in system for system in captured)
    assert 'FOUNDATION PRIORITY' in provider_system(dict(profile=a.profile()))
    assert 'Repair requires' not in captured[0]
    result=asyncio.run(Worker(c,TestProvider()).run_once())
    assert result['value']['status']=='applied'
    assert all(x['mechanic']=='conversation' for x in c.profile()['value']['plan'])
