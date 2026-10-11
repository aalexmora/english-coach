"""Multi-learner public API boundaries. Synthetic data only."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import pytest
from saver.store import Store, StoreError
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.methodologist import Worker, TestProvider


def coach(store, user):
    if user != 'owner': store.register_user(user)
    return Coach(MemoryAPI(store,user,'english',['english']),LegacyEnglishAPI(store,user,['english']))


def setup(c):
    pattern=c.legacy.add_pattern('pattern','Can we talk tomorrow?')
    c.configure('goal',dict(outcome='Discuss '+c.learner_id,minutes=15,milestones=['Ask a question'],
        skills=[dict(id='question',outcome='Ask a clear question',pattern_ids=[pattern['id']])]),confirmed=True)
    session=c.start('start')['session']
    a=dict(idempotency_key='same-observation',pattern_id=pattern['id'],occurred_at=datetime.now(timezone.utc).isoformat(),
           outcome='correct',assistance='independent',context='a simple conversation',mode='free',
           observation='Synthetic answer by '+c.learner_id)
    saved=c.save('same-save',session['id'],session['version'],[a],review=True)
    return session,saved


def test_two_learners_ids_metrics_jobs_and_old_owner_history(tmp_path):
    store=Store(tmp_path/'memory.sqlite',tmp_path/'export')
    a=coach(store,'owner'); b=coach(store,'learner-b')
    assert b.context()['legacy_progress']['patterns']==[]
    assert not b.context('runtime')['configured']
    sa,ra=setup(a); before=deepcopy(a.context()); sb,rb=setup(b)
    assert sa['id']!=sb['id']
    assert ra['review_job']==rb['review_job']  # same logical key, independent namespace
    assert a.required(ra['review_job'])['id']!=b.required(rb['review_job'])['id']
    assert a.legacy.observations()[0]['id']!=b.legacy.observations()[0]['id']
    assert a.context()==before
    assert b.context('runtime')['learner_id']=='learner-b'
    assert a.required('coach-session-'+sa['id'])['value']['learner_id']=='owner'
    for current,foreign in ((a,sb),(b,sa)):
        with pytest.raises(StoreError): current.legacy.get(foreign['id'])
        with pytest.raises(StoreError): current.legacy.checkpoint('intrude',foreign['id'],1,[])
    assert b.memory.get('coach-session-'+sa['id']) is None
    assert b.memory.history('coach-session-'+sa['id'])==[]
    for current in (a,b):
        job=current.required(ra['review_job'])['value']
        assert job['learner_id']==job['snapshot']['learner_id']==current.learner_id
        assert {x['user_id'] for x in job['snapshot']['observations']}=={current.learner_id}
    with pytest.raises(ValueError,match='same learner'): Coach(a.memory,b.legacy)
    store.export()
    assert (store.export_root/'english'/ (a.profile()['id']+'.md')).is_file()
    path=store.export_root/'learners'/'learner-b'/'english'
    assert (path/(b.profile()['id']+'.md')).is_file()
    assert not (path/(a.profile()['id']+'.md')).exists()
    restarted=Store(store.path,store.export_root)
    assert coach(restarted,'owner').profile()==a.profile()
    assert coach(restarted,'learner-b').profile()==b.profile()
    assert coach(restarted,'owner').memory.history('coach-profile')==a.memory.history('coach-profile')


@pytest.mark.parametrize('where',['job','snapshot','profile','session','observation'])
def test_worker_blocks_foreign_snapshot_before_provider(tmp_path,where):
    store=Store(tmp_path/'memory.sqlite',tmp_path/'export'); c=coach(store,'learner-b')
    _,r=setup(c); doc=c.required(r['review_job']); v=deepcopy(doc['value'])
    if where=='job': v['learner_id']='owner'
    elif where=='snapshot': v['snapshot']['learner_id']='owner'
    elif where=='observation': v['snapshot']['observations'][0]['user_id']='owner'
    else: v['snapshot'][where]['user_id']='owner'
    c.memory.put(doc['key'],v,doc['version'])
    class ForbiddenProvider:
        async def review(self,snapshot): pytest.fail('Foreign learner input reached model')
    result=asyncio.run(Worker(c,ForbiddenProvider()).run_once())
    assert result['value']['status']=='failed'
    assert result['value']['error_category']=='identity'
    assert c.profile()['version']==1


def test_worker_preserves_old_owner_job_without_rewriting_history(tmp_path):
    c=coach(Store(tmp_path/'memory.sqlite',tmp_path/'export'),'owner'); _,r=setup(c)
    doc=c.required(r['review_job']); v=deepcopy(doc['value'])
    v.pop('learner_id'); v['snapshot'].pop('learner_id')
    v['snapshot']['session']['value'].pop('learner_id')
    c.memory.put(doc['key'],v,doc['version'])
    assert asyncio.run(Worker(c,TestProvider()).run_once())['value']['status']=='applied'


def test_disabled_learner_during_review_does_not_apply(tmp_path):
    c=coach(Store(tmp_path/'memory.sqlite',tmp_path/'export'),'learner-b'); setup(c)
    active=True
    class DeactivatingProvider:
        async def review(self,snapshot):
            nonlocal active
            active=False
            return await TestProvider().review(snapshot)
    result=asyncio.run(Worker(c,DeactivatingProvider(),authorized=lambda:active).run_once())
    assert result['value']['status']=='queued'
    assert c.profile()['version']==1
