"""Language-neutral lesson planning over the existing public MemoryAPI.

No SQL or extra attempt ledger. Each instance is bound to one authorized
storage identity. The provider suggests plans; it never writes learner data.
"""
from __future__ import annotations
import asyncio
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, model_validator


def clock():
    return datetime.now(timezone.utc).isoformat()


def identity(*parts):
    return sha256(':'.join(map(str, parts)).encode()).hexdigest()


class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)


class LanguageStep(Strict):
    id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,40}$')
    topic: str = Field(min_length=3,max_length=150)
    communicative_goal: str = Field(min_length=3,max_length=300)
    prompts: list[str] = Field(min_length=2,max_length=5)
    success_criterion: str = Field(min_length=3,max_length=300)


class LanguageProgram(Strict):
    rationale: str = Field(min_length=10,max_length=1000)
    steps: list[LanguageStep] = Field(min_length=3,max_length=8)
    @model_validator(mode='after')
    def unique_steps(self):
        if len(set(s.id for s in self.steps))!=len(self.steps):
            raise ValueError('Duplicate program step IDs')
        return self


class LanguageReview(Strict):
    summary: str = Field(min_length=5,max_length=1200)
    next_step_id: str = Field(min_length=1,max_length=60)
    next_prompts: list[str] = Field(min_length=2,max_length=5)
    rationale: str = Field(min_length=5,max_length=800)
    learning_findings: list[str] = Field(default_factory=list,max_length=8)


