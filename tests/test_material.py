import asyncio
from pathlib import Path

import pytest
from saver.store import Store
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from english_coach.coach import Coach
from english_coach.material import MaterialIntake, digest, source_coverage
import json


@pytest.fixture
def coach(tmp_path):
    store = Store(tmp_path/'memory.sqlite', tmp_path/'export')
    c = Coach(MemoryAPI(store, 'owner', 'english', ['english']),
              LegacyEnglishAPI(store, 'owner', ['english']))
    goal = dict(outcome='Discuss delivery decisions at work', minutes=20,
                milestones=['Clarify a decision'],
                skills=[dict(id='clarify', outcome='Ask a clarifying question', pattern_ids=[])])
    c.configure('goal', goal, confirmed=True)
    return c, store


def run(intake, key, text):
    return asyncio.run(intake.submit(key, text))


def test_source_coverage_counts_fragments_across_fields():
    text='A colleague proposed a change. The team discussed the owner and delivery date.'
    assert source_coverage(text, dict(summary='A colleague proposed a change.',
                                      notes=['The team discussed the owner and delivery date.'])) > 60


def test_one_call_curates_without_raw_transcript_or_progress(coach):
    c, store = coach
    phrase = 'Could we clarify the next step?'
    text = phrase + ' The confidential code is ORCHID-999 and should not be retained.'
    class Provider:
        calls = 0
        async def analyze_material(self, snapshot):
            self.calls += 1
            assert snapshot['text'] == text
            return dict(materials=[dict(skill_id='clarify', phrase=phrase,
                                        meaning='Ask for the next action', situation='A generic project meeting',
                                        practice_prompt='Ask a colleague about the next step', origin='quoted')])
    provider = Provider()
    intake = MaterialIntake(c, provider, 2)
    first = run(intake, 'meeting-1', text)
    assert first['saved_count'] == 1 and first['source_excerpt_stored'] is False
    assert run(intake, 'meeting-1', text) == first
    assert provider.calls == 1
    assert run(intake, 'meeting-2', text)['existing_count'] == 1
    assert len(c.documents('coach-material-')) == 1
    assert c.context()['work_material'][0]['phrase'] == phrase
    assert c.context()['skills']['clarify']['independent_total'] == 0
    assert c.legacy.observations() == []
    restarted = Store(store.path, store.export_root)
    resumed = Coach(MemoryAPI(restarted, 'owner', 'english', ['english']),
                    LegacyEnglishAPI(restarted, 'owner', ['english']))
    assert resumed.context()['work_material'][0]['phrase'] == phrase
    files = [store.path, Path(str(store.path) + '-wal')]
    assert all(b'ORCHID-999' not in p.read_bytes() for p in files if p.exists())


@pytest.mark.parametrize('bad', [
    dict(skill_id='missing', phrase='Could we clarify the next step?', origin='quoted'),
    dict(skill_id='clarify', phrase='Contact me at test@example.com', origin='adapted'),
])
def test_invalid_model_material_is_rejected_without_saving(coach, bad):
    c, _ = coach
    class Provider:
        async def analyze_material(self, snapshot):
            return dict(materials=[dict(bad, meaning='Meaning', situation='A generic meeting',
                                        practice_prompt='Ask about a work decision')])
    with pytest.raises(ValueError, match='Invalid material result'):
        run(MaterialIntake(c, Provider(), 2), 'bad', 'Could we clarify the next step?')
    assert c.documents('coach-material-') == []
    assert c.documents('coach-intake-') == []


def test_provider_failure_is_sanitized_and_retryable(coach):
    c, _ = coach
    class Provider:
        async def analyze_material(self, snapshot):
            raise RuntimeError('The meeting contained a private sentence')
    intake = MaterialIntake(c, Provider(), 2)
    with pytest.raises(RuntimeError, match='Material provider RuntimeError') as exc:
        run(intake, 'retry', 'Could we clarify the next step?')
    assert 'private sentence' not in str(exc.value)
    assert c.documents('coach-material-') == []


def test_punctuation_changed_quote_is_labeled_adapted(coach):
    c, _ = coach
    text='A teammate asked who would tell the customer and whether the date had changed.'
    class Provider:
        async def analyze_material(self, snapshot):
            return dict(materials=[dict(skill_id='clarify',phrase='who would tell the customer?',
                                        meaning='Ask who owns communication',
                                        situation='A changed delivery plan',
                                        practice_prompt='Ask about the owner',origin='quoted')])
    result=run(MaterialIntake(c,Provider(),2),'punctuation',text)
    assert result['saved'][0]['origin']=='adapted'
    assert c.context()['work_material'][0]['origin']=='adapted'


