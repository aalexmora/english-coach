"""A complete synthetic conversation journey over the original host APIs."""
import asyncio
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.conversation import Conversation,ROUTE,suggested_topics
from english_coach.methodologist import Worker,TestProvider


@pytest.fixture
def family(tmp_path):
    s=Store(tmp_path/'memory.sqlite',tmp_path/'export');s.register_user('learner-k')
    def make(user):return Coach(MemoryAPI(s,user,'english',['english']),LegacyEnglishAPI(s,user,['english']))
    a,k=make('owner'),make('learner-k')
    a.configure('goal',dict(outcome='Simple questions',minutes=15,milestones=['Past events'],skills=[dict(id='past',outcome='Ask about yesterday',pattern_ids=['past_simple_questions'])]),confirmed=True)
    return s,a,k,Conversation(k)


def setup(v):
    return v.onboard('onboard',0,dict(outcome='Speak freely and correctly',minutes=18,
        interests=['travel','films'],situations=['friends','family'],comfortable_topic_ids=['everyday','travel'],
        reported_level='B2',level_source='administrator_statement'),True)


def begin(c):
    s=c.start('start');sid=s['session']['id'];sd=s['coach'];item=sd['value']['items'][0]
    return sid,c.transition('begin',sid,sd['version'],'begin_item',item['id'])


def reply(c,sd,key='answer',text='I have been there last year.',outcome='incorrect',assistance='independent',context='a trip'):
    item=next(i for i in sd['value']['items'] if i['id']==sd['value']['current_item_id'])
    pid=next(s['pattern_ids'][0] for s in c.profile()['value']['goal']['skills'] if s['id']==item['skill_id'])
    return dict(idempotency_key=key,pattern_id=pid,occurred_at=datetime.now(timezone.utc).isoformat(),
                outcome=outcome,assistance=assistance,context=context,mode='free',observation=text)


def annotation(a,focus='past_time',kind='actual_error',dimensions=None,corrected='I went there last year.'):
    return dict(attempt_key=a['idempotency_key'],demonstrated=dimensions or ['maintains_dialogue'],
                correction=dict(kind=kind,focus_id=focus,corrected_text=corrected,reason='A completed past event.',
                                meaning_preserved=True,occurred_at=datetime.now(timezone.utc)))


def save(v,c,sid,sd,a,n,key='checkpoint'):
    return v.save_block(key,sid,c.legacy.get(sid)['session']['version'],sd['version'],[a],[n],True)


def test_onboarding_requires_agreement_and_never_infers_level_or_minutes(family):
    _,a,c,v=family;owner=deepcopy(a.context());before=deepcopy(c.legacy.progress())
    read=v.get();assert not read['configured'] and len(read['suggested_topics'])==7
    assert not c.memory.get('coach-profile') and c.legacy.progress()==before
    args=dict(outcome='Conversation',minutes=12,interests=['films'],situations=['friends'],comfortable_topic_ids=['everyday','culture'])
    with pytest.raises(ValueError):v.onboard('unconfirmed',0,args,False)
    assert c.legacy.progress()==before
    p=v.onboard('agreed',0,args,True)
    assert p['value']['conversation']['proficiency']==dict(reported=None,source=None,assessed=False)
    assert p['value']['conversation']['route_status']=='provisional'
    assert p['value']['goal']['minutes']==12 and p['value']['settings']['homework_minutes']==0
    assert c.legacy.observations()==[] and len(c.legacy.progress()['patterns'])==5
    assert v.onboard('agreed',0,args,True)==p
    assert a.context()==owner