class LanguageLearning:
    """A profile-scoped language methodology with CAS and bounded evidence."""
    def __init__(self,memory,language,explanation_language='ru'):
        self.memory=memory
        self.language=language
        self.explanation_language=explanation_language
        self.learner_id=memory.user

    def required(self,key):
        doc=self.memory.get(key)
        if doc is None:raise ValueError('Missing '+key)
        if doc['user_id']!=self.learner_id:raise ValueError('Foreign learning document')
        return doc

    def configure(self,key,goal,minutes,interests,level=None,confirmed=False):
        """Agree goals, preserve self-report provenance, queue a model-generated plan."""
        if not confirmed:raise ValueError('Explicit goal confirmation required')
        if not isinstance(goal,str) or not 5<=len(goal)<=500:raise ValueError('Invalid goal')
        if type(minutes) is not int or not 5<=minutes<=120:raise ValueError('Invalid minutes')
        if not isinstance(interests,list) or not 1<=len(interests)<=8 or any(not isinstance(s,str) or not 1<=len(s)<=100 for s in interests):
            raise ValueError('Invalid interests')
        if level is not None and (not isinstance(level,str) or len(level)>100):
            raise ValueError('Invalid self-reported level')
        payload=dict(goal=goal,minutes=minutes,interests=interests,level=level,
                     level_source='learner_statement' if level else 'unknown',
                     language=self.language,explanation_language=self.explanation_language)
        def action():
            old=self.memory.get('language-goal')
            active=self.memory.get('language-active')
            if active and active['value'].get('session_id'):
                raise ValueError('Finish the active lesson before changing the goals')
            goal_doc=self.memory.put('language-goal',payload,old['version'] if old else 0)
            job_id='language-job-'+identity(key,'initial-plan')
            self.memory.put(job_id,dict(kind='initial_plan',status='queued',snapshot=dict(
                goal=goal_doc,program_version=(self.memory.get('language-program') or {}).get('version',0)),
                attempts=0,created_at=clock(),updated_at=clock(),lease=None,error=None),0)
            return dict(profile_id=self.learner_id,job_id=job_id,status='queued',
                        goal_version=goal_doc['version'])
        return self.memory.request(key,dict(op='language-configure',**payload,confirmed=confirmed),action)

    def jobs(self):
        out=[];offset=0
        while True:
            docs=self.memory.list('language-job-',100,offset)
            out.extend(docs)
            if len(docs)<100:return out
            offset+=100

    def recent_sessions(self,limit=5):
        """Bounded real learner evidence; use completed lessons, never invent scores."""
        docs=[];offset=0
        while True:
            page=self.memory.list('language-session-',100,offset)
            docs.extend(page)
            if len(page)<100:break
            offset+=100
        finished=[d for d in docs if d['value']['phase']=='finished']
        finished.sort(key=lambda d:d['value'].get('finished_at',''),reverse=True)
        return [dict(id=d['value']['id'],step=d['value']['step'],
                     finished_at=d['value']['finished_at'],
                     observations=d['value']['observations'][-6:])
                for d in finished[:limit]]

    def latest_job(self):
        return next(iter(sorted(self.jobs(),key=lambda d:(d['value']['created_at'],d['key']),reverse=True)),None)

    def readiness(self):
        goal=self.memory.get('language-goal')
        program=self.memory.get('language-program')
        active=self.memory.get('language-active')
        job=self.latest_job()
        status=job['value']['status'] if job else 'none'
        blocked=status in ('queued','running','failed','stale','proposed','rejected') or program is None
        return dict(profile_id=self.learner_id,language=self.language,
                    status=status,job_id=job['key'] if job else None,
                    plan_version=program['version'] if program else None,
                    goal_version=goal['version'] if goal else None,
                    active_session_id=active['value'].get('session_id') if active else None,
                    lesson_ready=not blocked,
                    next_action='resume' if active and active['value'].get('session_id') else
                       ('start' if not blocked else 'check_job' if status in ('queued','running') else 'retry_or_previous_plan'))

    def context(self):
        with self.memory.atomic():
            return self._context()

    def _context(self):
        goal=self.memory.get('language-goal')
        plan=self.memory.get('language-program')
        ready=self.readiness()
        active_id=ready['active_session_id']
        session=self.memory.get('language-session-'+active_id) if active_id else None
        notes=self.memory.get('language-methodology-notes')
        imported=self.memory.get('language-imported-context')
        proposal=self.memory.get('language-proposal')
        return dict(goal=goal,readiness=ready,program=plan,proposal=proposal,active_session=session,
                    recent_lessons=self.recent_sessions(),
                    methodology_notes=notes['value'] if notes else None,
                    imported_context=imported['value'] if imported else None,
                    instructions='One question at a time. Do not call prompted imitation independent. '
                                 'Persist observations only from actual learner answers. '
                                 'Keep the active lesson snapshot immutable; vary examples without changing the goal.')

    def start(self,key,expected_plan_version=None,accept_outdated=False):
        def action():
            ready=self.readiness()
            if ready['active_session_id']:
                existing=self.required('language-session-'+ready['active_session_id'])
                if existing['value']['phase']=='paused':
                    resumed=self.memory.put(existing['key'],dict(existing['value'],phase='active'),existing['version'])
                    return dict(started=False,resumed=True,session=resumed)
                return dict(started=False,resumed=True,session=existing)
            if expected_plan_version is not None and expected_plan_version!=ready['plan_version']:
                raise ValueError('Plan version conflict')
            if not ready['lesson_ready'] and not (accept_outdated and ready['plan_version'] is not None):
                return dict(started=False,**ready)
            program=self.required('language-program')
            value=program['value']
            stage=next(s for s in value['steps'] if s['id']==value['next_step_id'])
            sid='ls-'+uuid4().hex
            self.memory.put('language-session-'+sid,dict(
                id=sid,profile_id=self.learner_id,language=self.language,phase='active',
                program_version=program['version'],goal_version=self.required('language-goal')['version'],
                step=deepcopy(stage),observations=[],started_at=clock()),0)
            current=self.memory.get('language-active')
            self.memory.put('language-active',dict(session_id=sid),current['version'] if current else 0)
            return dict(started=True,resumed=False,session_id=sid,
                        plan_version=program['version'],step=stage,
                        plan_status=ready['status'],outdated=not ready['lesson_ready'])
        with self.memory.atomic():
            ready=self.readiness()
            if not ready['active_session_id'] and not ready['lesson_ready'] and not (
                accept_outdated and ready['plan_version'] is not None):
                return dict(started=False,**ready)
            return self.memory.request(key,dict(op='language-start',expected_plan_version=expected_plan_version,
                                                accept_outdated=accept_outdated),action)

    def pause(self,key,session_id,expected_session_version):
        """Pause without losing the immutable lesson snapshot or pending observations."""
        def action():
            doc=self.required('language-session-'+session_id)
            if doc['version']!=expected_session_version:raise ValueError('Version conflict')
            active=self.required('language-active')
            if active['value'].get('session_id')!=session_id:raise ValueError('Session is not active')
            if doc['value']['phase']!='active':raise ValueError('Only an active lesson can be paused')
            saved=self.memory.put(doc['key'],dict(doc['value'],phase='paused'),doc['version'])
            return dict(session_id=session_id,session_version=saved['version'],phase='paused')
        return self.memory.request(key,dict(op='language-pause',
            session_id=session_id,expected_session_version=expected_session_version),action)

    def observe(self,key,session_id,expected_session_version,reply,feedback='',assistance='independent'):
        if assistance not in ('independent','hint','immediate_repeat'):raise ValueError('Invalid assistance')
        if not isinstance(reply,str) or not reply.strip() or len(reply)>2000:raise ValueError('Invalid reply')
        if not isinstance(feedback,str) or len(feedback)>1000:raise ValueError('Invalid feedback')
        def action():
            doc=self.required('language-session-'+session_id)
            if doc['version']!=expected_session_version:raise ValueError('Version conflict')
            if doc['value']['phase']!='active':raise ValueError('Session not active')
            v=deepcopy(doc['value'])
            if len(v['observations'])>=100:raise ValueError('Lesson observation limit reached')
            v['observations'].append(dict(id=identity(key,'reply'),reply=reply,
                                          feedback=feedback,assistance=assistance,at=clock()))
            saved=self.memory.put(doc['key'],v,doc['version'])
            return dict(session_id=session_id,session_version=saved['version'],saved=True)
        return self.memory.request(key,dict(op='language-observe',session_id=session_id,
                              version=expected_session_version,reply=reply,feedback=feedback,assistance=assistance),action)

    def finish(self,key,session_id,expected_session_version,explicit_end=False):
        if not explicit_end:raise ValueError('Learner must explicitly finish or pause')
        def action():
            doc=self.required('language-session-'+session_id)
            if doc['version']!=expected_session_version:raise ValueError('Version conflict')
            if doc['value']['phase']!='active':raise ValueError('Session already finished')
            current=self.required('language-active')
            if current['value']['session_id']!=session_id:raise ValueError('Foreign active session')
            v=dict(doc['value'],phase='finished',finished_at=clock())
            finished=self.memory.put(doc['key'],v,doc['version'])
            self.memory.put('language-active',dict(session_id=None),current['version'])
            job_id='language-job-'+identity(key,'review')
            self.memory.put(job_id,dict(kind='review',status='queued',snapshot=dict(
                session=finished,goal=self.required('language-goal'),
                program=self.required('language-program')),
                attempts=0,created_at=clock(),updated_at=clock(),lease=None,error=None),0)
            return dict(saved=True,finished=True,session_id=session_id,
                        review_job_id=job_id,review_status='queued')
        return self.memory.request(key,dict(op='language-finish',session_id=session_id,
                              version=expected_session_version,explicit_end=explicit_end),action)

    async def run_once(self,provider,timeout,authorized=None):
        """Claim one durable job; reject stale snapshots and invalid model output."""
        with self.memory.atomic():
            claim=None
            for doc in sorted(self.jobs(),key=lambda d:(d['value']['created_at'],d['key'])):
                v=doc['value']
                if v['status']=='running' and v.get('lease'):
                    deadline=datetime.fromisoformat(v['lease']['until'])
                    if datetime.now(timezone.utc)<deadline:continue
                    if v['attempts']>=3:
                        self.memory.put(doc['key'],dict(v,status='failed',error='Lease retries exhausted',lease=None),doc['version'])
                        continue
                    v=dict(v,status='queued',lease=None)
                if v['status']!='queued':continue
                if v['attempts']>=3:
                    self.memory.put(doc['key'],dict(v,status='failed',error='Retry limit reached'),doc['version'])
                    continue
                lease=uuid4().hex
                until=(datetime.now(timezone.utc)+timedelta(seconds=timeout+30)).isoformat()
                claimed=self.memory.put(doc['key'],dict(v,status='running',attempts=v['attempts']+1,
                         lease=dict(id=lease,until=until),updated_at=clock()),doc['version'])
                claim=claimed
                break
        if claim is None:return None
        v=claim['value'];snapshot=v['snapshot']
        system=('You are a language-teaching methodologist. Personalize to learner goals; '
                'never infer certified proficiency. Preserve meaning and use natural target-language examples. '
                'Return only JSON according to the supplied schema. '
                'Do not store sensitive learner text in proposed explanations.')
        try:
            if v['kind']=='initial_plan':
                goal=snapshot['goal']['value']
                system+=(' Design a progressive curriculum of 3 to 8 distinct communicative topics. '
                         'Prompts must be in the target language and accessible to the reported starting level. '
                         'This is a provisional plan, not proof of ability.')
                inp=dict(language=self.language,explanation_language=self.explanation_language,
                         requested_goal=goal,prior_context=(self.memory.get('language-imported-context') or {}).get('value'))
                raw=await asyncio.wait_for(provider._complete(system,inp,LanguageProgram.model_json_schema(),
                                           'language_program'),timeout)
                result=LanguageProgram.model_validate(raw).model_dump(mode='json')
            else:
                session=snapshot['session']['value']
                plan=snapshot['program']['value']
                system+=(' Review only actually saved learner replies. Produce a concise explanation, '
                         'new prompts for the next session, and select an existing step ID. '
                         'Do not treat a hinted or repeated reply as independent success.')
                inp=dict(language=self.language,goal=snapshot['goal']['value'],
                         plan=plan,lesson=session,previous_lessons=self.recent_sessions(4),
                         imported=(self.memory.get('language-imported-context') or {}).get('value'))
                raw=await asyncio.wait_for(provider._complete(system,inp,LanguageReview.model_json_schema(),
                                           'language_review'),timeout)
                result=LanguageReview.model_validate(raw).model_dump(mode='json')
                if result['next_step_id'] not in {step['id'] for step in plan['steps']}:
                    raise ValueError('Unknown recommended step ID')
        except asyncio.CancelledError:raise
        except Exception as exc:
            with self.memory.atomic():
                current=self.memory.get(claim['key'])
                if current and (current['value'].get('lease') or {}).get('id')==v['lease']['id']:
                    terminal=current['value']['attempts']>=3
                    self.memory.put(claim['key'],dict(current['value'],
                        status='failed' if terminal else 'queued',
                        error='Methodologist '+type(exc).__name__,lease=None,
                        updated_at=clock()),current['version'])
            return dict(job_id=claim['key'],status='failed_or_retry')
        with self.memory.atomic():
            current=self.memory.get(claim['key'])
            if not current or (current['value'].get('lease') or {}).get('id')!=v['lease']['id']:
                return dict(job_id=claim['key'],status='lease_lost')
            goal=self.memory.get('language-goal')
            program=self.memory.get('language-program')
            stale=goal['version']!=snapshot['goal']['version']
            if v['kind']=='initial_plan':
                stale=stale or (program['version'] if program else 0)!=snapshot['program_version']
            else:
                stale=stale or not program or program['version']!=snapshot['program']['version']
            if authorized is not None and not authorized():
                stale=True
            if stale:
                final=dict(current['value'],status='stale',error='Input versions changed or profile access revoked',
                           lease=None,updated_at=clock())
            else:
                if v['kind']=='initial_plan':
                    previous=self.memory.get('language-proposal')
                    self.memory.put('language-proposal',dict(
                        plan=result,goal_version=goal['version'],
                        program_version=program['version'] if program else 0,
                        review_job=claim['key'],created_at=clock()),
                        previous['version'] if previous else 0)
                    final=dict(current['value'],status='proposed',result=result,error=None,
                               lease=None,updated_at=clock())
                else:
                    p=deepcopy(program['value'])
                    step=next(s for s in p['steps'] if s['id']==result['next_step_id'])
                    step['prompts']=result['next_prompts']
                    p['next_step_id']=result['next_step_id']
                    p['decision_job']=claim['key']
                    self.memory.put('language-program',p,program['version'])
                    notes=self.memory.get('language-methodology-notes')
                    self.memory.put('language-methodology-notes',dict(
                        job_id=claim['key'],summary=result['summary'],
                        rationale=result['rationale'],learning_findings=result['learning_findings']),
                        notes['version'] if notes else 0)
                    final=dict(current['value'],status='applied',result=result,error=None,
                               lease=None,updated_at=clock())
            self.memory.put(claim['key'],final,current['version'])
            return dict(job_id=claim['key'],status=final['status'])

    def retry_job(self,key,job_id):
        """Explicitly enqueue fresh review after terminal failure or stale input."""
        if not job_id.startswith('language-job-'):
            raise ValueError('Invalid language job ID')
        def action():
            previous=self.required(job_id)
            v=previous['value']
            if v['status'] not in ('failed','stale','rejected'):
                raise ValueError('Only failed, stale or rejected jobs can be retried')
            goal=self.required('language-goal')
            program=self.memory.get('language-program')
            if v['kind']=='initial_plan':
                if program:
                    raise ValueError('Plan already available; propose goal changes separately')
                snapshot=dict(goal=goal,program_version=0)
            elif v['kind']=='review':
                sid=v['snapshot']['session']['value']['id']
                session=self.required('language-session-'+sid)
                if session['value']['phase']!='finished':
                    raise ValueError('Only finished lessons may be reviewed')
                if program is None:raise ValueError('No approved plan')
                snapshot=dict(goal=goal,program=program,session=session)
            else:
                raise ValueError('Unknown job kind')
            fresh_id='language-job-'+identity(key,'retry')
            self.memory.put(fresh_id,dict(kind=v['kind'],status='queued',snapshot=snapshot,
                           attempts=0,created_at=clock(),updated_at=clock(),
                           lease=None,error=None,retry_of=job_id),0)
            return dict(job_id=fresh_id,status='queued',retry_of=job_id)
        return self.memory.request(key,dict(op='language-retry-job',job_id=job_id),action)

    def approve_plan(self,key,expected_proposal_version,approved=False):
        """Only an explicit learner decision can apply an initial plan proposal."""
        def action():
            proposal=self.required('language-proposal')
            if proposal['version']!=expected_proposal_version:
                raise ValueError('Plan proposal version conflict')
            v=proposal['value']
            goal=self.required('language-goal')
            previous=self.memory.get('language-program')
            if goal['version']!=v['goal_version'] or (previous['version'] if previous else 0)!=v['program_version']:
                raise ValueError('Proposal became stale; request another plan')
            job=self.required(v['review_job'])
            if job['value']['status']!='proposed':
                raise ValueError('Proposal is no longer active')
            if not approved:
                self.memory.put(job['key'],dict(job['value'],status='rejected'),job['version'])
                return dict(approved=False,status='rejected',job_id=job['key'])
            plan=v['plan']
            program=dict(language=self.language,steps=plan['steps'],
                         next_step_id=plan['steps'][0]['id'],
                         rationale=plan['rationale'],decision_job=job['key'])
            saved=self.memory.put('language-program',program,previous['version'] if previous else 0)
            self.memory.put(job['key'],dict(job['value'],status='applied',
                            applied_plan_version=saved['version']),job['version'])
            return dict(approved=True,status='applied',job_id=job['key'],
                        plan_version=saved['version'])
        return self.memory.request(key,dict(op='approve-language-plan',
                           expected_proposal_version=expected_proposal_version,
                           approved=approved),action)

    def job(self,job_id):
        doc=self.required(job_id)
        if not job_id.startswith('language-job-'):raise ValueError('Expected a language job')
        v=doc['value']
        return dict(job_id=job_id,status=v['status'],error=v.get('error'),
                    kind=v['kind'],attempts=v['attempts'],version=doc['version'],
                    result=v.get('result') if v['status'] in ('applied','proposed') else None)
