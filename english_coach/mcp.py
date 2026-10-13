"""MCP registration in the host process. Identity is obtained on every request."""
from typing import Any, Callable
from .models import Goal, Settings, ConversationSettings, PolicyId, Feedback, Discovery, TeachingTurn, HomeworkAnswer, ConversationOnboarding, ConversationTopic, ConversationAnnotation
from .speaking import Speaking
from .material import MaterialIntake
from .methodologist import from_env
from .versions import version_alias


def register(mcp, factory: Callable, read, write, Attempt, submit_material_async=None):
    def resolve(learner_id):
        # The host authorizes selection before constructing both public APIs.
        return factory() if learner_id is None else factory(learner_id)

    @mcp.tool(annotations=read)
    def get_english_admin_view(section:str='overview',days:int=14,start:str|None=None,end:str|None=None,query:str='',status:str='',mode:str='',limit:int=20,offset:int=0,learner_id:str|None=None) -> dict[str,Any]:
        """Read full paginated admin projections with all matching aggregates, Moscow date boundaries, source versions and coverage. Main sections: home/methodology/roadmap/decisions. Legacy projections: overview/program/progress/vocabulary/lessons/methodologist/materials/settings. Atomic host snapshot; never launches a model, changes lexical exposure or fabricates learning history."""
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
    def save_english_conversation_block(idempotency_key:str,session_id:str,expected_coach_version:int,attempts:list[Attempt],annotations:list[ConversationAnnotation],save_requested:bool=False,learner_id:str|None=None,
                                        expected_session_version:int|None=None,expected_version:int|None=None) -> dict[str,Any]:
        """At an explicitly requested checkpoint save up to 20 actual free-conversation replies through the original host ledger. Annotate each attempt_key once with only demonstrated dimensions and at most one reviewed correction. Actual errors differ from optional natural alternatives; at most two correction focuses per topic block. Reuse references a saved correction, independent correct reply, delay and different context. No copied learner answers in domain documents, no model review/end. During voice buffer candidates until a permitted save point; never claim automatic background recording. finalize_english_lesson explicitly finishes and freezes a summary from these saved references."""
        from .conversation import Conversation
        version=version_alias(expected_session_version,expected_version,'expected_session_version',required=True)
        return Conversation(resolve(learner_id)).save_block(idempotency_key,session_id,version,expected_coach_version,
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
    def finalize_english_lesson(session_id:str, expected_coach_version:int,
                                idempotency_key:str, explicit_end:bool, attempts:list[Attempt]=[], feedback:list[Feedback]=[], learner_id:str|None=None,
                                expected_session_version:int|None=None, expected_version:int|None=None) -> dict[str, Any]:
        """After an actual explicit learner end, atomically save final answers, finish and enqueue FINAL-version review. expected_session_version=original Saver session; expected_coach_version=Coach document. Deprecated expected_version aliases original session. Foundation issues basic homework 10–15 minutes; conversation issues only agreed optional preparation. queued is not applied. Identical retries are safe. Never invent observed answers."""
        version=version_alias(expected_session_version,expected_version,'expected_session_version',required=True)
        return resolve(learner_id).finalize(idempotency_key,session_id,version,expected_coach_version,
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
        """Durably queue an explicitly submitted work dialogue and return job_id with actual status immediately. Read get_learning_material_job(job_id) separately; queued means received, running means processing, applied means selected results saved. The private source is temporarily retained by the host, excluded from normal exports/backups and removed after processing or expiry. Work dialogue is context, never learner performance. Identical retries use the same key and arguments."""
        if submit_material_async is not None:
            return submit_material_async(idempotency_key,text,context,learner_id)
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
        """Call in every new English chat. Runtime versions.session_version is the original Saver session; versions.coach_version is the Coach document. Pass each to its named expected field. Default runtime returns one next_action, current curriculum, guardrails and bounded evidence; say say_first verbatim at lesson start. detail=full returns full context. Use get_english_session_state for a small cursor/version read. Select hands_free only on explicit request; driving defers tasks until safely stopped. Reading never starts or completes work. No audio measures."""
        return resolve(learner_id).context(detail,interaction_mode)

    @mcp.tool(annotations=read)
    def get_english_lesson_readiness(learner_id:str|None=None) -> dict[str, Any]:
        """Read the latest relevant review job and current plan identity before starting a new lesson. No mutation."""
        return resolve(learner_id).lesson_readiness()

    @mcp.tool(annotations=read)
    def get_english_session_state(session_id:str, learner_id:str|None=None) -> dict[str, Any]:
        """Read only authorized session_version, coach_version, phase, current item/practice and next_action/next_item. No attempts, due bank, full plan or settings, no model call or mutation. Useful for conflict recovery and voice continuation. Context supplies extra scheduled/curriculum suggestions."""
        return resolve(learner_id).session_state(session_id)

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
    def start_coach_session(idempotency_key:str, learner_id:str|None=None, accept_outdated:bool=False, expected_plan_etag:str|None=None) -> dict[str, Any]:
        """Atomically check latest review and start/resume the agreed plan. When started=false, return job_id/status and do not teach a new lesson until applied, or explicit learner agreement sets accept_outdated=true. Use expected_plan_etag from get_english_lesson_readiness. Active lessons retain their snapshot. Say returned say_first at the beginning if not already spoken."""
        return resolve(learner_id).start(idempotency_key,accept_outdated,expected_plan_etag,require_review=True)

    @mcp.tool(annotations=write)
    def save_english_progress(session_id:str, idempotency_key:str, attempts:list[Attempt], feedback:list[Feedback]=[], discoveries:list[Discovery]=[], learner_id:str|None=None,
                              expected_session_version:int|None=None, expected_coach_version:int|None=None,
                              expected_version:int|None=None, item_id:str|None=None, completed_item_ids:list[str]=[]) -> dict[str, Any]:
        """Only on an explicit SAVE PROGRESS request: atomically save observations and enqueue review, without ending. expected_session_version=original Saver session; expected_coach_version=Coach document. Deprecated expected_version aliases ONLY expected_session_version. Omit the session version to resolve it inside the transaction. Supply item_id and the last Coach version to protect attribution. Explicit completed_item_ids completes performed blocks in the same checkpoint and requires Coach CAS; never infer completion from correct attempts. Success returns next_action/next_item and review_status=queued, not applied. A Version conflict contains current/expected tokens: keep key and observations, correct the session token and retry once without get_session; inspect get_english_session_state for a changed Coach/item. Use save_checkpoint without review."""
        version=version_alias(expected_session_version,expected_version,'expected_session_version')
        return resolve(learner_id).save(idempotency_key, session_id, version, [a.model_dump(mode='json') for a in attempts], review=True,
                              feedback=[f.model_dump(mode='json') for f in feedback], discoveries=[d.model_dump(mode='json') for d in discoveries],
                              expected_coach_version=expected_coach_version,item_id=item_id,completed_item_ids=completed_item_ids)

    @mcp.tool(annotations=write)
    def update_english_session(session_id:str, idempotency_key:str, action:str, item_id:str|None=None, note:str='', explicit_end:bool=False, learner_id:str|None=None,
                               expected_coach_version:int|None=None, expected_version:int|None=None) -> dict[str, Any]:
        """Plan Guard actions: begin_item, branch, return, complete_item, pause, resume, resolve_state (explicit item and explanatory note), finish. expected_coach_version is the COACH document, and deprecated expected_version aliases it. Returns named versions and next_action/next_item. Identify the actual item before attempts; unfinished practice must be resumed through its linked item. Prefer finalize_english_lesson for explicit end plus final save/review/homework. Carry unfinished items forward."""
        version=version_alias(expected_coach_version,expected_version,'expected_coach_version',required=True)
        return resolve(learner_id).transition(idempotency_key, session_id, version, action, item_id, note, explicit_end,include_state=True)

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
    def get_english_review(job_id:str, learner_id:str|None=None, detail:str='status') -> dict[str, Any]:
        """Compact read of one job: queued/running/applied/failed, result/error, applied_profile_version and plan_is_current. stale/superseded are terminal unapplied states. Applied changes affect FUTURE lessons; active lesson items remain frozen. Default excludes the input snapshot; detail=full returns the original full job. Reads never launch review; do not poll repeatedly while unchanged."""
        return resolve(learner_id).review(job_id,detail)

    @mcp.tool(annotations=write)
    def request_english_review(session_id:str, expected_coach_version:int, idempotency_key:str, learner_id:str|None=None,
                               expected_session_version:int|None=None, expected_version:int|None=None) -> dict[str, Any]:
        """Request a fresh bounded methodology review after failed/stale review, including a finished lesson. expected_session_version=original Saver session, expected_coach_version=Coach document; deprecated expected_version aliases original session. Use get_english_session_state for versions. Does not reopen, issue homework or invent attempts. queued is not applied; read this job with get_english_review, without endless polling."""
        coach=resolve(learner_id)
        version=version_alias(expected_session_version,expected_version,'expected_session_version',required=True)
        def action():
            coach.check_versions(session_id,version,expected_coach_version)
            return dict(job_id=coach.enqueue_review(idempotency_key,session_id),status='queued')
        return coach.request(idempotency_key,'request_review',dict(sid=session_id,expected_version=version,expected_coach_version=expected_coach_version),action)

    @mcp.tool(annotations=write)
    def decide_english_proposal(idempotency_key:str, job_id:str, proposal_id:int, expected_version:int, accept:bool, learner_confirmed:bool=False, learner_id:str|None=None) -> dict[str, Any]:
        """Apply/reject the exact goal/workload proposal after explicit learner approval; stale proposals cannot overwrite newer decisions."""
        return resolve(learner_id).decide(idempotency_key, job_id, proposal_id, expected_version, accept, learner_confirmed)