def test_paraphrase_mislabeled_as_quote_is_saved_as_adapted(coach):
    c, _ = coach
    text='A teammate asked who would tell the customer and whether the date had changed.'
    class Provider:
        async def analyze_material(self, snapshot):
            return dict(materials=[dict(skill_id='clarify',
                                        phrase='Who is responsible for updating the client?',
                                        meaning='Clarify the communication owner',
                                        situation='A delivery change',
                                        practice_prompt='Ask about the owner in another project',
                                        origin='quoted')])
    result=run(MaterialIntake(c,Provider(),2),'paraphrase',text)
    assert result['saved'][0]['origin']=='adapted'
    assert c.context()['work_material'][0]['origin']=='adapted'


def test_resubmitted_legacy_cards_gain_analysis_without_duplication(coach):
    c, _ = coach
    phrase='Could we clarify who owns the follow-up?'
    text=(phrase+' The team then discussed a delayed release, a new date, '
          'and who would update the client about the decision.')
    key='legacy-meeting'
    source_digest=digest(json.dumps([text,''],ensure_ascii=False))
    receipt_key='coach-intake-'+digest(key)
    card_key='coach-material-'+digest(json.dumps(['clarify',phrase.casefold()],ensure_ascii=False))
    old_result=dict(saved=[dict(id=card_key,skill_id='clarify',phrase=phrase,origin='quoted')],
                    saved_count=1,existing_count=0,source_excerpt_stored=False)
    def legacy_save():
        c.memory.put(card_key,dict(id=card_key,skill_id='clarify',phrase=phrase,
                                   origin='quoted',source_digest=source_digest,
                                   created_at='2026-10-01',status='active'),0)
        c.memory.put(receipt_key,dict(source_digest=source_digest,result=old_result),0)
        return old_result
    assert c.memory.request(key,dict(op='submit_english_material',source_digest=source_digest),
                            legacy_save)==old_result
    assert c.documents('coach-source-')==[]
    class Provider:
        calls=0
        async def analyze_material(self,snapshot):
            self.calls+=1
            return dict(summary='The team clarifies ownership of a delayed release.',
                        topics=['Delivery planning'],
                        situations=[dict(skill_id='clarify',topic='Delivery planning',
                                         setting='A project meeting about a delayed release',
                                         communicative_goal='Confirm who updates the client',
                                         colleague_move='Asks for the owner of the follow-up',
                                         confidence='high')],
                        materials=[dict(skill_id='clarify',phrase=phrase,
                                        meaning='Clarify who owns the next action',
                                        situation='A delivery planning meeting',
                                        practice_prompt='Ask who will update the client',origin='quoted')],
                        exercises=[dict(skill_id='clarify',situation='A different delayed handoff',
                                        first_prompt='No one has agreed who will contact the client. Respond.',
                                        response_goal='Find the communication owner',
                                        success_criterion='Ask who will tell the client and confirm the answer',
                                        transfer_prompt='A new team has no owner for a decision. Respond.',
                                        mechanic='roleplay',why='Diagnose an agreed clarification skill')])
    provider=Provider()
    intake=MaterialIntake(c,provider,2)
    upgraded=run(intake,key,text)
    assert upgraded['source_upgraded'] and upgraded['existing_count']==1
    assert upgraded['saved_count']==0 and upgraded['exercise_count']==1
    assert upgraded['summary'] and upgraded['situation_count']==1
    assert c.required(receipt_key)['version']==2
    assert len(c.context()['work_context'])==1 and len(c.context()['lesson_brief'])==1
    assert c.context()['work_material'][0]['id']==card_key
    assert run(intake,key,text)==upgraded and provider.calls==1
    assert run(intake,'new-key',text)['source_existing'] and provider.calls==1
    with pytest.raises(ValueError,match='different meeting text'):
        run(intake,key,text+' Another event happened.')


