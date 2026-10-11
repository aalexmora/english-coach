from english_coach.teaching import lesson_brief


def test_lesson_brief_prioritizes_observed_difficulty_in_one_source():
    evidence = {
        'fluent': dict(state='observed', independent_total=5, independent_correct=5,
                       assisted_total=0, evidence_ids=['a']),
        'needs_work': dict(state='observed', independent_total=5, independent_correct=1,
                           assisted_total=2, evidence_ids=['b']),
    }
    source = dict(value=dict(id='source', status='active', created_at='2026-10-01',
                             topics=['Planning'], quality=dict(relevance='high'), used_count=0,
                             last_used_at=None, situations=[],
                             exercises=[dict(id='easy', skill_id='fluent', mechanic='roleplay'),
                                        dict(id='target', skill_id='needs_work', mechanic='roleplay')]),
                  version=1)
    chosen = lesson_brief([source], evidence, {'fluent', 'needs_work'})
    assert chosen[0]['id']=='target'
    assert chosen[0]['learner_evidence_ids']==['b']
