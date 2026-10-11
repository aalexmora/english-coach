"""Select grounded work exercises and expose the evidence behind each method."""
METHODS = {
    'conversation': dict(purpose='Develop a meaningful conversation, with brief correction and natural later reuse',
                         evidence='Teaching contract; personal benefit requires observation in a real lesson.',
                         source=None,verify='Express a related thought independently in a later conversation.'),
    'roleplay': dict(
        purpose='Practice a meaningful exchange with follow-up questions',
        evidence='Interaction supports second-language development; outcomes depend on task design.',
        source='https://doi.org/10.1017/S0261444818000125',
        verify='Reach the communicative goal in a new exchange without a supplied script.'),
    'contrast': dict(
        purpose='Notice and repair a consequential language choice',
        evidence='Classroom meta-analysis found durable benefits from oral corrective feedback.',
        source='https://doi.org/10.1017/S0272263109990520',
        verify='Produce a full repaired answer, then use it in another situation.'),
    'retrieval': dict(
        purpose='Retrieve a useful expression before seeing a model',
        evidence='Retrieval outperformed imitation for spoken foreign vocabulary in an experiment.',
        source='https://doi.org/10.3758/s13423-013-0450-z',
        verify='Produce the intended move independently after a delay.'),
    'task_repetition': dict(
        purpose='Reformulate the same task, then test a related new task',
        evidence='Task repetition has improved fluency; retention and transfer need separate checks.',
        source='https://doi.org/10.1017/S0272263124000251',
        verify='Solve a changed task without the coached wording.'),
    'rapid_retrieval': dict(
        purpose='Retrieve short answers across varied situations',
        evidence='Retrieval benefits spoken vocabulary; transfer to whole workplace dialogue is a hypothesis.',
        source='https://doi.org/10.3758/s13423-013-0450-z',
        verify='Answer a new situation without an answer cue.'),
    'guided_transfer': dict(
        purpose='Move from a supported answer to free speech',
        evidence='Coach design combining feedback and changed-task verification; personal benefit is unproven.',
        source='https://doi.org/10.1017/S0272263109990520',
        verify='Produce a free answer in a different situation after a delay.'),
}
for method in METHODS.values():
    method['version'] = 1
    method['limit'] = ('Evidence supports the technique in studied tasks; personal benefit and '
                       'transfer to unscripted workplace speech require observation.')


def skill_gap_score(evidence):
    if evidence['state'] == 'insufficient_data':
        return 3
    total = evidence['independent_total']
    if total and evidence['independent_correct'] / total < .7:
        return 2
    if evidence['assisted_total']:
        return 1
    return 0


def rank_sources(sources, skill_evidence, relevant_skills, limit=6):
    candidates = []
    for doc in sources:
        value = doc['value']
        if value.get('status') != 'active':
            continue
        situations = [s for s in value.get('situations', []) if s['skill_id'] in relevant_skills]
        exercises = [e for e in value.get('exercises', []) if e['skill_id'] in relevant_skills]
        if not situations and not exercises:
            continue
        gap = max(skill_gap_score(skill_evidence[s['skill_id']]) for s in situations + exercises)
        quality = value.get('quality') or {}
        score = gap * 3 + (2 if quality.get('relevance') == 'high' else 0)
        score += 2 if not value.get('used_count') else 0
        candidates.append((score, value.get('last_used_at') or '', value['created_at'],
                           dict(value, version=doc['version'])))
    candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
    return [row[3] for row in candidates[:limit]]


def lesson_brief(sources, skill_evidence, relevant_skills, limit=3, reviewed_only=False):
    chosen = []
    for source in rank_sources(sources, skill_evidence, relevant_skills, limit=12):
        exercises = [e for e in source.get('exercises', []) if e['skill_id'] in relevant_skills and (not reviewed_only or e.get('teaching_eligible'))]
        exercises.sort(key=lambda e: -skill_gap_score(skill_evidence[e['skill_id']]))
        for exercise in exercises:
            skill = skill_evidence[exercise['skill_id']]
            chosen.append(dict(**exercise, source_id=source['id'],
                               source_topic=source.get('topics', [])[:2],
                               learner_evidence_ids=skill['evidence_ids'][-5:],
                               need='diagnostic' if skill['state'] == 'insufficient_data'
                               else 'practice_and_verify',
                               method=METHODS[exercise['mechanic']]))
            break
        if len(chosen) >= limit:
            break
    return chosen


def work_context(sources, skill_evidence, relevant_skills):
    return [dict(id=s['id'], version=s['version'], summary=s.get('summary', ''), topics=s.get('topics', []),
                 quality=s.get('quality'), situations=[item for item in s.get('situations', [])
                                                       if item['skill_id'] in relevant_skills],
                 used_count=s.get('used_count', 0), last_used_at=s.get('last_used_at'))
            for s in rank_sources(sources, skill_evidence, relevant_skills)]


def work_patterns(sources, skill_evidence, relevant_skills):
    """Counts describe submitted samples, not the learner's whole workplace."""
    groups = {}
    for source in rank_sources(sources, skill_evidence, relevant_skills, limit=100):
        for topic in source.get('topics', []):
            key = topic.casefold().strip()
            if key:
                item = groups.setdefault(key, dict(topic=topic, source_ids=[],
                                                   confidence='single_sample'))
                if source['id'] not in item['source_ids']:
                    item['source_ids'].append(source['id'])
                    if len(item['source_ids']) > 1:
                        item['confidence'] = 'multiple_submitted_samples'
    return sorted(groups.values(), key=lambda row: (-len(row['source_ids']), row['topic']))[:12]
