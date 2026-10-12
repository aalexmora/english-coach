"""Bounded, read-only lesson decisions over the authoritative Coach state."""
from datetime import datetime, timezone
import json
from . import policies

GUARDS = [
    'Ask one short prompt, then wait for the learner.',
    'Do not reveal the answer before an independent diagnostic; teaching support is allowed during repair.',
    'Do not praise correctness of an incorrect or ambiguous answer. Preserve the intended meaning.',
    'Correct at most two targets in conversation, then return to the communicative task.',
    'Only the learner ends or pauses the lesson. Saving or finishing a plan is not an end command.',
    'A hinted answer or imitation is not independent success; ten-minute reuse is not long-term mastery.',
    'No pronunciation, speed or hesitation measurements from text.',
    'Use basic familiar words and short sentences. No complex professional phrases or idioms. At most one new simple phrase; none during difficult repair.',
    'Do not call an identical answer a correction. Clarify an unfinished thought before changing its meaning.',
    'After explicit finish, deliver the saved homework receipt. Explain failed/stale review once; do not keep polling without progress.',
]


def health(jobs):
    ordered = sorted(jobs, key=lambda d: (d['created_at'], d['key']), reverse=True)
    def brief(doc):
        if not doc: return None
        v=doc['value']
        return dict(id=doc['key'], status=v['status'], at=doc['updated_at'], error=v.get('error'))
    successful=next((d for d in ordered if d['value']['status']=='applied'),None)
    failed=next((d for d in ordered if d['value']['status']=='failed'),None)
    latest=ordered[0] if ordered else None
    return dict(latest=brief(latest), last_success=brief(successful), last_failure=brief(failed),
                pending_count=sum(d['value']['status'] in ('queued','running') for d in ordered),
                state=('idle' if latest is None else 'attention' if latest['value']['status'] in ('failed','stale')
                       else 'working' if latest['value']['status'] in ('queued','running') else 'ok'),
                interpretation='Job health only, not a provider uptime or learning-effect claim')


def program_slice(doc):
    if not doc or doc.get('invalid'): return doc
    v=doc['value']; current=v['teaching_state']['current_stage']
    stage=next(s for s in v['stages'] if s['id']==current)
    return dict(key=doc['key'],version=doc['version'],revision=v.get('revision'),
                stage=stage,teaching_state=v['teaching_state'],method_rules=v.get('method_rules',[]),
                transition_rule=v.get('transition_rule'),
                source_limits=[s for s in v['source_analysis'] if s['id'] in stage['source_ids']],
                detail='Current stage; request detail=full for all stages and sources')


