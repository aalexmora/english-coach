"""Authenticated UI projections and explicit actions over the public host APIs."""
from copy import deepcopy
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from .coach import now,key_for,dump
from . import __version__,policies
from .curriculum import read_program,KEY
from .runtime import health
from .models import Feedback
from .homework import Homework
from .material import MaterialIntake
from .conversation import Conversation

UI_VERSION='0.5.2'
METRICS_VERSION='admin-metrics-1.0.0'
UI_CHANGES=[dict(version=UI_VERSION,date='2026-10-13',status='installed_build',items=[
    'Выбор независимого учебного профиля на главной, сохранённая цель и программа.',
    'Готовность, согласование программы и история занятий выбранного профиля.']),
    dict(version='0.5.1',date='2026-10-13',status='installed_build',items=[
    'Отдельный настраиваемый вход администратора в форме кабинета.',
    'Пароль UI отделён от кода подключения ChatGPT; прежние browser sessions отзываются.']),
    dict(version='0.5.0',date='2026-10-13',status='installed_build',items=[
    'Независимые языковые профили, онбординг и инструкции для ChatGPT Project.',
    'Готовность следующего урока и отдельные задания методолога.',
    'Асинхронный приём рабочих материалов с проверкой доступа перед сохранением.']),
    dict(version='0.4.0',date='2026-10-12',status='installed_build',items=[
    'Четыре понятных раздела; методика и инструкции на одном экране.',
    'Личные черновики, пример занятия, применение, пробный урок и возврат правил.',
    'Отзывы о методике и решения без поштучных фраз и технических журналов.']),
    dict(version='0.3.1',date='2026-10-11',status='installed_build',items=[
    'Кабинет на отдельном HTTPS-домене с личным входом и защитой запросов.']),
    dict(version='0.3.0',date='2026-10-09',status='previous_build',items=[
    'Личный вход и разрешённые учебные профили.',
    'Восемь разделов с серверными данными, исходными ответами и отдельными версиями.',
    'Настройки, разрешение грамматики, разборы, предложения, история и семейные аккаунты.'])]
SECTIONS=('overview','program','progress','vocabulary','lessons','methodologist','materials','settings')
MANAGEMENT_SECTIONS=('home','methodology','roadmap','decisions')
TZ=ZoneInfo('Europe/Moscow')


def page(rows,limit,offset):
    return dict(items=rows[offset:offset+limit],total=len(rows),offset=offset,limit=limit,next_offset=offset+limit if offset+limit<len(rows) else None)


def ratio(rows):
    known=[r for r in rows if r['outcome']!='ambiguous'];n=sum(r['outcome']=='correct' for r in known)
    return dict(correct=n,total=len(known),accuracy=n/len(known) if known else None,ambiguous=len(rows)-len(known))