def test_full_journey_topics_corrections_route_finish_worker_and_next_lesson(family):
    _,a,c,v=family;owner=deepcopy(a.context());p=setup(v);sid,sd=begin(c)
    a1=reply(c,sd);r=save(v,c,sid,sd,a1,annotation(a1));sd=c.required(sd['key'])
    first=sd['value']['current_item_id'];assert c.context('runtime')['lesson_runtime']['conversation']['current_topic']['topic']['id']=='everyday'
    # Free discussion retains its planned return point and unfinished item.
    sd=v.select('free',sid,sd['version'],first,'free','culture',None,True)
    assert sd['value']['conversation']['items'][first]['return_to']['topic']['id']=='everyday'
    a2=reply(c,sd,'opinion','It made me see the character differently.','correct',context='a film')
    n2=dict(attempt_key='opinion',demonstrated=['develops_idea','maintains_dialogue'],correction=None)
    save(v,c,sid,sd,a2,n2,'checkpoint-2');sd=c.required(sd['key'])
    frozen=deepcopy(sd)
    evidence=[a['id'] for a in c.legacy.observations()]
    p=v.set_route('route',p['version'],['opinion','dialogue','story','comparison','spontaneous'],['culture','travel'],evidence,
                  'Her replies develop an opinion; continue that goal and observe follow-up questions.',True)
    assert p['value']['conversation']['route_status']=='agreed' and c.required(sd['key'])==frozen
    sd=v.select('return',sid,sd['version'],first,'return',None,None,True)
    assert sd['value']['conversation']['items'][first]['topic']['id']=='everyday'
    result=c.finalize('finish',sid,c.legacy.get(sid)['session']['version'],sd['version'],[],True)
    assert result['homework'] is None and result['conversation_summary']['value']['mode']=='text_conversation'
    summary=deepcopy(v.get(sid)['summary']);assert len(summary['value']['independent_examples'])==2
    assert len(summary['value']['correction_ids'])==1 and not any('observation' in e for e in summary['value']['independent_examples'])
    worker=Worker(c,TestProvider());job=worker.claim();snapshot=job['value']['snapshot']
    assert len(snapshot['conversation']['records'])==2
    assert {r['attempt_id'] for r in snapshot['conversation']['records']}==set(evidence)
    assert asyncio.run(worker.run_once()) is None  # claimed job is leased
    raw=asyncio.run(TestProvider().review(snapshot));assert worker.finish(job,raw)['value']['status']=='applied'
    nxt=c.start('next');ns=nxt['coach']
    assert next(i for i in ns['value']['items'] if i['id']==first)['status']=='carried'
    assert ns['value']['conversation']['items'][first]['topic']['id']=='everyday'
    sd=c.transition('resume',nxt['session']['id'],ns['version'],'begin_item',first)
    rt=c.context('runtime')['lesson_runtime'];assert rt['conversation']['next_verification_targets'][0]['focus_id']=='past_time'
    assert v.get(sid)['summary']==summary and a.context()==owner
    assert c.legacy.get(sid)['session']['status']=='finished' and len(c.legacy.observations())==2


def test_block_idempotency_references_and_no_copied_attempt_ledger(family):
    _,_,c,v=family;setup(v);sid,sd=begin(c);a=reply(c,sd);n=annotation(a)
    r=save(v,c,sid,sd,a,n);assert v.save_block('checkpoint',sid,1,sd['version'],[a],[n],True)==r
    block=r['block'];record=block['value']['records'][0]
    assert 'attempt_id' in record and 'observation' not in record and 'idempotency_key' not in record
    rows=v.get(sid)['records'];assert rows[0]['attempt']['observation']==a['observation']
    assert rows[0]['attempt']['assistance']=='independent'
    assert v.get(sid)['progress']['maintains_dialogue']['independent']==1
    latest=c.required(sd['key']);count=len(c.legacy.observations())
    with pytest.raises(ValueError):save(v,c,sid,latest,a,n,'duplicate-new-key')
    assert len(c.legacy.observations())==count and c.required(sd['key'])==latest


@pytest.mark.parametrize('case',['same_text','meaning','false_error','ambiguous','third_focus','unsupported_accuracy'])
def test_invalid_corrections_are_atomic_and_do_not_create_success(family,case):
    _,_,c,v=family;setup(v);sid,sd=begin(c)
    if case=='third_focus':
        for j in range(2):
            a=reply(c,sd,'a'+str(j));save(v,c,sid,sd,a,annotation(a,focus='focus_'+str(j)),'c'+str(j));sd=c.required(sd['key'])
    a=reply(c,sd,'bad');n=annotation(a,focus='third')
    if case=='same_text':n['correction']['corrected_text']=a['observation']
    if case=='meaning':n['correction']['meaning_preserved']=False
    if case=='false_error':a['outcome']='correct'
    if case=='ambiguous':a['outcome']='ambiguous'
    if case=='unsupported_accuracy':n['demonstrated']=['focus_accuracy'];n['correction']=None
    before=deepcopy(c.legacy.get(sid));docs=deepcopy(c.documents('coach-conversation-block-'))
    with pytest.raises(ValueError):save(v,c,sid,sd,a,n,'invalid')
    assert c.legacy.get(sid)==before and c.documents('coach-conversation-block-')==docs and c.required(sd['key'])==sd


