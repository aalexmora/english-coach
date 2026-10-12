"""Speaking workflow and evidence projections over the original Saver attempts.

Documents contain task state and evidence references, never a second attempt ledger.
No audio inference, model calls, SQL or alternative interval scheduler.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from . import policies


HELP = ('Wait for self-correction', 'Try again', 'Minimal cue', 'Two choices', 'Full model, then learner reproduction')


def instant():
    return datetime.now(timezone.utc)


def project(patterns, observations, practices, goal, at=None, current_practice_id=None):
    at = at or instant()
    links = {pid: s['id'] for s in goal['skills'] for pid in s['pattern_ids']}
    states, queue, errors = [], [], []
    for p in patterns:
        aa = sorted((a for a in observations if a['pattern_id']==p['id']), key=lambda a: a['occurred_at'])
        known = [a for a in aa if a['outcome']!='ambiguous']
        independent = [a for a in known if a['assistance']=='independent' and a['outcome']=='correct']
        assisted = [a for a in known if a['assistance']!='independent' and a['outcome']=='correct']
        failed = [a for a in known if a['outcome']=='incorrect' and a['assistance']!='immediate_repeat']
        state = 'insufficient_data'
        if assisted:
            state = 'produced_after_correction' if assisted[-1]['assistance']=='immediate_repeat' else 'produced_with_hint'
        if independent:
            state = 'produced_in_free_speech' if any(a['mode']=='free' for a in independent) else 'produced_independently'
        if len({a['context'] for a in independent})>=2 and any(a['mode']=='free' for a in independent):
            state = 'reused_in_new_context'
        delayed = any(
            datetime.fromisoformat(b['occurred_at'])-datetime.fromisoformat(a['occurred_at'])>=timedelta(minutes=10)
            and a['context']!=b['context'] and b['mode']=='free' for a,b in zip(independent, independent[1:]))
        if delayed:
            state = 'reused_after_delay'
        pending = [d for d in practices if d['value']['pattern_id']==p['id'] and d['value']['stage']!='completed']
        recent = [a for a in known if timedelta(0)<=at-datetime.fromisoformat(a['occurred_at'])<=timedelta(days=14)][-20:]
        recent_independent = [a for a in recent if a['assistance']=='independent']
        recent_failed = [a for a in recent_independent if a['outcome']=='incorrect']
        cold = [a for a in recent_independent if a.get('before_warmup') is True]
        streak = 0
        for a in reversed(recent_independent):
            if a['outcome']!='correct': break
            streak += 1
        retained = any(datetime.fromisoformat(b['occurred_at']).date()>datetime.fromisoformat(a['occurred_at']).date()
                       and a['context']!=b['context'] and b['mode']=='free'
                       for a,b in zip(independent,independent[1:]))
        recent_stats = dict(window_days=14, max_observations=20, known_total=len(recent),
                            independent_total=len(recent_independent), independent_errors=len(recent_failed),
                            independent_error_rate=len(recent_failed)/len(recent_independent) if recent_independent else None,
                            cold_total=len(cold), cold_errors=sum(a['outcome']=='incorrect' for a in cold),
                            cold_failure_rate=sum(a['outcome']=='incorrect' for a in cold)/len(cold) if cold else None,
                            independent_success_streak=streak, last_seen=aa[-1]['occurred_at'] if aa else None)
        recurring = len({a['session_id'] for a in recent_failed})>=2 or len(recent_failed)>=3
        last = known[-1] if known else None
        needs_practice = bool(last and (last['outcome']=='incorrect' or last['assistance']!='independent'))
        states.append(dict(pattern_id=p['id'], evidence_state=state, independent_successes=len(independent),
                           assisted_successes=len(assisted), failures=len(failed), recurring_error=recurring,
                           needs_practice=needs_practice, next_due=p['next_review'],
                           evidence_ids=[a['id'] for a in aa[-10:]], automaticity='unmeasured',recent=recent_stats,
                           retention_evidence='observed_on_later_date' if retained else 'not_yet_observed',
                           verification_needed=needs_practice or not retained,
                           mastery='not_certified'))
        for kind in sorted({a.get('error_type') or 'unclassified' for a in failed}):
            matches = [a for a in failed if (a.get('error_type') or 'unclassified')==kind]
            errors.append(dict(pattern_id=p['id'], error_type=kind, times_seen=len(matches),
                               sessions=len({a['session_id'] for a in matches}), last_seen=matches[-1]['occurred_at'],
                               recent_independent_errors=sum((a.get('error_type') or 'unclassified')==kind for a in recent_failed),
                               recent_independent_total=len(recent_independent),
                               evidence_ids=[a['id'] for a in matches[-10:]]))
        if p['id'] not in links:
            continue
        reasons = []
        if pending: reasons.append('unfinished_practice')
        if recurring and needs_practice and at-datetime.fromisoformat(failed[-1]['occurred_at'])<timedelta(days=14): reasons.append('recurring_error')
        if needs_practice: reasons.append('independent_verification_needed')
        if p['next_review'] and datetime.fromisoformat(p['next_review'])<=at: reasons.append('scheduled_due')
        if last and at-datetime.fromisoformat(last['occurred_at'])>=timedelta(days=14): reasons.append('not_seen_recently')
        if last and not reasons and at-datetime.fromisoformat(last['occurred_at'])<=timedelta(days=7): reasons.append('recent_material')
        if reasons:
            queue.append(dict(pattern_id=p['id'], skill_id=links[p['id']], pattern=p['text'], reasons=reasons,
                              evidence_ids=[a['id'] for a in aa[-5:]], next_due=p['next_review'],
                              priority=min(('unfinished_practice','recurring_error','independent_verification_needed','scheduled_due','not_seen_recently','recent_material').index(r) for r in reasons)))
    queue.sort(key=lambda x:(x['priority'], x['next_due'] or '', x['pattern_id']))
    open_practices = [d for d in practices if d['value']['stage']!='completed']
    open_practices.sort(key=lambda d:(d['key']!=current_practice_id,d['created_at']))
    expanded = []
    for d in open_practices[:10]:
        ids = {e['attempt_id'] for e in d['value']['errors'] if not e.get('reproduced_by')}
        ids.update(r['attempt_id'] for r in d['value']['records'][-3:])
        expanded.append(dict(d, evidence=[a for a in observations if a['id'] in ids][-10:]))
    return dict(patterns=states, error_harvest=errors, queue=queue,
                next_lesson_opening=queue[:3],
                open_practices=expanded, open_practice_count=len(open_practices),
                guidance='Use up to three opening targets inside the existing lesson budget, not extra workload. Ask for meaning in a fresh situation without revealing the answer. Evidence states describe observations, not certified mastery. Apply current profile preferences; historical settings snapshots describe past usage.')


class Speaking:
    def __init__(self, coach):
        self.c = coach

    def binding(self, sid, pattern_id):
        sd = self.c.required('coach-session-'+sid)
        if sd['value']['phase'] not in ('active','branch') or self.c.legacy.get(sid)['session']['status']!='active':
            raise ValueError('Resume an active lesson before practice')
        item = next((i for i in sd['value']['items'] if i['id']==sd['value'].get('current_item_id') and i['status']!='done'), None)
        if item is None:
            raise ValueError('Begin an unfinished plan item first')
        skills = self.c.profile()['value']['goal']['skills']
        if not any(s['id']==item['skill_id'] and pattern_id in s['pattern_ids'] for s in skills):
            raise ValueError('Practice pattern must belong to the current agreed skill')
        return sd, item

    def start(self, key, sid, expected_version, pattern_id, task, mode='coaching', work_exercise_id=None):
        if mode not in ('conversation','coaching') or not 1<=len(task)<=1000:
            raise ValueError('Expected short task and conversation/coaching mode')
        def apply():
            sd, item = self.binding(sid, pattern_id)
            if sd['version']!=expected_version:
                raise ValueError('Version conflict')
            policy=policies.session_selection(sd,item['id'])
            policies.check_activity(policy,item['mechanic'],task,item.get('activity','communicative'))
            effective_mode='conversation' if policy['id']==policies.CONVERSATION and not policy['grammar_exercises'] else mode
            source = None
            if work_exercise_id is not None:
                matches = [d for d in self.c.documents('coach-source-')
                           if d['value'].get('status') == 'active'
                           and any(e['id'] == work_exercise_id and e['skill_id'] == item['skill_id']
                                   for e in d['value'].get('exercises', []))]
                if len(matches) != 1:
                    raise ValueError('Unknown work exercise for the current skill')
                source = matches[0]
                exercise=next(e for e in source['value']['exercises'] if e['id']==work_exercise_id)
                policies.check_activity(policy,exercise['mechanic'],exercise['first_prompt']+' '+exercise['transfer_prompt'],exercise.get('activity','communicative'))
            existing = self.c.documents('coach-practice-')
            if any(d['value']['current_session_id']==sid and d['value']['stage'] not in ('awaiting_reuse','completed') for d in existing):
                raise ValueError('Continue the unfinished practice before starting another')
            pid = 'coach-practice-'+sha256(key.encode()).hexdigest()
            v = dict(origin_session_id=sid, current_session_id=sid, item_id=item['id'],
                     teaching_policy=policy,pattern_id=pattern_id, task=task, original_task=task, mode=effective_mode,
                     mechanic=item['mechanic'], mechanic_version=item['mechanic_version'],
                     work_exercise_id=work_exercise_id,
                     stage='produce', help_level=0, records=[], errors=[], repair_queue=[],
                     reuse_after=None, created_at=instant().isoformat())
            result = self.c.memory.put(pid, v, 0)
            if source:
                value = deepcopy(source['value'])
                value['used_count'] = value.get('used_count', 0) + 1
                value['last_used_at'] = instant().isoformat()
                self.c.memory.put(source['key'], value, source['version'])
            sv=deepcopy(sd['value']); sv['current_practice_id']=pid
            self.c.memory.put(sd['key'], sv, sd['version'])
            return result
        return self.c.request(key,'practice_start',dict(sid=sid,expected_version=expected_version,
                            pattern_id=pattern_id,task=task,mode=mode,
                            work_exercise_id=work_exercise_id),apply)

    def update(self, key, pid, version, sid, session_version, action, attempt=None, task='', correction=''):
        if not pid.startswith('coach-practice-') or len(task)>1000 or len(correction)>1000:
            raise ValueError('Invalid practice or text length')
        if action not in ('respond','help','coach','repeat_task','transfer','continue'):
            raise ValueError('Unknown practice action')
        if (action=='respond') != (attempt is not None):
            raise ValueError('Only respond takes one learner observation')
        if correction and (not attempt or attempt.get('outcome')!='incorrect'):
            raise ValueError('A suggested correction must reference an incorrect learner response')
        def apply():
            doc=self.c.required(pid)
            if doc['version']!=version:
                raise ValueError('Version conflict')
            v=deepcopy(doc['value'])
            sd,item=self.binding(sid,v['pattern_id'])
            policy=policies.session_selection(sd,item['id'])
            policies.check_activity(policy,item['mechanic'],task or v['task'],item.get('activity','communicative'))
            natural=policy['id']==policies.CONVERSATION and (v['mode']=='conversation' or not policy['grammar_exercises'])
            if natural and action in ('help','coach','repeat_task'):
                raise ValueError('Continue the dialogue with brief correction; drill cycles require an explicitly permitted block')
            self.c.check_versions(sid,expected_session_version=session_version)
            stage=v['stage']
            if stage=='completed':
                raise ValueError('Practice already completed')
            v['current_session_id']=sid
            v['item_id']=item['id']
            if action=='continue':
                if not natural or not task or stage not in ('produce','reuse'): raise ValueError('Continue requires a conversation block and next topic prompt')
                v.update(stage='completed',continuation=task)
            elif action=='help':
                if stage not in ('produce','repair','reuse','task_retry') or v['help_level']>=4:
                    raise ValueError('No further help at this stage')
                v['help_level']+=1
                v.update(stage='repair',mode='coaching')
                if not v['repair_queue']:
                    v['repair_queue']=[e['attempt_id'] for e in v['errors'] if not e.get('reproduced_by')][:1]
            elif action=='coach':
                pending=[e['attempt_id'] for e in v['errors'] if not e.get('reproduced_by')]
                if stage!='produce' or v['mode']!='conversation' or not pending:
                    raise ValueError('No buffered conversation errors to coach')
                v.update(mode='coaching', stage='repair', help_level=0, repair_queue=pending[:2])
            elif action=='repeat_task':
                if stage not in ('produce','awaiting_reuse') or not v['records'] or v['repair_queue']:
                    raise ValueError('Finish the current repair/reproduction before retrying the task')
                if stage=='produce' and v['errors']:
                    raise ValueError('Coach the buffered errors before retrying the task')
                v.update(stage='task_retry', mode='coaching', task=v['original_task'], help_level=0)
            elif action=='transfer':
                if stage!=('produce' if natural else 'awaiting_reuse') or not task or task in (v['task'],v['original_task']):
                    raise ValueError('Transfer requires completed reproduction and a different situation')
                if natural:
                    if not v['records']: raise ValueError('Transfer needs an original conversation observation')
                    observed={a['id']:a for a in self.c.legacy.observations()}
                    v['reuse_after']=(datetime.fromisoformat(observed[v['records'][-1]['attempt_id']]['occurred_at'])+timedelta(minutes=10)).isoformat()
                    v['reuse_session_id']=sid
                if sid==doc['value']['current_session_id'] and instant()<datetime.fromisoformat(v['reuse_after']):
                    raise ValueError('Wait for delayed reuse or continue in the next lesson')
                v.update(stage='reuse', mode='conversation' if natural else 'coaching', task=task, help_level=0)
            else:
                if stage not in ('produce','repair','reproduce','reuse','task_retry'):
                    raise ValueError('Prepare delayed transfer before recording reuse')
                if attempt['pattern_id']!=v['pattern_id']:
                    raise ValueError('Observation belongs to another pattern')
                expected = 'immediate_repeat' if stage=='reproduce' or v['help_level']==4 else ('hint' if stage in ('repair','task_retry') else 'independent')
                if not natural and attempt['assistance']!=expected:
                    raise ValueError('Assistance must be '+expected+' for this stage')
                if natural and attempt['assistance']=='independent':
                    from .homework import normalize
                    for error in v['errors']:
                        if error.get('suggested_correction') and error.get('at') and timedelta(0)<=datetime.fromisoformat(attempt['occurred_at'])-datetime.fromisoformat(error['at'])<timedelta(minutes=10):
                            if normalize(error['suggested_correction']) in {normalize(attempt.get('observation','')),normalize(attempt['context'])}:
                                raise ValueError('Immediate imitation of a correction is assisted, not independent')
                if stage=='reuse' and attempt['mode']!='free':
                    raise ValueError('Transfer needs free speech, without a prescribed structure')
                if natural and stage=='reuse' and attempt['assistance']!='independent':
                    raise ValueError('Natural transfer needs independent original evidence')
                if stage=='reuse' and sid==v.get('reuse_session_id') and datetime.fromisoformat(attempt['occurred_at'])<datetime.fromisoformat(v['reuse_after']):
                    raise ValueError('Observation does not establish the required delay')
                if stage=='reuse' and attempt['context'] in [a['context'] for a in self.c.legacy.observations() if a['id'] in {r['attempt_id'] for r in v['records']}]:
                    raise ValueError('Transfer observation needs a new context')
                if len(v['records'])>=100:
                    raise ValueError('Practice observation limit reached')
                if any(a['idempotency_key']==attempt['idempotency_key'] for a in self.c.legacy.observations()):
                    raise ValueError('Use a new observation; retries must reuse the original request key')
                saved=self.c.save(sha256((key+':observation').encode()).hexdigest(),sid,session_version,[attempt])
                aid=saved['attempt_ids'][0]
                # The original attempt cannot be reinterpreted as a second practice event.
                if any(aid==r['attempt_id'] for d in self.c.documents('coach-practice-') for r in d['value']['records']):
                    raise ValueError('Observation already attached to a practice')
                v['records'].append(dict(attempt_id=aid,stage=stage,help_level=v['help_level'],session_id=sid,
                                         mechanic=item['mechanic'],mechanic_version=item['mechanic_version']))
                outcome=attempt['outcome']
                if outcome=='incorrect':
                    v['errors'].append(dict(attempt_id=aid, at=attempt['occurred_at'],suggested_correction=correction or None,
                                             source='teacher_interpretation',reproduced_by=None))
                    if not natural and v['mode']!='conversation':
                        if not v['repair_queue']: v['repair_queue']=[aid]
                        v.update(stage='repair',help_level=0)
                elif not natural and outcome=='correct' and not (stage=='produce' and v['mode']=='conversation'):
                    if stage=='repair':
                        v.update(stage='reproduce')
                    elif stage=='reproduce':
                        if v['repair_queue']:
                            repaired=v['repair_queue'].pop(0)
                            next(e for e in v['errors'] if e['attempt_id']==repaired)['reproduced_by']=aid
                        if v['repair_queue']:
                            v.update(stage='repair',help_level=0)
                        else:
                            v.update(stage='awaiting_reuse',reuse_after=(datetime.fromisoformat(attempt['occurred_at'])+timedelta(minutes=10)).isoformat(),reuse_session_id=sid)
                    elif stage=='reuse':
                        v.update(stage='completed')
                    else:
                        v.update(stage='awaiting_reuse',reuse_after=(datetime.fromisoformat(attempt['occurred_at'])+timedelta(minutes=10)).isoformat(),reuse_session_id=sid)
                # An ambiguous transcription never advances the learning state.
                if natural: v.update(stage='produce',mode='conversation',help_level=0)
                sd=self.c.required(sd['key'])
            sv=deepcopy(sd['value']); sv['current_practice_id']=None if action=='continue' else pid
            self.c.memory.put(sd['key'],sv,sd['version'])
            return self.c.memory.put(pid,v,version)
        return self.c.request(key,'practice_update',dict(pid=pid,version=version,sid=sid,session_version=session_version,
                              action=action,attempt=attempt,task=task,correction=correction),apply)
