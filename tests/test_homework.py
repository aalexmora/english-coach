from copy import deepcopy
import asyncio
import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.homework import Homework
from english_coach.models import TeachingTurn
from english_coach.runtime import check_turn
from english_coach.methodologist import Worker, TestProvider
from english_coach.vocabulary import Vocabulary
from test_coach import env, attempt


def finish(c):
    s=c.start('lesson');a=attempt('lesson-answer',outcome='incorrect')
    return c.finalize('final',s['session']['id'],1,1,[a],True),s,a


def test_atomic_finish_homework_final_review(env):
    _,m,c=env;r,s,a=finish(c)
    assert c.finalize('final',s['session']['id'],1,1,[a],True)==r
    assert r['saved'] and r['finished'] and r['review_status']=='queued'
    hw=r['homework'];assert 10<=hw['value']['minutes']<=15
    assert len(hw['value']['items'])==6 and all('accepted' not in i for i in hw['value']['items'])
    assert len(c.documents('coach-homework-'))==1
    assert asyncio.run(Worker(c,TestProvider()).run_once())['value']['status']=='applied'


def test_partial_new_chat_ledger_no_lesson_collision(env):
    store,m,c=env;r,s,_=finish(c);h=Homework(c);d=r['homework']
    active=c.start('next-lesson')['session'];aa=[dict(item_id='1',text='Did')]
    saved=h.submit('part1',d['key'],1,aa)
    assert h.submit('part1',d['key'],1,aa)==saved
    assert saved['status']=='partial' and len(saved['remaining_items'])==5
    assert c.legacy.progress()['active_sessions'][0]['id']==active['id']
    assert len(c.legacy.observations())==2
    new=Store(store.path,store.export_root)
    again=Coach(MemoryAPI(new,'owner','english',['english']),LegacyEnglishAPI(new,'owner',['english']))
    resumed=Homework(again).get();assert resumed['version']==2 and len(resumed['evidence'])==1
    assert resumed['evidence'][0]['context']=='Did'
    assert 'Did' not in str(m.get(d['key'])['value']['submissions'])
    out=Homework(again).submit('part2',d['key'],2,[dict(item_id='2',text='Did he go home?')])
    assert out['status']=='partial' and len(again.legacy.observations())==3
    assert again.legacy.get(s['session']['id'])['session']['status']=='finished'


def test_delay_keys_and_completion(env):
    _,m,c=env;r,_,_=finish(c);h=Homework(c);hid=r['homework']['key']
    free=dict(item_id='5',text='Did you call your mum yesterday?',meaning='preserved',grammar='correct',lexis='acceptable',reason='Вопрос с did и базовым call.')
    with pytest.raises(ValueError,match='not due'):h.submit('early',hid,1,[free])
    h.reveal('keys',hid,1);d=m.get(hid);v=deepcopy(d['value']);v['delayed_not_before']='2000-01-01T00:00:00+00:00';m.put(hid,v,2)
    aa=[dict(item_id='1',text='Did'),dict(item_id='2',text='Did he go home?'),dict(item_id='3',text='go'),dict(item_id='4',text='A'),free,dict(free,item_id='6',text='Where did Anna go yesterday?')]
    out=h.submit('all',hid,3,aa)
    assert out['status']=='checked' and out['remaining_items']==[]
    assert all(a['assistance']=='immediate_repeat' for a in out['checks'][:4])
    assert all(a['assistance']=='independent' for a in out['checks'][4:])
    assert c.context('runtime')['homework']['status']=='checked'


def test_checkpoint_pause_wrong_usage(env):
    _,m,c=env;s=c.start('s');sid=s['session']['id']
    c.transition('begin',sid,1,'begin_item',item_id='step-negotiate')
    c.save('save',sid,1,[attempt()]);d=c.required('coach-session-'+sid)
    assert d['value']['usages']==[] and d['value']['unassigned_attempts'][0]['reason']=='pattern_item_mismatch'
    c.transition('pause',sid,d['version'],'pause');assert c.documents('coach-homework-')==[]


