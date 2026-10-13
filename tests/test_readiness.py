"""Lesson readiness invariants: queue, retry, outdated override and plan identity."""
import asyncio
from tests.test_coach import env, goal
from english_coach.methodologist import Worker, TestProvider


def test_readiness_blocks_future_lesson_until_review_is_applied(env):
    _, _, coach = env
    first = coach.start('first')
    sid = first['session']['id']
    saved = coach.save('review-save', sid, first['session']['version'], [], review=True)
    pending = coach.lesson_readiness()
    assert pending['status'] == 'queued'
    assert pending['job_id'] == saved['review_job']
    assert coach.start('same-active')['session']['id'] == sid
    coach.transition('finish-current', sid, coach.required('coach-session-'+sid)['version'],
                     'finish', explicit_end=True)
    blocked = coach.start('next')
    assert blocked['started'] is False
    assert blocked['status'] == 'queued'
    assert coach.legacy.progress()['active_sessions'] == []
    assert coach.start('next') == blocked
    resumed = coach.start('next', accept_outdated=True,
                          expected_plan_etag=blocked['plan_etag'])
    assert resumed['session']['id'] != sid


def test_readiness_plan_version_guard(env):
    _, _, coach = env
    state = coach.lesson_readiness()
    assert state['lesson_ready'] and state['status'] == 'none'
    # A stale client cannot start a new session with a different plan identity.
    try:
        coach.start('stale', expected_plan_etag='invalid')
    except ValueError as exc:
        assert 'Plan version conflict' in str(exc)
    else:
        raise AssertionError('stale plan must be rejected')
    assert coach.legacy.progress()['active_sessions'] == []
