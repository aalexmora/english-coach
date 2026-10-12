"""Personal methodology workflows over MemoryAPI. No extra storage or attempts."""
from copy import deepcopy
import re
from pydantic import ValidationError
from . import policies
from .models import Goal
from .instructions import contract,example,FEEDBACK_NAMES

DRAFT='coach-method-draft'
TRIAL='coach-method-trial'
CHANGES='coach-method-change-'
FEEDBACK='coach-method-feedback-'


def rule_error(text):return dict(ok=False,issues=[text])


class Management:
    def __init__(self,coach):self.c=coach

    def current_config(self,p=None):
        p=p or self.c.profile();v=p['value']
        return dict(policy=policies.selection(p),settings=deepcopy(v['settings']),goal=deepcopy(v['goal']))

    def validate(self,data):
        if not isinstance(data,dict) or set(data)!={'policy_id','grammar_exercises','settings','minutes'}:
            return rule_error('Проверьте настройки методики.')
        try:
            policy=policies.choose(data['policy_id'])
            if type(data['grammar_exercises']) is not bool:raise ValueError()
            policy['grammar_exercises']=data['grammar_exercises'];policies.checked(policy)
            settings=policies.settings_for(policy,data['settings'])
            if type(data['minutes']) is not int or not 5<=data['minutes']<=120:raise ValueError()
        except (ValidationError,ValueError,KeyError,TypeError):
            return rule_error('Выберите поддерживаемый формат и нагрузку. Базовая методика сохраняет простую лексику и ДЗ 10–15 минут; упражнения в разговоре требуют разрешения.')
        text=settings['instructions'].lower()
        expressions=[r'(?:завершай|заканчивай|finish)\s+(?:урок\s+)?(?:через|после|after)\s+\d']
        if policy['id']==policies.FOUNDATION:
            expressions.append(r'(?:используй|давай|teach|use)\s+(?:сложн\w*\s+(?:слов\w*|лексик\w*)|advanced\s+(?:words|idioms))')
        if policy['id']==policies.CONVERSATION and not policy['grammar_exercises']:
            expressions.append(r'(?:давай|включи|give|use)\s+(?:грамматическ\w*\s+(?:задани\w*|упражнен\w*)|grammar\s+(?:drills|exercises))')
        for expression in expressions:
            if any(not re.search(r'\b(?:не|not|never)\s*$',text[max(0,m.start()-12):m.start()]) for m in re.finditer(expression,text)):
                return rule_error('Это пожелание противоречит правилам выбранной методики. Проверьте базовую лексику, разрешение упражнений и окончание урока только по вашей просьбе.')
        return dict(ok=True,policy=policy,settings=settings,minutes=data['minutes'])

    def read(self):
        from .coach import now
        from .methodologist import provider_system
        with self.c.memory.atomic():
            p=self.c.memory.get('coach-profile')
            catalog=[dict(id=i,name=info['name'],version=policies.VERSIONS[i],rules=contract(policies.choose(i),policies.defaults(policies.choose(i)))['teacher']['rules']) for i,info in policies.REGISTRY.items()]
            if not p:return dict(configured=False,catalog=catalog,draft=None,trial=None,history=[],feedback=[])
            config=self.current_config(p);future=contract(config['policy'],config['settings'])
            active=self.c.legacy.progress()['active_sessions']
            sd=self.c.memory.get('coach-session-'+active[0]['id']) if active else None
            current=None
            if sd:
                saved=sd['value'].get('instruction_snapshot')
                current=dict(session_id=sd['value']['session_id'],recorded=bool(saved),snapshot=deepcopy(saved),
                             policy=policies.session_selection(sd,'__none__'),trial_id=sd['value'].get('method_trial_id'))
            trial=self.c.memory.get(TRIAL)
            changes=sorted(self.c.documents(CHANGES),key=lambda d:d['updated_at'],reverse=True)
            feedback=sorted(self.c.documents(FEEDBACK),key=lambda d:d['created_at'],reverse=True)
            draft=self.c.memory.get(DRAFT)
            return dict(configured=True,catalog=catalog,profile_version=p['version'],goal=config['goal'],future=future,current=current,
                        draft=deepcopy(draft),trial=deepcopy(trial),history=changes[:20],feedback=feedback[:20],
                        review=dict(rules=['Разбирать реальные сохранённые ответы; помощь учитывать отдельно.',
                                           'Проверять трудности позже в другой ситуации; при малом числе ответов уточнять, а не заявлять освоение.',
                                           'Объяснять изменения плана; новую цель и нагрузку предлагать на согласование.',
                                           'Отвечать на отзывы о методике и объяснять следующее действие.'],
                                    exact=provider_system(dict(profile=p)),wishes=config['settings']['instructions']),
                        verification=dict(status='not_recorded',label='Выполнение правил по сохранённым репликам пока не проверено.',
                                          note='Включение инструкций в урок не доказывает их выполнение.'),generated_at=now())

    def save_draft(self,key,expected_profile_version,expected_draft_version,data):
        from .coach import now
        parsed=self.validate(data)
        if not parsed['ok']:return parsed
        def apply():
            p=self.c.profile()
            if p['version']!=expected_profile_version:raise ValueError('Version conflict')
            goal=deepcopy(p['value']['goal']);goal['minutes']=parsed['minutes'];Goal.model_validate(goal)
            value=dict(status='draft',base_profile_version=p['version'],policy=parsed['policy'],settings=parsed['settings'],goal=goal,
                       preview=example(parsed['policy'],parsed['settings']),instructions=contract(parsed['policy'],parsed['settings']),saved_at=now())
            return dict(ok=True,draft=self.c.memory.put(DRAFT,value,expected_draft_version))
        return self.c.request(key,'method_draft',dict(expected_profile_version=expected_profile_version,expected_draft_version=expected_draft_version,data=data),apply)

    def discard(self,key,expected_draft_version):
        def apply():
            d=self.c.required(DRAFT);v=deepcopy(d['value']);v['status']='discarded'
            return dict(ok=True,draft=self.c.memory.put(DRAFT,v,expected_draft_version))
        return self.c.request(key,'method_discard',dict(expected_draft_version=expected_draft_version),apply)

    def _publish(self,p,target,key,reason):
        from .coach import now,key_for
        before=self.current_config(p)
        if before['policy']['id']!=target['policy']['id']:
            self.c.configure(key_for(key,'configure'),target['goal'],p['version'],True,target['policy']['id'])
            p=self.c.profile()
        value=deepcopy(p['value']);value['settings']=policies.settings_for(target['policy'],target['settings'])
        value['teaching_policy']=policies.checked(target['policy']);value['goal']=deepcopy(target['goal'])
        items=deepcopy(value['plan']);total=sum(i.get('minutes',1) for i in items)
        for i in items:
            i['mechanic']=value['settings']['preferred_mechanic'];i['mechanic_version']=1
            if total>value['goal']['minutes']:i['minutes']=max(1,int(i.get('minutes',1)*value['goal']['minutes']/total))
        value['plan']=items;self.c.validate_plan(items,value['goal'],target['policy'])
        value['decision']=dict(source='user',kind='methodology',reason=reason,at=now())
        saved=self.c.memory.put('coach-profile',value,p['version'])
        change=self.c.memory.put(CHANGES+key_for(key)[:32],dict(before=before,after=deepcopy(target),reason=reason,at=now(),profile_version=saved['version']),0)
        return saved,change

    def publish(self,key,expected_profile_version,expected_draft_version,mode):
        from .coach import now,key_for
        if mode not in ('future','trial'):raise ValueError('Unknown publication mode')
        def apply():
            p=self.c.profile();d=self.c.required(DRAFT)
            if p['version']!=expected_profile_version or d['version']!=expected_draft_version or d['value']['base_profile_version']!=p['version']:raise ValueError('Version conflict')
            if d['value']['status']!='draft':raise ValueError('Draft not active')
            trial=self.c.memory.get(TRIAL)
            if trial and trial['value']['status'] in ('waiting','running'):return rule_error('Сначала завершите или отмените текущую пробу.')
            target={k:deepcopy(d['value'][k]) for k in ('policy','settings','goal')}
            current=self.current_config(p)
            if target['policy']['id']!=current['policy']['id'] and (self.c.legacy.progress()['active_sessions'] or (self.c.memory.get('coach-carry') or {}).get('value',{}).get('items')):
                return rule_error('Для смены полной методики сначала завершите текущую работу и перенесённые пункты. Черновик сохранён.')
            if mode=='trial':
                if target['policy']['id']!=current['policy']['id'] or target['goal']!=current['goal']:
                    return rule_error('Для пробного урока меняйте личные настройки текущей методики; цель и время урока сохраняйте прежними.')
                items=deepcopy((self.c.memory.get('coach-carry') or {}).get('value',{}).get('items') or p['value']['plan'])
                for item in items:item['mechanic']=target['settings']['preferred_mechanic']
                if any(not policies.compatible(target['policy'],item) for item in items):
                    return rule_error('Пробные правила не подходят к перенесённым заданиям. Сначала завершите их или сохраните правила для следующих занятий.')
                t=self.c.memory.put(TRIAL,dict(id=key_for(key)[:32],status='waiting',config=target,base_profile_version=p['version'],created_at=now(),session_id=None),trial['version'] if trial else 0)
                result=dict(ok=True,trial=t)
            else:
                saved,change=self._publish(p,target,key,'Правила изменены по вашему решению')
                result=dict(ok=True,profile_version=saved['version'],change=change)
            value=deepcopy(d['value']);value['status']='scheduled' if mode=='trial' else 'published'
            self.c.memory.put(DRAFT,value,d['version']);return result
        return self.c.request(key,'method_publish',dict(expected_profile_version=expected_profile_version,expected_draft_version=expected_draft_version,mode=mode),apply)

    def lesson_config(self,p):
        """Only called inside the named start workflow, never on reads."""
        config=self.current_config(p);t=self.c.memory.get(TRIAL)
        if t and t['value']['status']=='waiting':
            if t['value']['base_profile_version']==p['version']:return deepcopy(t['value']['config']),t
            v=deepcopy(t['value']);v['status']='outdated';self.c.memory.put(TRIAL,v,t['version'])
        return config,None

    def begin_trial(self,t,sid):
        if t:
            v=deepcopy(t['value']);v.update(status='running',session_id=sid);self.c.memory.put(TRIAL,v,t['version'])

    def end_trial(self,sid):
        from .coach import now
        t=self.c.memory.get(TRIAL)
        if t and t['value']['status']=='running' and t['value']['session_id']==sid:
            v=deepcopy(t['value']);v.update(status='finished',finished_at=now());self.c.memory.put(TRIAL,v,t['version'])

    def trial_decision(self,key,expected_profile_version,expected_trial_version,keep):
        if type(keep) is not bool:raise ValueError('Explicit trial decision required')
        def apply():
            p=self.c.profile();t=self.c.required(TRIAL)
            if p['version']!=expected_profile_version or t['version']!=expected_trial_version:raise ValueError('Version conflict')
            if t['value']['status'] not in ('waiting','finished'):return rule_error('Решение о постоянных правилах доступно после завершения пробного урока.')
            if keep and t['value']['status']!='finished':return rule_error('Сначала проведите пробный урок.')
            result=dict(ok=True)
            if keep:
                target=deepcopy(t['value']['config']);target['goal']=deepcopy(p['value']['goal'])
                if target['policy']['id']!=policies.selection(p)['id']:return rule_error('Методика уже изменилась. Создайте новый черновик.')
                saved,change=self._publish(p,target,key,'Пробный вариант оставлен по вашему решению');result.update(profile_version=saved['version'],change=change)
            v=deepcopy(t['value']);v['status']='kept' if keep else 'returned';self.c.memory.put(TRIAL,v,t['version']);return result
        return self.c.request(key,'method_trial_decision',dict(expected_profile_version=expected_profile_version,expected_trial_version=expected_trial_version,keep=keep),apply)

    def restore(self,key,expected_profile_version,change_id):
        if not isinstance(change_id,str) or not change_id.startswith(CHANGES):raise ValueError('Unknown methodology change')
        def apply():
            p=self.c.profile()
            if p['version']!=expected_profile_version:raise ValueError('Version conflict')
            target=deepcopy(self.c.required(change_id)['value']['before'])
            trial=self.c.memory.get(TRIAL)
            if trial and trial['value']['status'] in ('waiting','running'):return rule_error('Сначала завершите или отмените текущую пробу.')
            if target['policy']['id']!=policies.selection(p)['id'] and (self.c.legacy.progress()['active_sessions'] or (self.c.memory.get('coach-carry') or {}).get('value',{}).get('items')):return rule_error('Смена полной методики требует завершения текущей работы.')
            saved,change=self._publish(p,target,key,'Возвращены предыдущие правила по вашему решению')
            return dict(ok=True,profile_version=saved['version'],change=change)
        return self.c.request(key,'method_restore',dict(expected_profile_version=expected_profile_version,change_id=change_id),apply)

    def feedback(self,key,expected_profile_version,kind,text):
        from .coach import now,key_for
        if kind not in FEEDBACK_NAMES or not isinstance(text,str) or len(text)>1000:raise ValueError('Invalid methodology feedback')
        def apply():
            p=self.c.profile()
            if p['version']!=expected_profile_version:raise ValueError('Version conflict')
            active=self.c.legacy.progress()['active_sessions'];sid=active[0]['id'] if active else None
            return dict(ok=True,feedback=self.c.memory.put(FEEDBACK+key_for(key)[:32],dict(kind=kind,text=text.strip() or FEEDBACK_NAMES[kind],
                profile_version=p['version'],policy=policies.selection(p),status='pending',session_id=sid,created_at=now()),0))
        return self.c.request(key,'method_feedback',dict(expected_profile_version=expected_profile_version,kind=kind,text=text),apply)

    def pending_feedback(self):
        docs=sorted([d for d in self.c.documents(FEEDBACK) if d['value']['status']=='pending'],key=lambda d:d['created_at'])[:3]
        return [dict(id=d['key'],version=d['version'],kind=d['value']['kind'],text=d['value']['text'],profile_version=d['value']['profile_version']) for d in docs]

    def answer_feedback(self,responses,job_id):
        from .coach import now
        for response in responses:
            d=self.c.required(response['feedback_id']);v=deepcopy(d['value'])
            if v['status']=='pending':
                v.update(status='answered',response=response,job_id=job_id,answered_at=now());self.c.memory.put(d['key'],v,d['version'])

    def review_feedback(self,key,expected_profile_version):
        def apply():
            if self.c.profile()['version']!=expected_profile_version:raise ValueError('Version conflict')
            if not self.pending_feedback():return rule_error('Нет ожидающих отзывов.')
            sessions=[s for s in self.c.legacy.sessions() if self.c.memory.get('coach-session-'+s['id'])]
            if not sessions:return rule_error('Сначала проведите и сохраните урок. Отзыв уже сохранён.')
            sid=max(sessions,key=lambda s:s['created_at'])['id']
            return dict(ok=True,job_id=self.c.enqueue_review(key,sid),status='queued')
        return self.c.request(key,'method_feedback_review',dict(expected_profile_version=expected_profile_version),apply)