def lesson_runtime(ctx, mode='standard'):
    if mode not in ('standard','hands_free','driving'): raise ValueError('Unknown interaction mode')
    p=ctx['profile']; session=ctx['session']; sv=session['value'] if session else {}
    policy=policies.session_selection(session) if session else policies.selection(p)
    conversation=policy['id']==policies.CONVERSATION
    items=sv.get('items',ctx['unfinished']); pending=[i for i in items if i['status']!='done']
    current=next((i for i in pending if i['id']==sv.get('current_item_id')),None)
    problems=[]
    if sv.get('current_item_id') and current is None: problems.append('current_item_missing_or_done')
    if sv.get('current_practice_id') and ctx.get('current_practice_exists') is False:
        problems.append('current_practice_missing')
    practices=ctx['speaking']['open_practices']
    practice=next((d for d in practices if d['key']==sv.get('current_practice_id')),None)
    if practice and practice['value']['stage']!='awaiting_reuse' and (not current or practice['value']['item_id']!=current['id']):
        problems.append('practice_item_mismatch')
    # An active practice has priority over starting another item or a due check.
    active=practice if practice and practice['value']['stage'] not in ('awaiting_reuse','completed') else None
    if not active:
        active=next((d for d in practices if d['value'].get('current_session_id')==sv.get('session_id')
                     and d['value']['stage'] not in ('awaiting_reuse','completed')),None)
        if active and (not current or active['value']['item_id']!=current['id']):
            problems.append('unfinished_practice_requires_explicit_item')
    program=program_slice(ctx.get('course_program'))
    if program and program.get('invalid'): problems.append('invalid_curriculum')
    if len(ctx.get('legacy_sessions',[]))>1: problems.append('multiple_active_sessions')
    queue=ctx['speaking']['queue']
    action=dict(kind='continue_item', item_id=current['id'] if current else pending[0]['id'] if pending else None,
                prompt=current['task'] if current else pending[0]['task'] if pending else p['value']['goal']['outcome'],
                why='Resume the active communicative task; do not mark it started by reading context',
                return_to=current['id'] if current else pending[0]['id'] if pending else None)
    if mode=='driving':
        action=dict(kind='defer_until_safe',prompt=None,why='Defer learning tasks until safely stopped; do not infer that hands-free is safe',return_to=action['return_to'])
    elif problems:
        action=dict(kind='resolve_state',prompt=None,why='Read current session and explicitly identify the intended item; no automatic history rewrite',issues=problems,
                    current_item_id=sv.get('current_item_id'),practice_item_id=practice['value']['item_id'] if practice else None,
                    candidates=[dict(id=i['id'],skill_id=i['skill_id'],task=i['task']) for i in pending if i['id'] in {sv.get('current_item_id'),practice['value']['item_id'] if practice else None}])
    elif not session:
        action=dict(kind='start_or_resume',prompt=None,why='Start/resume the authoritative lesson before recording work')
    elif sv['phase']=='paused':
        action=dict(kind='await_resume',prompt=None,why='Wait for the learner to resume')
    elif sv['phase']=='finished':
        action=dict(kind='await_start',prompt=None,why='The lesson is finished; start the next lesson only on request')
    elif sv['phase']=='branch' and not active:
        action=dict(kind='continue_branch',prompt=(sv.get('branch') or {}).get('note'),why='Continue the explicit branch',return_to=(sv.get('branch') or {}).get('return_to'))
    elif active:
        pv=active['value']; stage=pv['stage']
        action.update(kind='continue_practice',practice_id=active['key'],practice_version=active['version'],
                      pattern_id=pv['pattern_id'],stage=stage,prompt=pv['task'],
                      assistance='independent' if stage in ('produce','reuse') else 'immediate_repeat' if stage=='reproduce' or pv['help_level']==4 else 'hint',
                      instruction={'repair':'Wait for self-repair; offer one minimal cue only if needed.',
                                   'reproduce':'Ask the learner for the whole repaired sentence.',
                                   'task_retry':'Repeat the communicative task; this remains assisted practice.'}.get(stage,'Ask without a model answer, then wait.'),
                      why='Finish the current response/repair before another target')
    elif practice and current and practice['value']['item_id']==current['id'] and practice['value']['stage']=='awaiting_reuse' and (
            practice['value']['current_session_id']!=sv.get('session_id') or
            datetime.now(timezone.utc)>=datetime.fromisoformat(practice['value']['reuse_after'])):
        action.update(kind='prepare_transfer',prompt=None,practice_id=practice['key'],practice_version=practice['version'],
                      pattern_id=practice['value']['pattern_id'],instruction='Create a different situation, call transfer, then request one unprimed response.',
                      why='The practice is ready for delayed reuse; later-day retention remains a separate check')
    elif practice and current and practice['value']['item_id']==current['id'] and practice['value']['stage']=='awaiting_reuse':
        other=next((i for i in pending if i['id']!=action.get('item_id')),None)
        action.update(kind='begin_item' if other else 'free_practice',item_id=other['id'] if other else action.get('item_id'),
                      prompt=other['task'] if other else p['value']['goal']['outcome'],
                      why='Reuse is not due yet; continue another task and retain the return point')
    elif current is None and any(
            d['value']['stage']=='awaiting_reuse' and
            (d['value']['current_session_id']!=sv.get('session_id') or datetime.now(timezone.utc)>=datetime.fromisoformat(d['value']['reuse_after'])) and
            any(i['id']==d['value']['item_id'] for i in pending) for d in practices):
        waiting=next(d for d in practices if d['value']['stage']=='awaiting_reuse' and
                     (d['value']['current_session_id']!=sv.get('session_id') or datetime.now(timezone.utc)>=datetime.fromisoformat(d['value']['reuse_after'])) and
                     any(i['id']==d['value']['item_id'] for i in pending))
        action.update(kind='prepare_transfer',prompt=None,item_id=waiting['value']['item_id'],
                      practice_id=waiting['key'],practice_version=waiting['version'],pattern_id=waiting['value']['pattern_id'],
                      instruction='Explicitly begin the linked carried item, create a different situation, call transfer, then ask without a model.',
                      why='At this boundary resume a ready delayed check from the preceding lesson')
    elif current is None:
        due=next((q for q in queue if any(r in q['reasons'] for r in ('scheduled_due','not_seen_recently'))
                  and any(i['skill_id']==q['skill_id'] for i in pending)),None)
        if due and not conversation:
            item=next(i for i in pending if i['skill_id']==due['skill_id'])
            action.update(kind='prepare_cold_check',item_id=item['id'],pattern_id=due['pattern_id'],prompt=None,
                          instruction='Prepare one new meaning-focused situation for this pattern without naming its form; begin this item explicitly.',
                          why='At a task boundary, take a due independent check, then return to the unfinished plan',evidence_ids=due['evidence_ids'])
        elif not pending:
            action.update(kind='free_practice',why='Continue within the agreed goal until the learner stops; completing the plan does not end the lesson')
        else:
            action['kind']='begin_item'
    # Waiting for delayed reuse does not freeze the rest of the lesson.
    verification=[]
    for d in practices:
        v=d['value']
        if v['stage']=='awaiting_reuse':
            verification.append(dict(practice_id=d['key'],pattern_id=v['pattern_id'],not_before=v['reuse_after'],
                                     requirement='A different situation; independent response. Later-day retention still requires a later check.'))
    skill=next((i['skill_id'] for i in items if i['id']==action.get('item_id')),None)
    work=[e for e in ctx.get('reviewed_lesson_brief',ctx['lesson_brief']) if e['skill_id']==skill and e.get('teaching_eligible')][:1]
    if work and action['kind'] in ('begin_item','free_practice'):
        action.update(prompt=work[0]['first_prompt'],work_exercise_id=work[0]['id'],source_id=work[0]['source_id'])
    stage=(program or {}).get('stage')
    if stage and skill in stage.get('skill_ids',[]) and action['kind']=='begin_item' and not work:
        action.update(prompt=stage['diagnostic_prompt'],curriculum_stage=stage['id'],why='Diagnose the current foundation within an existing plan item')
    if mode=='hands_free':
        action['delivery']='One short situation and one question. If the saved task is long, shorten its wording without changing its goal; no lists or tables.'
    settings=sv.get('settings_snapshot',p['value']['settings'])
    guards=GUARDS if not conversation else policies.COMMON+[
        policies.definition(policy)['instructions'],
        'After explicit finish, report saved conversation and any agreed preparation; no compulsory worksheet.',
    ]
    if conversation and action['kind']=='continue_practice' and action['stage']=='produce':
        action['instruction']='React to the meaning. Briefly correct one important error after the thought, then continue the topic. No compulsory repetition.'
    conversation_state=sv.get('conversation')
    topic_binding=(conversation_state or {}).get('items',{}).get(action.get('item_id'))
    if topic_binding and action['kind'] in ('begin_item','continue_item','free_practice') and not work:
        action['prompt']=topic_binding['topic']['questions'][0]
        action['instruction']='React to the last reply and choose one relevant follow-up; these questions are options, not a script to repeat.'
    return dict(goal=p['value']['goal'],settings=settings,future_settings=p['value']['settings'],teaching_policy=policies.contract(policy),
                conversation=(dict(phase=conversation_state['snapshot']['phase'],route_status=conversation_state['snapshot']['route_status'],
                                   current_topic=topic_binding,free_topic_available=True,checkpoint_tool='save_english_conversation_block',
                                   next_verification_targets=(ctx.get('conversation') or {}).get('next_conversation',{}).get('verification_targets',[]),
                                   data_mode='text_conversation',instruction='Take two or three comfortable topics for initial conversation; adapt the provisional route using original replies. No grammar diagnostic worksheet. Only confirmed goal/load are saved.') if conversation_state else None),
                grammar_permissions=sv.get('grammar_permissions',{}),interaction_mode=mode,
                versions=dict(profile=p['version'],session_version=ctx.get('session_version'),
                              coach_version=session['version'] if session else None,
                              course_program=ctx.get('course_program',{}).get('version') if ctx.get('course_program') else None),
                session_id=sv.get('session_id'),phase=sv.get('phase'),
                state_authority=dict(current='session items',future_template='profile plan',
                                     differences='pending template and carried session are compatible',issues=problems),
                curriculum=program,next_action=action,lexical_targets=ctx.get('vocabulary',{}).get('targets',[])[-3:],
                vocabulary_policy=dict(level=policies.definition(policy)['vocabulary'],new_limit=settings.get('new_phrases_per_lesson',1),
                                       instruction='Select useful natural expressions for this conversation; do not force rare words or synonym drills.' if conversation else 'Teach one simple phrase before checking it; use zero new phrases while repairing grammar. Simplify source prompts before asking.'),
                recent_targets=[{k:v for k,v in row.items() if k!='evidence_ids'} for row in sorted(ctx['speaking']['patterns'],key=lambda r:-r['recent']['independent_errors'])
                                if row['needs_practice']][:3],
                due_targets=[q for q in queue if any(r in q['reasons'] for r in ('scheduled_due','not_seen_recently'))][:3],verification=verification[:3],work_exercises=work,
                guardrails=guards,rule_origin='Coach policy and explicit learner preferences; client speech is not observed',
                learning_measurement='Compare independent correct/total, later-day transfer and assistance over lessons; no certified mastery or measured speech timing')


