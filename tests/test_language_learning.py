"""Language-neutral onboarding, approval, review and scoped observations."""
import asyncio
import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from english_coach.language_learning import LanguageLearning


class FakeMethodologist:
    async def _complete(self, system, payload, schema, name):
        if name=='language_program':
            assert payload['language']=='es'
            assert payload['requested_goal']['level']=='A1'
            return dict(rationale='Progress from travel greetings through everyday questions.',
                steps=[
                    dict(id='arrivals',topic='Arriving at the airport',
                         communicative_goal='Ask where to find transport',
                         prompts=['¿Dónde está el autobús?','¿Cuánto cuesta el billete?'],
                         success_criterion='Ask a destination and price independently'),
                    dict(id='hotel',topic='Checking in at a hotel',
                         communicative_goal='Explain a booking',
                         prompts=['Tengo una reserva.','¿A qué hora es el desayuno?'],
                         success_criterion='Make a booking request independently'),
                    dict(id='food',topic='Ordering food',
                         communicative_goal='Ask for a meal',
                         prompts=['Quisiera un café.','¿Tiene agua?'],
                         success_criterion='Order a meal and ask a question independently')])
        if name=='language_review':
            assert payload['language']=='es'
            assert payload['lesson']['observations'][0]['reply']=='¿Dónde está el autobús?'
            return dict(summary='The first independent question is saved, not certified.',
                        next_step_id='arrivals',
                        next_prompts=['¿Dónde está la estación?','¿Cuándo sale el tren?'],
                        rationale='Revisit the same communicative goal in a new context.',
                        learning_findings=['One independently produced location question'])
        raise AssertionError(name)


@pytest.fixture
def learning(tmp_path):
    store=Store(tmp_path/'memory.sqlite',tmp_path/'exports')
    user='lp-0123456789abcdef'
    store.register_user(user,('english',))
    memory=MemoryAPI(store,user,'english',['english'])
    return LanguageLearning(memory,'es','ru')


def test_new_language_plan_requires_approval(learning):
    c=learning
    submitted=c.configure('goal','Speak Spanish in travel situations',20,
                          ['travel','outdoors'],'A1',confirmed=True)
    assert submitted['status']=='queued'
    assert c.start('too-early')['started'] is False
    prepared=asyncio.run(c.run_once(FakeMethodologist(),10))
    assert prepared['status']=='proposed'
    proposal=c.context()['proposal']
    assert proposal['value']['plan']['steps'][0]['id']=='arrivals'
    assert c.start('still-early')['started'] is False
    approved=c.approve_plan('approve',proposal['version'],approved=True)
    assert approved['status']=='applied'
    assert c.readiness()['lesson_ready']
    started=c.start('start',expected_plan_version=approved['plan_version'])
    assert started['started']
    assert started['step']['prompts'][0].startswith('¿')


def test_saved_replies_drive_next_lesson_without_editing_active_one(learning):
    c=learning
    c.configure('goal','Speak Spanish in travel situations',20,['travel'],'A1',confirmed=True)
    asyncio.run(c.run_once(FakeMethodologist(),10))
    proposal=c.context()['proposal']
    c.approve_plan('approve',proposal['version'],approved=True)
    started=c.start('start')
    sid=started['session_id']
    before=c.context()['active_session']['value']['step']['prompts']
    saved=c.observe('reply1',sid,1,'¿Dónde está el autobús?',assistance='independent')
    assert saved['saved']
    closed=c.finish('finish',sid,saved['session_version'],explicit_end=True)
    assert closed['review_status']=='queued'
    blocked=c.start('next',expected_plan_version=1)
    assert blocked['started'] is False
    assert blocked['status']=='queued'
    result=asyncio.run(c.run_once(FakeMethodologist(),10))
    assert result['status']=='applied'
    assert c.context()['active_session'] is None
    old=c.required('language-session-'+sid)['value']
    assert old['step']['prompts']==before
    next_session=c.start('next',expected_plan_version=c.context()['program']['version'])
    assert next_session['started']
    assert 'estación' in next_session['step']['prompts'][0]


def test_level_is_self_report_not_inferred(learning):
    response=learning.configure('first','Learn conversational Spanish',15,
                               ['family'],level=None,confirmed=True)
    assert response['status']=='queued'
    assert learning.required('language-goal')['value']['level_source']=='unknown'
