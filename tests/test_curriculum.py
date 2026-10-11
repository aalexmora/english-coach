from copy import deepcopy
import pytest
from test_coach import env, save_review, run
from english_coach.methodologist import Worker, TestProvider
from english_coach.curriculum import KEY


def program():
    return dict(schema='english_course_program_v1',
                source_analysis=[dict(id='sample', access='TOC only')],
                stages=[dict(id='foundation', source_ids=['sample'], diagnostic_prompt='Ask a fresh question')],
                teaching_state=dict(current_stage='foundation'),
                transition_rule=dict(description='Independent delayed transfer'))


def test_full_program_persists_in_context_snapshot_and_decision(env):
    _, m, c = env
    doc=m.put(KEY, program(), 0)
    assert c.context()['course_program']==doc
    session,saved=save_review(c)
    job=m.get(saved['review_job'])
    assert job['value']['snapshot']['course_program']==doc
    done=run(Worker(c, TestProvider()))
    assert done['value']['status']=='applied'
    assert c.profile()['value']['decision']['curriculum']['stage_id']=='foundation'
    assert m.get(KEY)==doc
    assert c.legacy.get(session['session']['id'])['session']['status']=='active'
    assert c.legacy.observations()==[]


@pytest.mark.parametrize('existing', [True, False])
def test_program_change_or_addition_makes_review_stale(env, existing):
    _,m,c=env
    if existing: m.put(KEY, program(), 0)
    save_review(c)
    worker=Worker(c,TestProvider())
    claimed=worker.claim()
    import asyncio
    result=asyncio.run(worker.provider.review(claimed['value']['snapshot']))
    m.put(KEY,program(),int(existing))
    assert worker.finish(claimed,raw=result)['value']['status']=='stale'
    assert c.profile()['version']==1


@pytest.mark.parametrize('bad', ['missing', 'stage', 'source', 'version'])
def test_false_curriculum_attribution_cannot_apply(env,bad):
    _,m,c=env
    m.put(KEY,program(),0)
    save_review(c)
    worker=Worker(c,TestProvider()); claimed=worker.claim()
    import asyncio
    result=asyncio.run(worker.provider.review(claimed['value']['snapshot']))
    if bad=='missing': result.pop('curriculum')
    elif bad=='stage': result['curriculum']['stage_id']='advanced'
    elif bad=='source': result['curriculum']['source_ids']=['unread-book']
    else: result['curriculum']['document_version']=99
    assert worker.finish(claimed,raw=result)['value']['status']=='failed'
    assert c.profile()['version']==1


def test_invalid_program_is_visible_and_blocks_provider(env):
    _,m,c=env
    m.put(KEY,{},0)
    assert c.context()['course_program']['invalid']
    save_review(c)
    class NeverCall:
        async def review(self,snapshot):
            raise AssertionError('Invalid curriculum must not reach provider')
    result=run(Worker(c,NeverCall(),max_attempts=1))
    assert result['value']['error']=='Invalid course program; review blocked'


def test_expired_retry_keeps_cause(env):
    _,m,c=env
    save_review(c)
    w=Worker(c,TestProvider(),max_attempts=1)
    claimed=w.claim(); v=deepcopy(claimed['value'])
    v['lease_until']='2000-01-01T00:00:00+00:00'
    v['error']='Provider TimeoutError'
    m.put(claimed['key'],v,claimed['version'])
    assert w.claim() is None
    assert m.get(claimed['key'])['value']['last_error']=='Provider TimeoutError'
