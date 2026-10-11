from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, AwareDatetime

Mechanic = Literal['roleplay', 'contrast', 'retrieval', 'task_repetition', 'rapid_retrieval', 'guided_transfer', 'conversation']
PolicyId = Literal['foundation', 'conversation']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Skill(Strict):
    id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,59}$')
    outcome: str = Field(min_length=1, max_length=500)
    pattern_ids: list[str] = Field(default_factory=list, max_length=30)

class Goal(Strict):
    outcome: str = Field(min_length=1, max_length=500)
    minutes: int = Field(ge=5, le=120)
    milestones: list[str] = Field(min_length=1, max_length=12)
    skills: list[Skill] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def unique(self):
        if len({s.id for s in self.skills}) != len(self.skills):
            raise ValueError('Duplicate skill')
        return self

class PlanItem(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    skill_id: str
    task: str = Field(min_length=1, max_length=1000)
    mechanic: Mechanic
    mechanic_version: int = Field(ge=1)
    status: Literal['pending', 'done', 'carried'] = 'pending'
    minutes: int = Field(default=5, ge=1, le=120)
    activity: Literal['communicative','grammar_drill'] = 'communicative'

class Feedback(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    kind: Literal['boredom', 'change_exercise', 'preference', 'other']
    text: str = Field(min_length=1, max_length=1000)
    mechanic: Mechanic | None = None

class Discovery(Strict):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')
    scope: Literal['personal', 'general'] = 'personal'
    skill_id: str
    cue: str = Field(min_length=1, max_length=1000)
    context: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    reuse_trigger: str = Field(min_length=1, max_length=500)
    explicit_save: bool = False

class TeachingTurn(Strict):
    attempt_id: str | None = None
    praises_correctness: bool = False
    independent_check: bool = False
    reveals_answer: bool = False
    ends_lesson: bool = False
    learner_requested_end: bool = False
    meaning_preserved: Literal['yes','no','unknown'] = 'unknown'
    question_count: int = Field(default=1,ge=0,le=10)
    claims_independent: bool = False
    claims_correction: bool = False
    learner_answer: str = Field(default='', max_length=2000)
    proposed_answer: str = Field(default='', max_length=2000)
    unfinished_answer: bool = False
    activity: Literal['dialogue','grammar_drill'] = 'dialogue'
    requires_repetition: bool = False
    correction_count: int = Field(default=0, ge=0, le=20)
    correction_timing: Literal['after_turn','interrupt'] = 'after_turn'
    meaning_blocked: bool = False


class WorkMaterial(Strict):
    language_quality: Literal['reviewed','uncertain'] = 'uncertain'
    meaning_preserved: bool | None = None
    quality_note: str = Field(default='',max_length=300)
    skill_id: str
    phrase: str = Field(min_length=3, max_length=300)
    meaning: str = Field(min_length=3, max_length=500)
    situation: str = Field(min_length=3, max_length=500)
    practice_prompt: str = Field(min_length=3, max_length=500)
    origin: Literal['quoted', 'adapted']

class WorkSituation(Strict):
    skill_id: str
    topic: str = Field(min_length=3, max_length=100)
    setting: str = Field(min_length=3, max_length=200)
    communicative_goal: str = Field(min_length=3, max_length=200)
    colleague_move: str = Field(min_length=3, max_length=200)
    reasoning_move: str | None = Field(default=None, max_length=200)
    language_register: Literal['formal', 'neutral', 'informal', 'unclear'] = 'unclear'
    speaker_role: str | None = Field(default=None, max_length=80)
    confidence: Literal['high', 'medium', 'low']

class MaterialQuality(Strict):
    language_quality: Literal['reviewed','uncertain'] = 'uncertain'
    meaning_preserved: bool | None = None
    relevance: Literal['high', 'medium', 'low']
    clarity: Literal['high', 'medium', 'low']
    attribution: Literal['explicit', 'uncertain', 'unavailable']
    novelty: Literal['new_topic', 'seen_before', 'unknown'] = 'unknown'
    repeatability: Literal['reusable', 'specific_to_this_meeting', 'uncertain'] = 'uncertain'
    reason: str = Field(min_length=3, max_length=300)

class WorkExercise(Strict):
    skill_id: str
    situation: str = Field(min_length=3, max_length=300)
    first_prompt: str = Field(min_length=3, max_length=300)
    response_goal: str = Field(min_length=3, max_length=200)
    success_criterion: str = Field(min_length=3, max_length=300)
    transfer_prompt: str = Field(min_length=3, max_length=300)
    mechanic: Mechanic
    why: str = Field(min_length=3, max_length=300)
    activity: Literal['communicative','grammar_drill'] = 'communicative'

class MaterialExtraction(Strict):
    summary: str = Field(default='', max_length=500)
    topics: list[str] = Field(default_factory=list, max_length=8)
    situations: list[WorkSituation] = Field(default_factory=list, max_length=8)
    quality: MaterialQuality | None = None
    materials: list[WorkMaterial] = Field(default_factory=list, max_length=8)
    exercises: list[WorkExercise] = Field(default_factory=list, max_length=4)

class Finding(Strict):
    skill_id: str
    hypothesis: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(max_length=50)
    uncertainty: Literal['high', 'medium', 'low']
    verify: str = Field(min_length=1, max_length=500)

class ChangeBase(Strict):
    why: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(max_length=50)
    uncertainty: Literal['high', 'medium', 'low']
    verify: str = Field(min_length=1, max_length=500)


class PlanChange(ChangeBase):
    kind: Literal['plan']
    plan: list[PlanItem] = Field(min_length=1, max_length=12)


class GoalChange(ChangeBase):
    kind: Literal['goal']
    goal: Goal


class LoadChange(ChangeBase):
    kind: Literal['load']
    minutes: int = Field(ge=5, le=120)


class PreferenceChange(ChangeBase):
    kind: Literal['preference']
    mechanic: Mechanic


Change = Annotated[PlanChange | GoalChange | LoadChange | PreferenceChange,
                   Field(discriminator='kind')]

class CurriculumDecision(Strict):
    document_version: int = Field(ge=1)
    stage_id: str = Field(min_length=1, max_length=100)
    source_ids: list[str] = Field(min_length=1, max_length=20)
    rationale: str = Field(min_length=1, max_length=1500)
    next_check: str = Field(min_length=1, max_length=1000)


class Review(Strict):
    curriculum: CurriculumDecision | None = None
    findings: list[Finding] = Field(max_length=20)
    changes: list[Change] = Field(max_length=10)

class Settings(Strict):
    preferred_mechanic: Mechanic = 'roleplay'
    instructions: str = Field(default='', max_length=1500)
    prompt_style: Literal['brief', 'guided'] = 'brief'
    vocabulary_level: Literal['basic'] = 'basic'
    new_phrases_per_lesson: int = Field(default=1, ge=0, le=1)
    homework_minutes: int = Field(default=12, ge=10, le=15)

class ConversationSettings(Strict):
    preferred_mechanic: Mechanic = 'conversation'
    instructions: str = Field(default='', max_length=1500)
    prompt_style: Literal['brief','guided'] = 'brief'
    vocabulary_level: Literal['natural'] = 'natural'
    new_phrases_per_lesson: int = Field(default=2, ge=0, le=3)
    homework_minutes: int = Field(default=0, ge=0, le=15)
    correction_intensity: Literal['light','balanced'] = 'light'

class ConversationTopic(Strict):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')
    title: str = Field(min_length=1,max_length=100)
    communicative_goal: str = Field(min_length=1,max_length=300)
    questions: list[str] = Field(min_length=2,max_length=4)
    criterion: str = Field(min_length=1,max_length=300)
    correctness_focus: str = Field(min_length=1,max_length=300)
    status: Literal['active','skipped'] = 'active'

    @model_validator(mode='after')
    def short_questions(self):
        if any(not 1<=len(q)<=300 or q.count('?')>1 for q in self.questions):
            raise ValueError('Each topic prompt asks one short open question')
        return self

class ConversationOnboarding(Strict):
    outcome: str = Field(min_length=1,max_length=500)
    minutes: int = Field(ge=5,le=120)
    interests: list[str] = Field(min_length=1,max_length=8)
    situations: list[str] = Field(min_length=1,max_length=8)
    comfortable_topic_ids: list[str] = Field(min_length=2,max_length=3)
    reported_level: str | None = Field(default=None,max_length=100)
    level_source: Literal['learner_statement','administrator_statement'] = 'learner_statement'
    correction_intensity: Literal['light','balanced'] = 'light'
    preparation_minutes: int = Field(default=0,ge=0,le=15)

    @model_validator(mode='after')
    def bounded_preferences(self):
        if any(not 1<=len(x)<=200 for x in self.interests+self.situations):
            raise ValueError('Use short interests and situations')
        if len(set(self.comfortable_topic_ids))!=len(self.comfortable_topic_ids):
            raise ValueError('Choose different comfortable topics')
        return self

class ConversationCorrection(Strict):
    kind: Literal['actual_error','natural_alternative']
    focus_id: str = Field(pattern=r'^[a-z][a-z0-9_]{0,59}$')
    corrected_text: str = Field(min_length=1,max_length=2000)
    reason: str = Field(min_length=1,max_length=500)
    meaning_preserved: bool
    occurred_at: AwareDatetime = Field(strict=False)

class ConversationAnnotation(Strict):
    attempt_key: str = Field(min_length=1,max_length=128)
    demonstrated: list[Literal['maintains_dialogue','develops_idea','asks_clarification','paraphrases','focus_accuracy','delayed_reuse']] = Field(default_factory=list,max_length=6)
    correction: ConversationCorrection | None = None
    reused_from: str | None = Field(default=None,max_length=120)

    @model_validator(mode='after')
    def unique_dimensions(self):
        if len(set(self.demonstrated))!=len(self.demonstrated):
            raise ValueError('Duplicate demonstrated dimension')
        return self

class HomeworkAnswer(Strict):
    item_id: str
    text: str = Field(min_length=1, max_length=2000)
    assistance: Literal['independent', 'hint', 'immediate_repeat'] = 'independent'
    meaning: Literal['preserved', 'changed', 'unclear'] = 'unclear'
    grammar: Literal['correct', 'incorrect', 'unclear'] = 'unclear'
    lexis: Literal['acceptable', 'needs_help', 'unclear'] = 'unclear'
    reason: str = Field(default='', max_length=500)
    acceptable_alternative: bool = False


MECHANICS = {
    'conversation': {1: dict(name='Conversation', instructions='Discuss a planned or learner-chosen topic. Let the learner finish, briefly correct one consequential error and continue the meaning-focused conversation. No compulsory repair/reproduction loop; invite natural independent reuse later.')},
    'roleplay': {1: dict(name='Role play', instructions='Negotiate a concrete outcome; vary roles, ask follow-up questions.')},
    'contrast': {1: dict(name='Contrast and repair', instructions='Compare two replies, explain the difference, repair an error in a fresh context.')},
    'retrieval': {1: dict(name='Cold retrieval', instructions='Ask for an unprimed answer in a new context; reveal a cue only after the first attempt.')},
    'task_repetition': {1: dict(name='Retell and transfer', instructions='Role-play a concrete task. Buffer errors, coach at most two, then ask for a newly constructed answer to the same task. This coached retry is not independent transfer. Later change the audience or situation and check unprimed reuse.')},
    'rapid_retrieval': {1: dict(name='Short spoken retrieval', instructions='Give one short situation at a time, without naming the grammar. Use up to three targets from the retrieval opening. Wait for each answer; speed is not measured and hesitation is not an error.')},
    'guided_transfer': {1: dict(name='From support to free speech', instructions='Start with a constrained situation, then a minimal cue if needed, then an unprimed new situation. Repair through hints, require a full learner reproduction, and verify delayed free use. Never treat an imitation as independent.')},
}