def test_dialogue_analysis_builds_reusable_context_and_archives_it(coach):
    c, store = coach
    text = ('The team discussed a delayed release and who should notify the client. '
            'Could we clarify who owns the follow-up? A colleague proposed a new date. '
            'Private reference ORCHID-999 appeared later in the conversation.')
    phrase = 'Could we clarify who owns the follow-up?'
    class Provider:
        calls = 0
        async def analyze_material(self, snapshot):
            self.calls += 1
            assert snapshot['skills'][0]['evidence']['state'] == 'insufficient_data'
            return dict(summary='The team coordinates a delayed delivery and follow-up.',
                        topics=['Delivery planning', 'Ownership'],
                        quality=dict(relevance='high', clarity='high', attribution='unavailable',
                                     novelty='new_topic', repeatability='reusable',
                                     reason='The decision and next action are explicit'),
                        situations=[dict(skill_id='clarify', topic='Delivery planning',
                                         setting='A project review meeting',
                                         communicative_goal='Confirm who owns the next action',
                                         colleague_move='Asks for an owner before agreeing a date',
                                         reasoning_move='Resolve ownership before committing to the date',
                                         language_register='neutral',
                                         confidence='high')],
                        materials=[dict(skill_id='clarify', phrase=phrase, meaning='Clarify responsibility',
                                        situation='A meeting about a delayed release',
                                        practice_prompt='Ask who will inform a stakeholder', origin='quoted')],
                        exercises=[dict(skill_id='clarify', situation='A delayed project handoff',
                                        first_prompt='The client expects news, but no one has agreed who will call. Respond.',
                                        response_goal='Find the owner',
                                        success_criterion='Ask who will contact the client and confirm the answer',
                                        transfer_prompt='A different team has no owner for a decision. Respond.',
                                        mechanic='roleplay', why='Diagnose an agreed clarification skill')])
    provider = Provider()
    intake = MaterialIntake(c, provider, 2)
    result = run(intake, 'dialogue', text)
    assert result['exercise_count'] == 1
    assert c.context()['work_context'][0]['topics'] == ['Delivery planning', 'Ownership']
    assert c.context()['work_context'][0]['situations'][0]['reasoning_move'].startswith('Resolve')
    assert c.context()['work_context'][0]['quality']['novelty']=='new_topic'
    exercise = c.context()['lesson_brief'][0]
    assert exercise['source_id'] == result['source_id']
    assert exercise['need'] == 'diagnostic' and exercise['method']['source']
    assert result['source_id'] == run(intake, 'same-source-different-key', text)['source_id']
    assert provider.calls == 1
    resumed = Coach(MemoryAPI(Store(store.path, store.export_root), 'owner', 'english', ['english']),
                    LegacyEnglishAPI(Store(store.path, store.export_root), 'owner', ['english']))
    assert resumed.context()['lesson_brief'][0]['id'] == exercise['id']
    assert all(b'ORCHID-999' not in p.read_bytes()
               for p in (store.path, Path(str(store.path) + '-wal')) if p.exists())
    version = c.context()['work_context'][0]['version']
    intake.archive('archive-dialogue', result['source_id'], version)
    assert c.context()['work_context'] == []
    assert c.context()['lesson_brief'] == []
    assert c.context()['work_material'] == []


def test_full_dialogue_or_unattributed_speaker_is_not_persisted(coach):
    c, _ = coach
    text = 'We discussed a delivery delay and then agreed to call the customer tomorrow.'
    class Provider:
        def __init__(self, result): self.result = result
        async def analyze_material(self, snapshot): return self.result
    for result in [dict(summary=text),
                   dict(situations=[dict(skill_id='clarify', topic='Delivery',
                                          setting='A team meeting', communicative_goal='Clarify a decision',
                                          colleague_move='Asks a question', speaker_role='Product director',
                                          confidence='high')])]:
        with pytest.raises(ValueError, match='Invalid material result'):
            run(MaterialIntake(c, Provider(result), 2), 'invalid-'+str(len(c.documents('coach-intake-'))), text)
    assert c.documents('coach-source-') == []


def test_reviewed_transcription_fragment_is_rejected(coach):
    c,_=coach
    class Provider:
        async def analyze_material(self,snapshot):
            return dict(materials=[dict(skill_id='clarify',phrase='We wanted it [time] ago.',meaning='Clarify timing',situation='A meeting',practice_prompt='Ask about timing',origin='adapted',language_quality='reviewed',meaning_preserved=True)])
    with pytest.raises(ValueError,match='Invalid material result'):
        run(MaterialIntake(c,Provider(),2),'broken-phrase','They discussed timing but the transcript contains an unclear fragment.')
    assert c.documents('coach-material-')==[]
