"""One-call dialogue analysis; only selected fragments and findings persist."""
import asyncio
from hashlib import sha256
import json
import re

from .coach import now
from .models import MaterialExtraction, MECHANICS
from . import policies


def digest(value):
    return sha256(value.encode('utf-8')).hexdigest()


def normalized(value):
    return ' '.join(value.casefold().split())


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def source_coverage(text, result):
    """Count source characters reused verbatim across all saved fields."""
    original = normalized(text)
    ranges = []
    for value in strings(result):
        excerpt = normalized(value)
        if len(excerpt) < 20:
            continue
        start = original.find(excerpt)
        if start >= 0:
            ranges.append((start, start + len(excerpt)))
    if not ranges:
        return 0
    ranges.sort()
    total = 0
    left, right = ranges[0]
    for start, end in ranges[1:]:
        if start > right:
            total += right - left
            left, right = start, end
        else:
            right = max(right, end)
    return total + right - left


class MaterialIntake:
    def __init__(self, coach, provider, timeout):
        self.coach, self.provider, self.timeout = coach, provider, timeout

    async def submit(self, idempotency_key, text, context=''):
        if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 128:
            raise ValueError('Invalid idempotency key')
        if not isinstance(text, str) or not 20 <= len(text.strip()) <= 20000:
            raise ValueError('Meeting text must contain 20..20000 characters')
        if not isinstance(context, str) or len(context) > 500:
            raise ValueError('Context must contain at most 500 characters')

        memory = self.coach.memory
        source_digest = digest(json.dumps([text, context], ensure_ascii=False))
        source_key = 'coach-source-' + source_digest
        receipt_key = 'coach-intake-' + digest(idempotency_key)
        prior = memory.get(receipt_key)
        if prior:
            if prior['value']['source_digest'] != source_digest:
                raise ValueError('Idempotency key reused with different meeting text')
            if prior['value']['result'].get('source_id'):
                return prior['value']['result']
        # A 0.3.0 receipt contains only cards. The re-sent text permits one
        # versioned enrichment without keeping a second copy of the original.
        upgrade = prior is not None
        request_key = digest('coach-material-upgrade:' + idempotency_key) if upgrade else idempotency_key
        request_payload = dict(op='submit_english_material_upgrade' if upgrade else 'submit_english_material',
                               source_digest=source_digest)
        existing_source = memory.get(source_key)
        if existing_source:
            result = dict(saved=[], saved_count=0,
                          existing_count=len(existing_source['value'].get('material_ids', [])),
                          source_id=source_key, source_existing=True,
                          source_upgraded=upgrade,
                          exercise_count=len(existing_source['value'].get('exercises', [])),
                          situation_count=len(existing_source['value'].get('situations', [])),
                          summary=existing_source['value'].get('summary', ''),
                          topics=existing_source['value'].get('topics', []),
                          source_excerpt_stored=False)
            def receipt():
                memory.put(receipt_key, dict(source_digest=source_digest, result=result),
                           prior['version'] if prior else 0)
                return result
            return memory.request(request_key, request_payload, receipt)

        profile = self.coach.profile()
        policy=policies.selection(profile)
        goal = profile['value']['goal']
        evidence = self.coach.skill_evidence(goal, self.coach.legacy.observations())
        previous = [dict(summary=d['value'].get('summary', ''),
                         topics=d['value'].get('topics', []))
                    for d in self.coach.documents('coach-source-')
                    if d['value'].get('status') == 'active'][-5:]
        snapshot = dict(teaching_policy=policy,teaching_contract=policies.contract(policy),learner_id=self.coach.learner_id,text=text, context=context, goal=goal['outcome'],
                        skills=[dict(id=s['id'], outcome=s['outcome'],
                                     evidence=evidence[s['id']]) for s in goal['skills']],
                        previous_context=previous)
        try:
            raw = await asyncio.wait_for(self.provider.analyze_material(snapshot), timeout=self.timeout)
        except Exception as exc:
            # Provider errors can contain request content. Never echo them into MCP responses.
            raise RuntimeError('Material provider ' + type(exc).__name__) from None
        try:
            extracted = MaterialExtraction.model_validate(raw)
            known_skills = {s['id'] for s in goal['skills']}
            for item in extracted.materials:
                if item.language_quality=='reviewed' and re.search(r'\[[^]]*\]|\b(?:inaudible|unintelligible)\b',item.phrase,re.I):
                    raise ValueError('Unresolved transcription cannot be a reviewed model phrase')
                if item.skill_id not in known_skills:
                    raise ValueError('Unknown skill')
                if item.origin == 'quoted' and normalized(item.phrase) not in normalized(text):
                    # Model paraphrases sometimes arrive mislabeled as quotes.
                    # Preserve useful teaching language without claiming verbatim provenance.
                    item.origin = 'adapted'
                if re.search(r'https?://|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', item.phrase):
                    raise ValueError('Contact information in phrase')
            for item in [*extracted.situations, *extracted.exercises]:
                if item.skill_id not in known_skills:
                    raise ValueError('Unknown skill')
            for situation in extracted.situations:
                if (situation.speaker_role and
                        normalized(situation.speaker_role) not in normalized(text + ' ' + context)):
                    raise ValueError('Unattributed speaker role')
            for exercise in extracted.exercises:
                policies.check_activity(policy,exercise.mechanic,exercise.first_prompt+' '+exercise.transfer_prompt+' '+exercise.situation,exercise.activity)
                if extracted.quality and extracted.quality.language_quality=='reviewed' and re.search(r'\[[^]]*\]|\b(?:inaudible|unintelligible)\b',exercise.first_prompt+' '+exercise.transfer_prompt,re.I):
                    raise ValueError('Unresolved transcription in reviewed exercise')
                if exercise.mechanic not in MECHANICS or normalized(exercise.first_prompt) == normalized(exercise.transfer_prompt):
                    raise ValueError('Invalid exercise')
                if any(normalized(item.phrase) in normalized(exercise.first_prompt)
                       for item in extracted.materials if item.skill_id == exercise.skill_id):
                    raise ValueError('First prompt reveals an answer')
            persisted = extracted.model_dump(mode='json')
            source = normalized(text.strip())
            if any(source in normalized(value) for value in strings(persisted)):
                raise ValueError('Full transcript in model result')
            old_fragments = [d['value'] for d in self.coach.documents('coach-material-')
                             if d['value'].get('source_digest') == source_digest]
            if source_coverage(text, [persisted, old_fragments]) > max(60, min(800, len(text.strip()) * .5)):
                raise ValueError('Too much quoted source')
            if any(re.search(r'https?://|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', value)
                   for value in strings(persisted)):
                raise ValueError('Contact information in result')
        except (ValueError, TypeError, KeyError):
            raise ValueError('Invalid material result') from None

        def save():
            if self.coach.profile()['version'] != profile['version']:
                raise ValueError('Profile changed during analysis; retry with a new key')
            saved, existing, seen = [], 0, set()
            all_card_ids = [d['id'] for d in old_fragments if d.get('status') == 'active']
            for item in extracted.materials:
                card = item.model_dump(mode='json')
                key = 'coach-material-' + digest(json.dumps(
                    [item.skill_id, normalized(item.phrase)], ensure_ascii=False))
                if key in seen:
                    continue
                seen.add(key)
                if key not in all_card_ids:
                    all_card_ids.append(key)
                if memory.get(key):
                    existing += 1
                    continue
                value = dict(card, id=key, source='meeting_text', source_digest=source_digest,
                             teaching_eligible=item.language_quality=='reviewed' and item.meaning_preserved is True,
                             created_at=now(), status='active')
                memory.put(key, value, 0)
                saved.append(dict(id=key, skill_id=item.skill_id, phrase=item.phrase,
                                  origin=item.origin))
            exercises = []
            for item in extracted.exercises:
                exercise = item.model_dump(mode='json')
                exercise['teaching_eligible'] = bool(extracted.quality and extracted.quality.language_quality=='reviewed' and extracted.quality.meaning_preserved is True)
                exercise['id'] = 'exercise-' + digest(source_digest + item.first_prompt)
                exercises.append(exercise)
            memory.put(source_key, dict(
                teaching_policy=policy,id=source_key, source_digest=source_digest, created_at=now(),
                status='active', summary=extracted.summary, topics=extracted.topics,
                quality=extracted.quality.model_dump(mode='json') if extracted.quality else None,
                situations=[item.model_dump(mode='json') for item in extracted.situations],
                exercises=exercises, material_ids=all_card_ids,
                used_count=0, last_used_at=None), 0)
            result = dict(saved=saved, saved_count=len(saved), existing_count=existing,
                          source_id=source_key, source_existing=False,
                          source_upgraded=upgrade, exercise_count=len(extracted.exercises),
                          situation_count=len(extracted.situations),
                          summary=extracted.summary, topics=extracted.topics,
                          source_excerpt_stored=False)
            memory.put(receipt_key, dict(source_digest=source_digest, result=result),
                       prior['version'] if prior else 0)
            return result

        return memory.request(request_key, request_payload, save)

    def archive(self, idempotency_key, source_id, expected_version):
        if not source_id.startswith('coach-source-'):
            raise ValueError('Expected work source ID')
        def save():
            doc = self.coach.required(source_id)
            if doc['version'] != expected_version:
                raise ValueError('Version conflict')
            value = dict(doc['value'], status='archived')
            return self.coach.memory.put(source_id, value, doc['version'])
        return self.coach.memory.request(idempotency_key,
                                         dict(op='archive_english_material', source_id=source_id,
                                              expected_version=expected_version), save)
