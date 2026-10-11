"""MCP registration in the host process. Identity is obtained on every request."""
from typing import Any, Callable
from .models import Goal, Settings, ConversationSettings, PolicyId, Feedback, Discovery, TeachingTurn, HomeworkAnswer, ConversationOnboarding, ConversationTopic, ConversationAnnotation
from .speaking import Speaking
from .material import MaterialIntake
from .methodologist import from_env


def register(mcp, factory: Callable, read, write, Attempt):
    def resolve(learner_id):
        # The host authorizes selection before constructing both public APIs.
        return factory() if learner_id is None else factory(learner_id)

    @mcp.tool(annotations=read)
    def get_english_admin_view(section:str='overview',days:int=14,start:str|None=None,end:str|None=None,query:str='',status:str='',mode:str='',limit:int=20,offset:int=0,learner_id:str|None=None) -> dict[str,Any]:
        """Read full paginated admin projections with all matching aggregates, Moscow date boundaries, source versions and coverage. Named sections: overview/program/progress/vocabulary/lessons/methodologist/materials/settings. Atomic host snapshot; never launches a model, changes lexical exposure or fabricates learning history."""
        from .admin import AdminRead
        return AdminRead(resolve(learner_id)).read(section,days,start,end,query,status,mode,limit,offset)

    @mcp.tool(annotations=read)
    def get_english_conversation(session_id:str|None=None,limit:int=20,offset:int=0,learner_id:str|None=None) -> dict[str,Any]:
        """Read onboarding, provisional/agreed communicative route, editable topics, evidence-linked original replies and corrections, progress dimensions and a frozen lesson summary. Initial read proposes topics; ask goal, interests, situations, minutes and correction preferences one question at a time. No inferred proficiency or agreed workload. Text conversation only; no audio/fluency/CEFR measurements."""
        from .conversation import Conversation
        return Conversation(resolve(learner_id)).get(session_id,limit,offset)

    @mcp.tool(annotations=write)
    def onboard_english_conversation(idempotency_key:str,data:ConversationOnboarding,expected_version:int=0,learner_confirmed:bool=False,topics:list[ConversationTopic]|None=None,learner_id:str|None=None) -> dict[str,Any]:
        """After explicit learner agreement, save their goal, minutes, interests, situations and correction preferences. Choose two or three comfortable topic IDs plus the free option. Starts a provisional conversational route; new communicative pattern labels have no learner evidence. reported_level is a statement, never assessed CEFR. Does not start or finish a lesson or overwrite an established profile. Then use start_coach_session and begin_item."""
        from .conversation import Conversation
        return Conversation(resolve(learner_id)).onboard(idempotency_key,expected_version,data.model_dump(mode='json'),learner_confirmed,
                                                       [t.model_dump(mode='json') for t in topics] if topics is not None else None)

    @mcp.tool(annotations=write)
    def set_english_conversation_topics(idempotency_key:str,expected_version:int,topics:list[ConversationTopic],learner_confirmed:bool=False,learner_id:str|None=None) -> dict[str,Any]:
        """Agree additions, replacements or skipped topics for future lessons using profile CAS. Keep free active and 3..20 unique topics. Each topic has a communicative goal, open questions, criterion and a provisional correctness focus. Active lesson topics are frozen; skipping a future topic never completes or deletes carried work."""
        from .conversation import Conversation
        return Conversation(resolve(learner_id)).set_topics(idempotency_key,expected_version,[t.model_dump(mode='json') for t in topics],learner_confirmed)

    @mcp.tool(annotations=write)
    def set_english_conversation_route(idempotency_key:str,expected_version:int,stage_order:list[str],topic_ids:list[str],evidence_ids:list[str],rationale:str,learner_confirmed:bool=False,learner_id:str|None=None) -> dict[str,Any]:
        """After getting to know the learner on at least two topics, agree the order of dialogue/story/opinion/comparison/spontaneous goals and one or two next planned topics plus free. Cite original saved conversation replies from this learner and explain the adaptation. Uses profile CAS, retains agreed goal/load, never certifies proficiency or rewrites the active lesson/carry."""
        from .conversation import Conversation
        return Conversation(resolve(learner_id)).set_route(idempotency_key,expected_version,stage_order,topic_ids,evidence_ids,rationale,learner_confirmed)

    @mcp.tool(annotations=write)
    def select_english_conversation_topic(idempotency_key:str,session_id:str,expected_version:int,item_id:str,mode:str,topic_id:str|None=None,topic:ConversationTopic|None=None,learner_confirmed:bool=False,learner_id:str|None=None) -> dict[str,Any]:
        """Choose a planned or learner-chosen free topic within an unfinished conversation item, or return to its saved planned topic. expected_version is Coach session version. Custom topic is allowed in free mode. Preserves item/skill/history and the planned return point; does not mark completion or end a lesson. Explicitly finish an incompatible active speaking practice first."""
        from .conversation import Conversation
        return Conversation(resolve(learner_id)).select(idempotency_key,session_id,expected_version,item_id,mode,topic_id,topic.model_dump(mode='json') if topic else None,learner_confirmed)

    @mcp.tool(annotations=write)
    def save_english_conversation_block(idempotency_key:str,session_id:str,expected_version:int,expected_coach_version:int,attempts:list[Attempt],annotations:list[ConversationAnnotation],save_requested:bool=False,learner_id:str|None=None) -> dict[str,Any]:
        """At an explicitly requested checkpoint save up to 20 actual free-conversation replies through the original host ledger. Annotate each attempt_key once with only demonstrated dimensions and at most one reviewed correction. Actual errors differ from optional natural alternatives; at most two correction focuses per topic block. Reuse references a saved correction, independent correct reply, delay and different context. No copied learner answers in domain documents, no model review/end. During voice buffer candidates until a permitted save point; never claim automatic background recording. finalize_english_lesson explicitly finishes and freezes a summary from these saved references."""
        from .conversation import Conversation
        return Conversation(resolve(learner_id)).save_block(idempotency_key,session_id,expected_version,expected_coach_version,
            [a.model_dump(mode='json') for a in attempts],[a.model_dump(mode='json') for a in annotations],save_requested)

    @mcp.tool(annotations=read)
    def list_english_teaching_policies(learner_id:str|None=None) -> dict[str,Any]:
        """Read real server policy identifiers, versions, teaching contracts and changelogs. Foundation uses basic words and homework; conversation uses natural C1-oriented teacher speech and no grammar drills by default. This is not a learner CEFR assessment."""
        from .policies import catalog
        resolve(learner_id)
        return dict(items=catalog())

    @mcp.tool(annotations=write)
    def set_english_grammar_permission(idempotency_key:str, expected_version:int, enabled:bool, learner_confirmed:bool=False,
                                       scope:str='future',session_id:str|None=None,item_id:str|None=None,learner_id:str|None=None) -> dict[str,Any]:
        """Conversation policy only, explicit learner agreement. Future scope: expected_version=profile version, no session/item IDs; changes future lessons, keeping active session permissions frozen. Item scope: expected_version=Coach session version, session_id and unfinished item_id required; affects that block only. Revoking item permission exits its drill cycle without inventing success. This does not request a grammar exercise automatically."""
        return resolve(learner_id).grammar_permission(idempotency_key,expected_version,enabled,learner_confirmed,scope,session_id,item_id)

    @mcp.tool(annotations=read)
    def get_english_vocabulary(learner_id:str|None=None) -> dict[str, Any]:
        """Read phrases under the active teaching policy: basic foundation or useful natural conversational expressions. Absence means no observed lexical history, never an inferred vocabulary size. Keep grammar and lexical success separate; do not show tracked phrases in independent test prompts."""
        from .vocabulary import Vocabulary
        return Vocabulary(resolve(learner_id)).context()

    @mcp.tool(annotations=write)
    def teach_english_phrase(idempotency_key:str, session_id:str, expected_version:int, phrase:str, meaning:str, basic_reviewed:bool, learner_id:str|None=None) -> dict[str, Any]:
        """Register a reviewed expression under the session policy. basic_reviewed=true confirms wording and meaning were reviewed. Foundation: ONE short basic phrase, no complex chunks/idioms, zero during difficult repair. Conversation: useful natural expressions within its own budget, no compulsory repetition. Re-exposure resets the independent-check delay. expected_version is Coach session version."""
        from .vocabulary import Vocabulary
        return Vocabulary(resolve(learner_id)).teach(idempotency_key,session_id,expected_version,phrase,meaning,basic_reviewed)

    @mcp.tool(annotations=write)
    def record_english_phrase_evidence(idempotency_key:str, phrase_id:str, expected_version:int, attempt_id:str, kind:str, situation:str, lexically_correct:bool, learner_id:str|None=None) -> dict[str, Any]:
        """Link a checked original learner observation to a policy-selected expression: understood, assisted, independent or transferred. Assess lexical meaning separately from grammatical outcome. Never link teacher speech. Independent wording requires original unassisted evidence after exposure delay; transfer also changes the situation. Active/stable are pilot evidence states, not universal mastery. expected_version is phrase document version."""
        from .vocabulary import Vocabulary
        return Vocabulary(resolve(learner_id)).record(idempotency_key,phrase_id,expected_version,attempt_id,kind,situation,lexically_correct)

    @mcp.tool(annotations=write)
    def finalize_english_lesson(session_id:str, expected_version:int, expected_coach_version:int,
                                idempotency_key:str, explicit_end:bool, attempts:list[Attempt]=[], feedback:list[Feedback]=[], learner_id:str|None=None) -> dict[str, Any]:
        """After an actual explicit learner end, atomically save final answers, finish and enqueue FINAL-version review. Foundation issues basic homework 10–15 minutes in two approaches. Conversation issues only previously agreed optional story/opinion preparation; default is none. expected_version=original session, expected_coach_version=Coach document. queued is not applied. Identical retries are safe. Never invent observed answers."""
        return resolve(learner_id).finalize(idempotency_key,session_id,expected_version,expected_coach_version,
                                  [a.model_dump(mode='json') for a in attempts],explicit_end,
                                  [f.model_dump(mode='json') for f in feedback])

    @mcp.tool(annotations=read)
    def get_english_homework(homework_id:str|None=None, learner_id:str|None=None) -> dict[str, Any]:
        """Read latest applicable homework/preparation or exact historical ID, including partial submissions. New chats can resume without reopening the finished lesson. Keys are hidden. Follow its teaching policy: basic wording for foundation; optional conversational preparation for conversation."""
        from .homework import Homework
        return dict(homework=Homework(resolve(learner_id)).get(homework_id))

    @mcp.tool(annotations=write)
    def issue_english_homework(session_id:str, idempotency_key:str, learner_id:str|None=None) -> dict[str, Any]:
        """Issue/resume homework from an ALREADY finished lesson's actual saved answers, under its frozen policy/settings. Foundation uses basic exercises; conversation returns none unless optional preparation was agreed. No reopening or alteration of historical attempts. An empty lesson supplies no personalized evidence. Repeated issuance returns the same assignment."""
        from .homework import Homework
        coach=resolve(learner_id)
        def action():
            doc=Homework(coach).issue(session_id)
            return dict(homework=Homework(coach).get(doc['key']) if doc else None)
        return coach.request(idempotency_key,'homework_issue',dict(session_id=session_id),action)

    @mcp.tool(annotations=write)
    def submit_english_homework(homework_id:str, expected_version:int, idempotency_key:str, answers:list[HomeworkAnswer], learner_id:str|None=None) -> dict[str, Any]:
        """Check and save 1..6 homework/preparation answers, including partial submissions. For free replies FIRST assess meaning, the selected accuracy focus and policy-appropriate vocabulary; supply judgments and a short reason. Accept valid alternative formulations. Controlled items use verified keys. Record actual help as hint/immediate_repeat; key exposure counts as assisted. Delayed items need at least 10 minutes. Missing work is not an error or mastery regression. Conversation preparation never starts a compulsory grammar/repair loop."""
        from .homework import Homework
        return Homework(resolve(learner_id)).submit(idempotency_key,homework_id,expected_version,[a.model_dump() for a in answers])

    @mcp.tool(annotations=write)
    def reveal_english_homework_answers(homework_id:str, expected_version:int, idempotency_key:str, learner_id:str|None=None) -> dict[str, Any]:
        """Only when the learner explicitly asks for keys. Records exposure so subsequent answers cannot be called independent. Free messages have criteria rather than one compulsory answer."""
        from .homework import Homework
        return Homework(resolve(learner_id)).reveal(idempotency_key,homework_id,expected_version)

    @mcp.tool(annotations=write)
    async def submit_english_material(idempotency_key:str, text:str, context:str='', learner_id:str|None=None) -> dict[str, Any]:
        """On the learner's explicit request, analyze an occasional work dialogue in one call. The methodologist saves a bounded work-context analysis, selected fragments and grounded speaking exercises automatically; no card-selection step or active lesson is needed. The full input goes to the configured external provider when COACH_PROVIDER=http, but is not stored in Coach. Work dialogue is context, never observed learner performance. Identical retries use the same key and arguments."""
        coach = resolve(learner_id)
        provider, timeout = from_env()
        return await MaterialIntake(coach, provider, timeout).submit(idempotency_key, text, context)

    @mcp.tool(annotations=write)
    def archive_english_material(idempotency_key:str, source_id:str, expected_version:int, learner_id:str|None=None) -> dict[str, Any]:
        """Exclude an outdated work dialogue analysis and its phrases from future lesson selection. Read work_context for the source ID/version. History remains available for audit."""
        return MaterialIntake(resolve(learner_id), None, 0).archive(idempotency_key, source_id, expected_version)

    @mcp.tool(annotations=write)
    def start_english_practice(session_id:str, expected_version:int, idempotency_key:str, pattern_id:str, task:str, mode:str='coaching', work_exercise_id:str|None=None, learner_id:str|None=None) -> dict[str, Any]:
        """Start a persisted speaking task after begin_item. For a lesson_brief exercise pass its id as work_exercise_id; this records use of the source. expected_version is COACH version. Use conversation mode to buffer errors during role-play, coaching for short retrieval. One prompt then wait; no audio access."""
        return Speaking(resolve(learner_id)).start(idempotency_key, session_id, expected_version,
                                         pattern_id, task, mode, work_exercise_id)

    @mcp.tool(annotations=write)
    def update_english_practice(practice_id:str, expected_version:int, session_id:str, expected_session_version:int, idempotency_key:str, action:str, attempt:Attempt|None=None, task:str='', correction:str='', learner_id:str|None=None) -> dict[str, Any]:
        """Persist one actual learner observation via respond. expected_version=practice, expected_session_version=original session. Foundation: produce/reuse independent; repair/task_retry hint; reproduce/full-model immediate_repeat. Conversation: brief correction keeps discussion open; mandatory help/coach/repeat cycles require a permitted drill block. continue closes the conversation practice block with a next-topic prompt, never the lesson. transfer is a new situation after a delay. An immediate imitation must be recorded as assisted. Correction is teacher interpretation, not learner mastery. Read current versions after writes. No model review or lesson finish."""
        return Speaking(resolve(learner_id)).update(idempotency_key, practice_id, expected_version, session_id,
                                          expected_session_version, action,
                                          attempt.model_dump(mode='json') if attempt else None, task, correction)

    @mcp.tool(annotations=read)
    def get_english_context(detail:str='runtime', interaction_mode:str='standard', learner_id:str|None=None) -> dict[str, Any]:
        """Call in every new English chat. Default runtime returns one next_action, current curriculum, guardrails and bounded evidence; say say_first verbatim at lesson start. detail=full returns original full context and program. Select hands_free only on explicit request; driving defers tasks until safely stopped. Follow versioned current session, not template status. Reading never starts or completes an item. Work sources are context, not learner ability; no audio measures."""
        return resolve(learner_id).context(detail,interaction_mode)

    @mcp.tool(annotations=read)
    def check_english_teaching_turn(session_id:str,expected_version:int,turn:TeachingTurn, learner_id:str|None=None) -> dict[str, Any]:
        """Before a planned teaching turn, check structured flags, saved evidence and active item grammar permission. In conversation disclose activity/repetition/correction count/timing; let the learner finish unless meaning is blocked. No writes. Cannot verify audio, flags or semantic equivalence; semantic_review_required means the teacher must review meaning. learner_requested_end requires an actual explicit request."""
        from .runtime import check_turn
        return check_turn(resolve(learner_id),session_id,expected_version,turn.model_dump(mode='json'))

    @mcp.tool(annotations=write)
    def configure_english(idempotency_key:str, goal:Goal, expected_version:int=0, learner_confirmed:bool=False, learner_id:str|None=None,policy_id:PolicyId|None=None) -> dict[str, Any]:
        """Set an explicitly agreed goal, workload, milestones, skills and foundation/conversation policy. Omitted policy retains the existing assignment, or foundation for a compatible initial client. New conversation profiles start with grammar drills and preparation off. Policy changes require finishing existing work. No inferred proficiency."""
        return resolve(learner_id).configure(idempotency_key, goal.model_dump(mode='json'), expected_version, learner_confirmed,policy_id)

    @mcp.tool(annotations=write)
    def start_coach_session(idempotency_key:str, learner_id:str|None=None) -> dict[str, Any]:
        """Start/resume using the agreed plan; retain unfinished items and freeze mechanics/settings actually used. Say the returned say_first verbatim before beginning the lesson if it has not already been spoken in this chat."""
        return resolve(learner_id).start(idempotency_key)

    @mcp.tool(annotations=write)
    def save_english_progress(session_id:str, expected_version:int, idempotency_key:str, attempts:list[Attempt], feedback:list[Feedback]=[], discoveries:list[Discovery]=[], learner_id:str|None=None) -> dict[str, Any]:
        """Only on an explicit request to SAVE PROGRESS: atomically persist supplied observations and enqueue server methodology. Does NOT finish the lesson. Success confirms text persistence, not audio access. Use save_checkpoint for technical saves without review."""
        return resolve(learner_id).save(idempotency_key, session_id, expected_version, [a.model_dump(mode='json') for a in attempts], review=True,
                              feedback=[f.model_dump(mode='json') for f in feedback], discoveries=[d.model_dump(mode='json') for d in discoveries])

    @mcp.tool(annotations=write)
    def update_english_session(session_id:str, expected_version:int, idempotency_key:str, action:str, item_id:str|None=None, note:str='', explicit_end:bool=False, learner_id:str|None=None) -> dict[str, Any]:
        """Plan Guard actions: begin_item, branch, return, complete_item, pause, resume, resolve_state (explicit item plus explanatory note; retain branch return point), finish. Identify the actual item before recording attempts; a conflicting unfinished practice must be resumed through its linked item. expected_version is COACH version. Prefer finalize_english_lesson for explicit end plus final save/review/homework in one transaction. Finish issues homework only from actual saved observations; carry items forward."""
        return resolve(learner_id).transition(idempotency_key, session_id, expected_version, action, item_id, note, explicit_end)

    @mcp.tool(annotations=write)
    def set_english_settings(idempotency_key:str, expected_version:int, settings:Settings|ConversationSettings, learner_confirmed:bool=False, learner_id:str|None=None) -> dict[str, Any]:
        """Persist agreed settings for future lessons; expected_version=profile. Foundation vocabulary is basic, one phrase maximum, homework 10–15 minutes. Conversation vocabulary is natural with its own budget/correction intensity; homework_minutes=0 disables preparation, a positive value is only explicitly agreed optional story/opinion preparation. Active lesson snapshots remain unchanged. Grammar permission is a separate tool."""
        return resolve(learner_id).settings(idempotency_key, expected_version, settings.model_dump(mode='json',exclude_unset=True), learner_confirmed)

    @mcp.tool(annotations=write)
    def switch_english_mechanic(idempotency_key:str, session_id:str, expected_version:int, item_id:str, mechanic:str, learner_confirmed:bool=False, learner_id:str|None=None) -> dict[str, Any]:
        """Change one unfinished current exercise and persist the preference for future sessions. Preserves the actual previous mechanism usage. expected_version is coach session version."""
        return resolve(learner_id).switch(idempotency_key, session_id, expected_version, item_id, mechanic, learner_confirmed)

    @mcp.tool(annotations=read)
    def get_english_history(learner_id:str|None=None) -> dict[str, Any]:
        """Read profile/plan/settings history for a deliberate rollback."""
        return dict(items=resolve(learner_id).history())

    @mcp.tool(annotations=write)
    def restore_english(idempotency_key:str, expected_version:int, source_version:int, part:str, learner_confirmed:bool=False, learner_id:str|None=None) -> dict[str, Any]:
        """Restore plan or settings from history as a NEW version; never erase observations or history."""
        return resolve(learner_id).restore(idempotency_key, expected_version, source_version, part, learner_confirmed)

    @mcp.tool(annotations=read)
    def get_english_review(job_id:str, learner_id:str|None=None) -> dict[str, Any]:
        """Read durable review status, uncertainty, evidence, rationale, verification and pending approvals. queued/running does not mean applied."""
        if not job_id.startswith('coach-job-'):
            raise ValueError('Expected review job id')
        return resolve(learner_id).required(job_id)

    @mcp.tool(annotations=write)
    def request_english_review(session_id:str, expected_version:int, expected_coach_version:int, idempotency_key:str, learner_id:str|None=None) -> dict[str, Any]:
        """Request a fresh bounded methodology review after failed/stale review, including an already finished lesson. Read latest versions first: expected_version=original session, expected_coach_version=Coach document. Does not reopen the lesson, issue another homework or invent attempts. queued does not mean applied; do not poll endlessly."""
        coach=resolve(learner_id)
        def action():
            if coach.legacy.get(session_id)['session']['version']!=expected_version or coach.required('coach-session-'+session_id)['version']!=expected_coach_version:
                raise ValueError('Version conflict; reload context')
            return dict(job_id=coach.enqueue_review(idempotency_key,session_id),status='queued')
        return coach.request(idempotency_key,'request_review',dict(sid=session_id,expected_version=expected_version,expected_coach_version=expected_coach_version),action)

    @mcp.tool(annotations=write)
    def decide_english_proposal(idempotency_key:str, job_id:str, proposal_id:int, expected_version:int, accept:bool, learner_confirmed:bool=False, learner_id:str|None=None) -> dict[str, Any]:
        """Apply/reject the exact goal/workload proposal after explicit learner approval; stale proposals cannot overwrite newer decisions."""
        return resolve(learner_id).decide(idempotency_key, job_id, proposal_id, expected_version, accept, learner_confirmed)