class AdminRead:
    def __init__(self,coach):self.c=coach

    def read(self,section='overview',days=14,start=None,end=None,query='',status='',mode='',limit=20,offset=0):
        if section in MANAGEMENT_SECTIONS:
            return self.management_view(section,days,start,end,query,status,mode,limit,offset)
        if section not in SECTIONS or days not in (0,7,14,30) or not 1<=limit<=100 or offset<0 or len(query)>200 or len(status)>40 or len(mode)>40:
            raise ValueError('Invalid view or filters')
        today=datetime.now(TZ).date();first=date.fromisoformat(start) if start else today-timedelta(days=days-1) if days else None
        last=date.fromisoformat(end) if end else today
        if first and first>last:raise ValueError('Invalid date range')
        def included(timestamp):
            if not timestamp:return first is None
            day=datetime.fromisoformat(timestamp).astimezone(TZ).date()
            return (not first or day>=first) and day<=last
        def matches(value):return not query or query.casefold() in str(value).casefold()
        with self.c.memory.atomic():
            p=self.c.memory.get('coach-profile');legacy=self.c.legacy.progress()
            sessions=self.c.legacy.sessions()
            observations=self.c.legacy.observations()
            filtered=[a for a in observations if included(a['occurred_at']) and (not mode or (a.get('before_warmup') if mode=='cold' else a['mode']==mode)) and matches(a)]
            all_docs=self.c.documents('coach-');docs={d['key']:d for d in all_docs}
            program=self.c.memory.get(KEY)
            jobs=[d for d in all_docs if d['key'].startswith('coach-job-')]
            selected=policies.selection(p) if p else None
            active=next((docs.get('coach-session-'+s['id']) for s in legacy['active_sessions'] if docs.get('coach-session-'+s['id'])),None)
            versions=dict(profile=p['version'] if p else None,session=active['version'] if active else None,
                          program=program['version'] if program else None)
            result=dict(section=section,learner_id=self.c.learner_id,generated_at=now(),timezone='Europe/Moscow',
                rules_version=METRICS_VERSION,source_versions=versions,consistency='atomic_host_snapshot',
                filters=dict(days=days,start=first.isoformat() if first else None,end=last.isoformat(),query=query,status=status,mode=mode),
                coverage=dict(complete_matching_aggregates=True,paginated_lists=True,transcript='saved_observations_only',audio='unavailable'),
                configured=bool(p),policy=policies.contract(selected) if selected else None,coach_version=__version__,ui_version=UI_VERSION)
            def doclist(prefix):
                return sorted([d for d in all_docs if d['key'].startswith(prefix) and included(d['updated_at']) and matches(d['value']) and (not status or d['value'].get('status',d['value'].get('state'))==status)],key=lambda d:(d['updated_at'],d['key']),reverse=True)
            metrics={kind:ratio([a for a in filtered if a['assistance']==kind]) for kind in ('independent','hint','immediate_repeat')}
            metrics.update(observations=len(filtered),lessons=len({a['session_id'] for a in filtered}),
                           note='Unique original IDs; ambiguous excluded from accuracy, assistance separate. Text samples do not measure overall fluency or CEFR.')
            if section=='overview':
                context=self.c.context('runtime')
                latest=max(jobs,key=lambda d:(d['updated_at'],d['key'])) if jobs else None
                result.update(metrics=metrics,goal=p['value']['goal'] if p else None,runtime=context.get('lesson_runtime'),
                    health=health(jobs),last_review=self.job(latest) if latest else None,
                    latest_saved=max((a['occurred_at'] for a in observations),default=None),
                    homework=Homework(self.c).get(),conversation=Conversation(self.c).get(limit=1) if p and p['value'].get('conversation') else None)
            elif section=='program':
                result.update(program=read_program(self.c.memory) if selected and selected['id']=='foundation' else None,
                    conversation=deepcopy(p['value'].get('conversation')) if p else None,current_session=deepcopy(active),
                    future_plan=deepcopy(p['value']['plan']) if p else [],carry=deepcopy(docs.get('coach-carry')),
                    goal=deepcopy(p['value']['goal']) if p else None)
                result.update(page(sorted([h for h in self.c.history() if included(h['updated_at']) and matches(h['value'])],key=lambda h:(h['updated_at'],h['version']),reverse=True) if p else [],limit,offset))
            elif section=='progress':
                skills=self.c.skill_evidence(p['value']['goal'],filtered) if p else {}
                pattern_rows=[]
                for pattern in legacy['patterns']:
                    aa=[a for a in filtered if a['pattern_id']==pattern['id']]
                    pattern_rows.append(dict(pattern=pattern,independent=ratio([a for a in aa if a['assistance']=='independent']),
                        assisted=sum(a['assistance']!='independent' for a in aa),evidence_ids=[a['id'] for a in aa][-20:]))
                daily=[]
                for day in sorted({datetime.fromisoformat(a['occurred_at']).astimezone(TZ).date().isoformat() for a in filtered}):
                    rows=[a for a in filtered if datetime.fromisoformat(a['occurred_at']).astimezone(TZ).date().isoformat()==day]
                    daily.append(dict(day=day,**{kind:ratio([a for a in rows if a['assistance']==kind]) for kind in ('independent','hint','immediate_repeat')}))
                result.update(metrics=metrics,daily=daily,skills=skills,patterns=pattern_rows,
                    conversation_progress=self.conversation_progress(filtered) if selected and selected['id']=='conversation' else None)
                result.update(page(sorted(filtered,key=lambda a:(a['occurred_at'],a['id']),reverse=True),limit,offset))
            elif section=='vocabulary':
                lexical=doclist('coach-lexical-');counts={}
                for d in lexical:counts[d['value']['state']]=counts.get(d['value']['state'],0)+1
                result.update(counts=counts,lexical_rule='Pilot evidence states; independent exposure delay and transfer requirements remain in Vocabulary. Not total vocabulary size.',
                              library_note='Selected source phrases are material, not learned lexical targets.')
                result.update(page(lexical,limit,offset))
            elif section=='lessons':
                rows=[]
                for s in sessions:
                    if not included(s['created_at']) or not matches(s):continue
                    sd=docs.get('coach-session-'+s['id']);phase=sd['value']['phase'] if sd else s['status']
                    if status and phase!=status:continue
                    hw=next((d for d in all_docs if d['key'].startswith('coach-homework-') and d['value']['lesson_id']==s['id']),None)
                    j=next(iter(sorted([j for j in jobs if j['value']['snapshot']['session']['value']['session_id']==s['id']],key=lambda j:j['updated_at'],reverse=True)),None)
                    aa=[a for a in observations if a['session_id']==s['id']]
                    rows.append(dict(id=s['id'],created_at=s['created_at'],goal=s['goal'],status=phase,kind=s.get('kind','lesson'),origin_id=s.get('origin_id'),
                        observations=len(aa),policy=(sd or {}).get('value',{}).get('teaching_policy'),
                        homework_id=hw['key'] if hw else None,review=self.job(j) if j else None))
                result.update(page(sorted(rows,key=lambda s:(s['created_at'],s['id']),reverse=True),limit,offset))
            elif section=='methodologist':
                result.update(page([self.job(d) for d in doclist('coach-job-')],limit,offset),health=health(jobs),
                    material_operations=page([dict(id=d['key'],at=d['created_at'],source_id=d['value']['result'].get('source_id'),summary=d['value']['result'].get('summary'),source_existing=d['value']['result'].get('source_existing',False)) for d in doclist('coach-intake-')],limit,offset))
            elif section=='materials':
                result.update(page(doclist('coach-source-'),limit,offset),methods=__import__('english_coach.teaching',fromlist=['METHODS']).METHODS,
                              phrases=page(doclist('coach-material-'),limit,offset),discoveries=page(doclist('coach-discovery-'),limit,offset))
            elif section=='settings':
                result.update(profile=deepcopy(p),policies=policies.catalog(),ui_changes=UI_CHANGES,
                              operations=dict(audio='unavailable',model_usage='unavailable',teaching_checks='not_recorded'))
            return result

    def management_view(self,section,days,start,end,query,status,mode,limit,offset):
        from .management import Management
        with self.c.memory.atomic():
            base=self.read('settings',days,start,end,query,status,mode,limit,offset)
            names=('learner_id','generated_at','timezone','rules_version','source_versions','consistency','coverage','configured','policy','coach_version','ui_version')
            result={k:base[k] for k in names};result['section']=section
            result['management']=Management(self.c).read()
            result['goal']=base['profile']['value']['goal'] if base['profile'] else None
            if section=='home':
                overview=self.read('overview',days,start,end,query,status,mode,limit,offset)
                result.update({k:overview.get(k) for k in ('runtime','health','last_review','latest_saved','homework')})
            elif section=='roadmap':
                program=self.read('program',days,start,end,query,status,mode,limit,offset)
                progress=self.read('progress',days,start,end,query,status,mode,limit,offset)
                result.update({k:program.get(k) for k in ('program','conversation','current_session','future_plan','carry')})
                labels={s['id']:s['outcome'] for s in (result['goal'] or {}).get('skills',[])}
                result.update(skills=[dict(id=i,label=labels.get(i,i),**v) for i,v in progress['skills'].items()] if result['configured'] else [],
                              metrics=progress['metrics'],daily=progress['daily'],conversation_progress=progress.get('conversation_progress'),period=progress['filters'])
                trial=result['management'].get('trial')
                if trial and trial['value'].get('session_id'):
                    rows=self.c.legacy.get(trial['value']['session_id'])['attempts']
                    result['trial_result']=dict(independent=ratio([r for r in rows if r['assistance']=='independent']),
                                                note='Saved independent examples from this trial only; not proof of methodology effectiveness.')
                history=result['management']['history']
                if history:
                    from .instructions import contract
                    change=history[0]['value'];groups={};comparable=change['before']['goal']==change['after']['goal']
                    for side in ('before','after'):
                        cfg=change[side];digest=contract(cfg['policy'],cfg['settings'])['digest']
                        ids={d['value']['session_id'] for d in self.c.documents('coach-session-')
                             if d['value'].get('instruction_snapshot',{}).get('digest')==digest
                             and d['value'].get('goal_snapshot')==cfg['goal']}
                        rows=[a for a in self.c.legacy.observations() if a['session_id'] in ids and a['assistance']=='independent'
                              and (not progress['filters']['start'] or datetime.fromisoformat(a['occurred_at']).astimezone(TZ).date().isoformat()>=progress['filters']['start'])
                              and datetime.fromisoformat(a['occurred_at']).astimezone(TZ).date().isoformat()<=progress['filters']['end']]
                        groups[side]=dict(independent=ratio(rows),lessons=len({a['session_id'] for a in rows}))
                    result['method_comparison']=dict(**groups,comparable=comparable,at=change['at'],
                        sufficient=comparable and all(g['independent']['total']>=3 for g in groups.values()))
            elif section=='decisions':
                review=self.read('methodologist',days,start,end,query,status,mode,limit,offset)
                result.update(items=review['items'],total=review['total'],offset=review['offset'],limit=review['limit'],next_offset=review['next_offset'],health=review['health'])
            return result

    def conversation_progress(self,observations):
        allowed={a['id'] for a in observations};rows=[r for r in Conversation(self.c).rows() if r['attempt_id'] in allowed];counts={}
        for r in rows:
            for dimension in r['demonstrated']:
                c=counts.setdefault(dimension,dict(independent=0,assisted=0))
                c['independent' if r['attempt']['assistance']=='independent' else 'assisted']+=1
        return dict(dimensions=counts,annotation_count=len(rows),mode='text_conversation',note='Teacher-annotated examples, not automatic fluency or CEFR scoring.')

    @staticmethod
    def job(d):
        v=d['value'];snap=v['snapshot']
        return dict(id=d['key'],version=d['version'],created_at=d['created_at'],updated_at=d['updated_at'],status=v['status'],attempts=v['attempts'],
            error_category=v.get('error_category'),session_id=snap['session']['value']['session_id'],
            input_versions=dict(profile=snap['profile']['version'],coach_session=snap['session']['version'],original_session=snap['session_version'],methodology=snap.get('methodology')),
            observation_count=len(snap['observations']),source_counts=snap.get('source_counts'),
            result=v.get('result'),proposals=v.get('proposals',[]),applied_profile_version=v.get('applied_profile_version'))

    def detail(self,kind,ident,limit=20,offset=0):
        if not 1<=limit<=100 or offset<0:raise ValueError('Invalid detail page')
        with self.c.memory.atomic():
            value=None
            if kind=='observation':value=next((a for a in self.c.legacy.observations() if a['id']==ident),None)
            elif kind=='lesson':
                value=self.c.get_session(ident)
                value['records_page']=page(sorted(value['attempts'],key=lambda a:(a['occurred_at'],a['id']),reverse=True),limit,offset)
                value['attempts']=value['records_page']['items']
                sd=value['coach'];value['policy_recorded']=bool(sd and sd['value'].get('teaching_policy'))
                if sd and sd['value'].get('conversation'):value['conversation']=Conversation(self.c).get(ident,limit=limit,offset=offset)
            elif kind=='homework':value=Homework(self.c).get(ident)
            elif kind=='job':
                if not ident.startswith('coach-job-'):raise ValueError('Expected review ID')
                d=self.c.required(ident);value=self.job(d)
                snap=d['value']['snapshot']
                value['snapshot']=dict(goal=snap['profile']['value']['goal'],plan=snap['profile']['value']['plan'],settings=snap['profile']['value']['settings'],
                                       observations=snap['observations'],findings=(d['value'].get('result') or {}).get('findings',[]))
                after=next((p for p in self.c.history() if p['version']==d['value'].get('applied_profile_version')),None)
                value['before_plan']=snap['profile']['value']['plan'];value['after_plan']=after['value']['plan'] if after else None
                sd=self.c.required(snap['session']['key']);value['current_session_versions']=dict(original=self.c.legacy.get(snap['session']['value']['session_id'])['session']['version'],coach=sd['version'])
            elif kind=='profile_version':value=next((p for p in self.c.history() if str(p['version'])==ident),None)
            elif kind in ('phrase','material','source','discovery'):
                prefix={'phrase':'coach-lexical-','material':'coach-material-','source':'coach-source-','discovery':'coach-discovery-'}[kind]
                if not ident.startswith(prefix):raise ValueError('Unexpected document type')
                value=self.c.required(ident)
                if kind=='phrase':
                    refs={r['attempt_id'] for r in value['value']['records']};value=deepcopy(value)
                    value['records_page']=page(sorted([a for a in self.c.legacy.observations() if a['id'] in refs],key=lambda a:(a['occurred_at'],a['id']),reverse=True),limit,offset)
                    value['evidence']=value['records_page']['items']
            else:raise ValueError('Unknown detail type')
            if value is None:raise ValueError('Record not found')
            return dict(kind=kind,id=ident,learner_id=self.c.learner_id,generated_at=now(),value=value)