def compact(ctx, mode='standard'):
    if not ctx['configured']:
        return dict(learner_id=ctx['learner_id'],configured=False,say_first=ctx['say_first'],methodology=ctx['methodology'],needs=ctx['needs'])
    result=dict(learner_id=ctx['learner_id'],configured=True,say_first=ctx['say_first'],methodology=ctx['methodology'],
                lesson_runtime=lesson_runtime(ctx,mode),methodologist_health=ctx['methodologist_health'],
                homework=(dict(id=ctx['homework']['key'],version=ctx['homework']['version'],status=ctx['homework']['value']['status'],goal=ctx['homework']['value']['goal'],minutes=ctx['homework']['value']['minutes'],kind=ctx['homework']['value'].get('kind','foundation_homework'),optional=ctx['homework']['value'].get('optional',False),read_tool='get_english_homework') if ctx.get('homework') else None),
                details='Use get_english_context(detail="full") for full history/program; get_session for current observations.')
    if len(json.dumps(result,ensure_ascii=False).encode())>24576:
        # Do not silently truncate user preferences, goals or curriculum rules.
        result.pop('lesson_runtime')
        result.update(full_context_required=True,reason='Authoritative goal/program exceeds the compact budget; load detail=full before teaching')
    return result


def check_turn(coach, sid, expected_version, turn):
    sd=coach.required('coach-session-'+sid)
    if sd['version']!=expected_version: raise ValueError('Stale teaching decision; reload context')
    issues=[]
    policy=policies.session_selection(sd)
    if policy['id']==policies.CONVERSATION:
        if not policy['grammar_exercises'] and turn.get('activity')=='grammar_drill': issues.append('grammar_permission_required')
        if not policy['grammar_exercises'] and turn.get('requires_repetition'): issues.append('compulsory_repetition_disabled')
        if turn.get('correction_timing')=='interrupt' and not turn.get('meaning_blocked'): issues.append('let_learner_finish_thought')
        if turn.get('correction_count',0)>1: issues.append('one_important_correction_per_turn')
    if turn['praises_correctness']:
        observation=next((a for a in coach.legacy.get(sid)['attempts'] if a['id']==turn.get('attempt_id')),None)
        if not observation or observation['outcome']!='correct': issues.append('correctness_praise_not_supported')
    if turn['independent_check'] and turn['reveals_answer']: issues.append('answer_before_independent_check')
    if turn['ends_lesson'] and not turn['learner_requested_end']: issues.append('unrequested_lesson_end')
    if turn['meaning_preserved']=='no': issues.append('changed_intended_meaning')
    if turn['question_count']>1: issues.append('more_than_one_question')
    if sd['value']['phase']=='paused' and turn['question_count']: issues.append('lesson_paused')
    if turn.get('claims_independent'):
        observation=next((a for a in coach.legacy.get(sid)['attempts'] if a['id']==turn.get('attempt_id')),None)
        if not observation or observation['assistance']!='independent': issues.append('independent_claim_not_supported')
    if turn.get('claims_correction'):
        from .homework import normalize
        if not turn.get('learner_answer') or not turn.get('proposed_answer'):
            issues.append('correction_text_missing')
        elif normalize(turn['learner_answer'])==normalize(turn['proposed_answer']):
            issues.append('identical_answer_is_not_correction')
        if turn.get('unfinished_answer'): issues.append('clarify_unfinished_meaning_first')
    return dict(allowed=not issues,violations=issues,coach_version=sd['version'],teaching_policy=policy,
                semantic_review_required=turn['meaning_preserved']=='unknown',
                scope='Checks supplied structured flags and saved evidence only; cannot inspect unsubmitted speech or verify the flags themselves')