def test_buffered_imitation_is_assisted_even_within_one_checkpoint(family):
    _,_,c,v=family;setup(v);sid,sd=begin(c)
    a=reply(c,sd,'wrong');n=annotation(a)
    b=reply(c,sd,'repeat','I went there last year.','correct');m=dict(attempt_key='repeat',demonstrated=['maintains_dialogue'],correction=None)
    with pytest.raises(ValueError,match='imitation'):v.save_block('wrong-label',sid,1,sd['version'],[a,b],[n,m],True)
    assert c.legacy.observations()==[]
    b['assistance']='immediate_repeat'
    r=v.save_block('assisted',sid,1,sd['version'],[a,b],[n,m],True)
    assert len(c.legacy.observations())==2 and len(r['block']['value']['records'])==2
    progress=v.get(sid)['progress']['maintains_dialogue'];assert (progress['independent'],progress['assisted'])==(1,1)


def test_natural_alternative_is_separate_and_reuse_requires_actual_delay(family):
    _,_,c,v=family;setup(v);sid,sd=begin(c)
    a=reply(c,sd,'first','The film was very interesting.','correct');n=annotation(a,kind='natural_alternative',corrected='I found the film compelling.')
    r=save(v,c,sid,sd,a,n);correction=r['block']['value']['records'][0]['correction']['id'];sd=c.required(sd['key'])
    b=reply(c,sd,'later','I found the book compelling.','correct',context='a book')
    m=dict(attempt_key='later',demonstrated=['delayed_reuse','focus_accuracy'],reused_from=correction)
    with pytest.raises(ValueError,match='Reuse'):save(v,c,sid,sd,b,m,'too-soon')
    # Simulate an elapsed exposure interval in a temporary fixture, not production.
    block=c.required(r['block']['key']);value=deepcopy(block['value']);value['records'][0]['correction']['at']=(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat()
    c.memory.put(block['key'],value,block['version'])
    save(v,c,sid,sd,b,m,'delayed')
    assert v.get(sid)['progress']['delayed_reuse']['independent']==1
    assert v.get()['next_conversation']['verification_targets']==[]  # optional wording is not an error


def test_editing_topics_keeps_current_and_carried_snapshots(family):
    _,_,c,v=family;p=setup(v);sid,sd=begin(c);original=deepcopy(sd)
    topics=suggested_topics();topics[0]['status']='skipped';topics[1]['questions'][0]='What would you change about your next trip?'
    custom=deepcopy(topics[0]);custom.update(id='family',status='active',title='Семья',questions=['What do you enjoy doing together?','What makes that time special?'])
    topics.append(custom);p=v.set_topics('topics',p['version'],topics,True)
    assert c.required(sd['key'])==original
    assert p['value']['conversation']['item_topics'][sd['value']['current_item_id']]=='free'
    goal=deepcopy(p['value']['goal']);goal['minutes']=10
    p=c.configure('new-agreed-load',goal,p['version'],True)
    assert p['value']['conversation']['interests']==['travel','films']
    assert sum(i['minutes'] for i in p['value']['plan'])==10
    assert c.required(sd['key'])==original
    c.finalize('finish',sid,1,sd['version'],[],True)
    ns=c.start('next')['coach'];first=sd['value']['current_item_id']
    assert ns['value']['conversation']['items'][first]['topic']['id']=='everyday'
    assert ns['value']['items'][0]['status']=='carried'
    bad=deepcopy(topics);bad[-1]['questions'][0]='Fill in the blanks: I ___ home.'
    with pytest.raises(ValueError):v.set_topics('hidden-worksheet',p['version'],bad,True)


def test_past_conversation_remains_readable_after_a_confirmed_policy_change(family):
    _,_,c,v=family;setup(v);sid,sd=begin(c);a=reply(c,sd)
    save(v,c,sid,sd,a,annotation(a));sd=c.required(sd['key'])
    for item in sd['value']['items']:sd=c.transition('done-'+item['id'],sid,sd['version'],'complete_item',item['id'])
    c.finalize('end',sid,c.legacy.get(sid)['session']['version'],sd['version'],[],True)
    before=deepcopy(v.get(sid));p=c.profile()
    c.configure('foundation',p['value']['goal'],p['version'],True,'foundation')
    past=v.get(sid)
    assert past['records']==before['records'] and past['summary']==before['summary']
    assert not past['configured'] and past['session_available'] and past['next_conversation'] is None
    with pytest.raises(ValueError):v.get(c.start('foundation-start')['session']['id'])


def test_foreign_session_is_rejected_before_onboarding(family):
    _,a,c,v=family;foreign=a.start('owner-start')['session']['id']
    with pytest.raises(ValueError):v.get(foreign)
    assert not c.memory.get('coach-profile')


def test_long_topic_keeps_its_context_and_finish_summary_stays_bounded(family):
    _,_,c,v=family;setup(v);sid,sd=begin(c);block_id=sd['value']['conversation']['items'][sd['value']['current_item_id']]['block_id']
    for batch in range(3):
        attempts=[reply(c,sd,f'reply-{batch}-{i}','I enjoyed discussing that idea.','correct') for i in range(16)]
        annotations=[dict(attempt_key=a['idempotency_key'],demonstrated=['develops_idea']) for a in attempts]
        v.save_block('batch-'+str(batch),sid,c.legacy.get(sid)['session']['version'],sd['version'],attempts,annotations,True)
        sd=c.required(sd['key'])
    assert len(c.legacy.observations())==48
    assert {d['value']['block_id'] for d in c.documents('coach-conversation-block-')}=={block_id}
    c.finalize('end-long',sid,c.legacy.get(sid)['session']['version'],sd['version'],[],True)
    page=v.get(sid,10);summary=page['summary']['value']
    assert len(page['records'])==10 and page['next_offset']==10 and page['total']==48
    assert summary['total_records']==48 and summary['independent_example_total']==48
    assert len(summary['independent_examples'])==5 and len(summary['evidence_ids'])==40
    assert page['progress']['develops_idea']['independent']==48


def test_route_and_topic_actions_reject_missing_evidence_stale_and_foreign_ids(family):
    _,a,c,v=family;p=setup(v);sid,sd=begin(c)
    with pytest.raises(ValueError):v.set_route('early',p['version'],[s['id'] for s in ROUTE],['travel'],[],'No observations',True)
    attempt=reply(c,sd);save(v,c,sid,sd,attempt,annotation(attempt));sd=c.required(sd['key'])
    with pytest.raises(ValueError,match='two'):v.set_route('one-topic',p['version'],[s['id'] for s in ROUTE],['travel'],[c.legacy.observations()[0]['id']],'Only one topic',True)
    with pytest.raises(ValueError):v.select('stale',sid,1,sd['value']['current_item_id'],'free','culture',None,True)
    foreign=a.start('owner-session')['session']['id']
    with pytest.raises(ValueError):v.get(foreign)
    with pytest.raises(ValueError):v.select('foreign',foreign,1,'missing','free','culture',None,True)
    assert c.legacy.get(sid)['session']['status']=='active'


def test_plan_completion_does_not_end_lesson_and_pause_stays_paused(family):
    _,_,c,v=family;setup(v);sid,sd=begin(c)
    for item in sd['value']['items']:sd=c.transition('complete-'+item['id'],sid,sd['version'],'complete_item',item['id'])
    assert c.legacy.get(sid)['session']['status']=='active'
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='free_practice'
    with pytest.raises(ValueError):c.transition('implicit-end',sid,sd['version'],'finish')
    sd=c.transition('pause',sid,sd['version'],'pause')
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='await_resume'
    with pytest.raises(ValueError):v.select('paused',sid,sd['version'],sd['value']['items'][0]['id'],'free','free',None,True)