class AdminAction:
    def __init__(self,coach):self.c=coach

    def execute(self,action,args):
        if action.startswith('method_'):
            return self.management_action(action,args)
        fields={'settings':{'expected_version','settings'},'grammar':{'expected_version','enabled','scope','session_id','item_id'},
                'proposal':{'job_id','proposal_id','expected_version','accept'},'archive':{'source_id','expected_version'},
                'restore':{'expected_version','source_version','part'},'reveal_homework':{'homework_id','expected_version'},
                'retry':{'job_id','expected_version','expected_coach_version'},'feedback':{'attempt_id','text','expected_coach_version'}}
        if action not in fields or set(args)-fields[action]-{'idempotency_key','learner_confirmed'}:
            raise ValueError('Unexpected domain action fields')
        a=deepcopy(args);key=a.pop('idempotency_key');confirmed=a.pop('learner_confirmed',False)
        if confirmed is not True:raise ValueError('Explicit learner decision required')
        for field in ('expected_version','expected_coach_version','source_version'):
            if field in a and (type(a[field]) is not int or a[field]<1):raise ValueError('Expected a positive integer version')
        if not isinstance(key,str) or not 1<=len(key)<=128:raise ValueError('Invalid action key')
        for field in ('enabled','accept'):
            if field in a and type(a[field]) is not bool:raise ValueError('Expected an explicit boolean decision')
        # Named domain operations only; no generic document editor or queue edit.
        if action=='settings':return self.c.settings(key,a['expected_version'],a['settings'],True)
        if action=='grammar':return self.c.grammar_permission(key,a['expected_version'],a['enabled'],True,a.get('scope','future'),a.get('session_id'),a.get('item_id'))
        if action=='proposal':return self.c.decide(key,a['job_id'],a['proposal_id'],a['expected_version'],a['accept'],True)
        if action=='archive':return MaterialIntake(self.c,None,0).archive(key,a['source_id'],a['expected_version'])
        if action=='restore':return self.c.restore(key,a['expected_version'],a['source_version'],a['part'],True)
        if action=='reveal_homework':return Homework(self.c).reveal(key,a['homework_id'],a['expected_version'])
        if action=='retry':
            def retry():
                job=self.c.required(a['job_id'])
                if not a['job_id'].startswith('coach-job-') or job['value']['status'] not in ('failed','stale'):raise ValueError('Retry only a failed or stale review')
                sid=job['value']['snapshot']['session']['value']['session_id'];sd=self.c.required('coach-session-'+sid)
                if self.c.legacy.get(sid)['session']['version']!=a['expected_version'] or sd['version']!=a['expected_coach_version']:raise ValueError('Version conflict')
                return dict(job_id=self.c.enqueue_review(key,sid),status='queued')
            return self.c.request(key,'admin_retry',a,retry)
        if action=='feedback':
            def feedback():
                original=AdminRead(self.c).detail('observation',a['attempt_id'])['value'];sd=self.c.required('coach-session-'+original['session_id'])
                f=dump(Feedback.model_validate(dict(id=key_for(key)[:40],kind='other',text=a['text'])))
                value=deepcopy(sd['value']);value['feedback'].append(dict(f))
                if len(value['feedback'])>200:raise ValueError('Feedback limit reached')
                value.setdefault('feedback_links',[]).append(dict(feedback_id=f['id'],attempt_id=original['id'],at=now()))
                return self.c.memory.put(sd['key'],value,a['expected_coach_version'])
            return self.c.request(key,'admin_feedback',a,feedback)
        raise ValueError('Unknown domain action')

    def management_action(self,action,args):
        from .management import Management
        fields={
            'method_draft':{'expected_profile_version','expected_draft_version','data'},
            'method_discard':{'expected_draft_version'},
            'method_publish':{'expected_profile_version','expected_draft_version','mode'},
            'method_trial_decision':{'expected_profile_version','expected_trial_version','keep'},
            'method_restore':{'expected_profile_version','change_id'},
            'method_feedback':{'expected_profile_version','kind','text'},
            'method_feedback_review':{'expected_profile_version'},
        }
        if action not in fields or set(args)!=fields[action]|{'idempotency_key','learner_confirmed'} or args['learner_confirmed'] is not True:
            raise ValueError('Explicit named methodology action required')
        key=args['idempotency_key']
        if not isinstance(key,str) or not 1<=len(key)<=128:raise ValueError('Invalid action key')
        values={k:deepcopy(args[k]) for k in fields[action]}
        for k,v in values.items():
            if k.startswith('expected_') and (type(v) is not int or v<(0 if k=='expected_draft_version' else 1)):raise ValueError('Invalid version')
        methods={'method_draft':'save_draft','method_discard':'discard','method_publish':'publish','method_trial_decision':'trial_decision',
                 'method_restore':'restore','method_feedback':'feedback','method_feedback_review':'review_feedback'}
        return getattr(Management(self.c),methods[action])(key=key,**values)