def test_save_finish_supersedes_pending_review(env):
    _,m,c=env;s=c.start('s');sid=s['session']['id']
    saved=c.save('save',sid,1,[attempt()],review=True)
    ended=c.transition('end',sid,saved['coach_version'],'finish',explicit_end=True)
    assert m.get(saved['review_job'])['value']['status']=='superseded'
    assert ended['review_job']!=saved['review_job']
    assert asyncio.run(Worker(c,TestProvider()).run_once())['value']['status']=='applied'


def test_gate_repeat_identical_unfinished(env):
    _,m,c=env;s=c.start('s');sid=s['session']['id'];saved=c.save('save',sid,1,[attempt(assistance='immediate_repeat')])
    t=TeachingTurn(attempt_id=saved['attempt_ids'][0],claims_independent=True,claims_correction=True,learner_answer="Okay, I'll send it tonight.",proposed_answer="Okay, I'll send it tonight.",unfinished_answer=True)
    assert set(check_turn(c,sid,saved['coach_version'],t.model_dump())['violations'])=={'independent_claim_not_supported','identical_answer_is_not_correction','clarify_unfinished_meaning_first'}


def test_vocabulary_budget_and_assisted_evidence(env):
    _,m,c=env;s=c.start('s');sid=s['session']['id'];vocab=Vocabulary(c)
    target=vocab.teach('phrase',sid,1,'at home','дома',True)
    assert target['value']['state']=='seen'
    with pytest.raises(ValueError,match='budget'):vocab.teach('second',sid,1,'call me','позвони мне',True)
    with pytest.raises(ValueError,match='BASIC'):vocab.teach('bad',sid,1,'at work','на работе',False)
    a=attempt('assisted',assistance='hint');a['context']='I am at home.';saved=c.save('save',sid,1,[a])
    with pytest.raises(ValueError,match='unassisted'):vocab.record('wrong',target['key'],1,saved['attempt_ids'][0],'independent','home',True)
    d=vocab.record('true',target['key'],1,saved['attempt_ids'][0],'assisted','home',True)
    assert d['value']['independent_uses']==0 and d['value']['state']=='assisted'


def test_branch_state_recovery_retains_return_point(env):
    from test_speaking import begin
    _,m,c=env;sid,practice=begin(c)
    sd=c.required('coach-session-'+sid)
    branch=c.transition('branch',sid,sd['version'],'branch',note='Уточним форму, затем вернёмся.')
    v=deepcopy(branch['value']);v['current_item_id']='step-negotiate';bad=m.put(branch['key'],v,branch['version'])
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='resolve_state'
    repaired=c.transition('recover',sid,bad['version'],'resolve_state',item_id=practice['value']['item_id'],note='Продолжаем фактически начатую практику.')
    assert repaired['value']['branch']==branch['value']['branch']
    assert c.context('runtime')['lesson_runtime']['next_action']['kind']=='continue_practice'


def test_open_reply_needs_semantic_check(env):
    _,m,c=env;r,_,_=finish(c);h=Homework(c);d=r['homework'];v=deepcopy(d['value']);v['delayed_not_before']='2000-01-01T00:00:00+00:00';m.put(d['key'],v,1)
    with pytest.raises(ValueError,match='Teacher must check'):
        h.submit('unchecked',d['key'],2,[dict(item_id='5',text='Maybe yes')])
    assert len(c.legacy.observations())==1


def test_lexical_error_counts_without_invented_success(env):
    _,m,c=env;s=c.start('s');sid=s['session']['id'];vocab=Vocabulary(c)
    target=vocab.teach('phrase',sid,1,'at home','дома',True)
    d=m.get(target['key']);v=deepcopy(d['value']);v['first_taught_at']=v['last_exposed_at']='2000-01-01T00:00:00+00:00';target=m.put(d['key'],v,1)
    a=attempt('lexical-error',outcome='incorrect');a['context']='I am at house.';saved=c.save('save',sid,1,[a])
    result=vocab.record('lexical',target['key'],2,saved['attempt_ids'][0],'independent','home',False)
    assert result['value']['independent_total']==1 and result['value']['independent_uses']==0
    assert result['value']['state']=='seen'
