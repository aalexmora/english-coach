"""Conversation setup and evidence-linked topic blocks through public host APIs.

Learner answers remain in LegacyEnglishAPI. Documents hold teaching context,
interpretation and references, never a copied attempt ledger or assessed CEFR.
"""
from copy import deepcopy
from datetime import datetime,timedelta
from uuid import uuid4
from . import policies
from .models import ConversationTopic,ConversationOnboarding,ConversationAnnotation
from .coach import now,key_for,dump
from .homework import normalize

ROUTE = [
    dict(id='dialogue',outcome='Support a conversation and ask follow-up questions'),
    dict(id='story',outcome='Tell a coherent story about an experience'),
    dict(id='opinion',outcome='Develop an opinion and explain reasons'),
    dict(id='comparison',outcome='Compare options and discuss disagreement'),
    dict(id='spontaneous',outcome='Handle a less prepared situation and clarify meaning'),
]


def suggested_topics():
    rows = [
        ('everyday','Повседневные решения','Explain a choice and respond to a follow-up',
         ['What small decision made your day better recently?','What influenced that choice?']),
        ('travel','Путешествия и впечатления','Describe an experience and what made it memorable',
         ['What place has left a lasting impression on you?','What made that experience stand out?']),
        ('culture','Книги и фильмы','Explain a personal response and discuss another view',
         ['What book or film has stayed with you lately?','What did it make you think about?']),
        ('technology','Технологии в жизни','Discuss benefits and trade-offs through an example',
         ['What technology has changed your everyday life?','What trade-off comes with using it?']),
        ('plans','Планы и возможности','Explain a future intention and weigh options',
         ['What would you like to make time for in the coming months?','What might help you get started?']),
        ('impressions','События и впечатления','Develop a thought about a recent event',
         ['What has surprised you recently?','How did it change the way you saw the situation?']),
        ('free','Свободная тема','Develop a learner-chosen topic and respond to the partner',
         ['What would you enjoy talking about today?','What would you like me to understand about it?']),
    ]
    return [dict(id=i,title=t,communicative_goal=g,questions=q,
                 criterion='Express a clear thought and respond to one content-based follow-up.',
                 correctness_focus='Select one or two consequential focuses from actual replies; none assessed yet.',status='active')
            for i,t,g,q in rows]


class Conversation:
    def __init__(self,coach):self.c=coach

    def profile(self):
        p=self.c.profile()
        if policies.selection(p)['id']!=policies.CONVERSATION or not p['value'].get('conversation'):
            raise ValueError('Configure conversation onboarding first')
        return p

    @staticmethod
    def topics(values):
        result=[dump(ConversationTopic.model_validate(t)) for t in values]
        if not 3<=len(result)<=20 or len({t['id'] for t in result})!=len(result):
            raise ValueError('Use 3..20 unique topics including free')
        if not any(t['id']=='free' and t['status']=='active' for t in result):
            raise ValueError('Keep the free topic available')
        for t in result:
            policies.check_activity(policies.choose('conversation'),'conversation',
                ' '.join([t['title'],t['communicative_goal'],t['criterion'],t['correctness_focus'],*t['questions']]))
        return result

    @staticmethod
    def plan(goal,topics,topic_ids,stage_ids):
        chosen=[next(t for t in topics if t['id']==i and t['status']=='active') for i in [*topic_ids,'free']]
        count=len(chosen);base=goal['minutes']//count;remainder=goal['minutes']%count
        items=[];bindings={}
        for n,t in enumerate(chosen):
            skill=stage_ids[n%len(stage_ids)] if t['id']!='free' else 'dialogue'
            ident='conversation-'+key_for(t['id'],skill)[:16]
            items.append(dict(id=ident,skill_id=skill,task=t['questions'][0],mechanic='conversation',
                              mechanic_version=1,status='pending',minutes=base+(n<remainder)))
            bindings[ident]=t['id']
        return items,bindings

    def onboard(self,key,expected_version,data,confirmed,topics=None):
        data=dump(ConversationOnboarding.model_validate(data))
        catalog=self.topics(topics or suggested_topics())
        if not confirmed:raise ValueError('Agree the learner goal, minutes and preferences explicitly')
        ids=data['comfortable_topic_ids']
        if 'free' in ids or not set(ids)<={t['id'] for t in catalog if t['status']=='active'}:
            raise ValueError('Choose two or three available comfortable topics, plus the free option')
        def apply():
            old=self.c.memory.get('coach-profile')
            if (old['version'] if old else 0)!=expected_version:raise ValueError('Version conflict')
            if old and (policies.selection(old)['id']!=policies.CONVERSATION or old['value'].get('conversation')):
                raise ValueError('Onboarding must not overwrite an established profile')
            if self.c.legacy.progress()['active_sessions'] or (self.c.memory.get('coach-carry') or {}).get('value',{}).get('items'):
                raise ValueError('Finish existing work before onboarding')
            skills=[]
            for stage in ROUTE:
                p=self.c.legacy.add_pattern(key_for('conversation-pattern',stage['id']),stage['outcome'])
                skills.append(dict(id=stage['id'],outcome=stage['outcome'],pattern_ids=[p['id']]))
            goal=dict(outcome=data['outcome'],minutes=data['minutes'],milestones=[s['outcome'] for s in ROUTE],skills=skills)
            p=self.c.configure(key_for(key,'goal'),goal,expected_version,True,'conversation')
            value=deepcopy(p['value'])
            value['settings'].update(correction_intensity=data['correction_intensity'],homework_minutes=data['preparation_minutes'])
            value['plan'],bindings=self.plan(goal,catalog,ids,['dialogue','story','opinion'])
            self.c.validate_plan(value['plan'],goal,policies.selection(p))
            value['conversation']=dict(phase='getting_to_know',interests=data['interests'],situations=data['situations'],
                proficiency=dict(reported=data['reported_level'],source=data['level_source'] if data['reported_level'] else None,assessed=False),
                route=deepcopy(ROUTE),route_status='provisional',topics=catalog,item_topics=bindings,
                diagnostic_evidence_ids=[],route_rationale='Provisional proposals; adapt after conversation on two or three comfortable topics.')
            return self.c.memory.put(p['key'],value,p['version'])
        return self.c.request(key,'conversation_onboard',dict(expected_version=expected_version,data=data,confirmed=confirmed,topics=catalog),apply)

    def set_topics(self,key,expected_version,topics,confirmed):
        topics=self.topics(topics)
        if not confirmed:raise ValueError('Topic additions, replacements and skips require learner agreement')
        def apply():
            p=self.profile();v=deepcopy(p['value']);conv=v['conversation']
            # Keep pending plan bindings valid when a topic is replaced or skipped.
            available={t['id']:t for t in topics if t['status']=='active'}
            for item in v['plan']:
                tid=conv['item_topics'].get(item['id'],'free')
                tid=tid if tid in available else 'free'
                conv['item_topics'][item['id']]=tid
                item['task']=available[tid]['questions'][0]
            conv['topics']=topics
            v['decision']=dict(source='user',kind='conversation_topics',at=now())
            return self.c.memory.put(p['key'],v,expected_version)
        return self.c.request(key,'conversation_topics',dict(version=expected_version,topics=topics,confirmed=confirmed),apply)

    def set_route(self,key,expected_version,stage_order,topic_ids,evidence_ids,rationale,confirmed):
        if not confirmed or set(stage_order)!={s['id'] for s in ROUTE} or len(stage_order)!=len(ROUTE):
            raise ValueError('Explicitly agree a permutation of the five communicative goals')
        if not 1<=len(topic_ids)<=2 or len(set(topic_ids))!=len(topic_ids) or 'free' in topic_ids or not 1<=len(rationale)<=1000:
            raise ValueError('Choose one or two topics and explain the observed basis')
        def apply():
            p=self.profile();v=deepcopy(p['value']);conv=v['conversation']
            rows=self.rows();by_id={r['attempt']['id']:r for r in rows}
            if not evidence_ids or len(set(evidence_ids))!=len(evidence_ids) or not set(evidence_ids)<=set(by_id):
                raise ValueError('Use original conversation evidence from this learner')
            if len({by_id[i]['topic']['id'] for i in evidence_ids})<2:
                raise ValueError('Get to know the learner on at least two comfortable topics first')
            available={t['id'] for t in conv['topics'] if t['status']=='active'}
            if not set(topic_ids)<=available:raise ValueError('Unknown or skipped topic')
            conv.update(phase='ready',route_status='agreed',route=[next(s for s in ROUTE if s['id']==i) for i in stage_order],
                        diagnostic_evidence_ids=list(evidence_ids),route_rationale=rationale)
            v['goal']['milestones']=[s['outcome'] for s in conv['route']]
            v['plan'],conv['item_topics']=self.plan(v['goal'],conv['topics'],topic_ids,stage_order)
            self.c.validate_plan(v['plan'],v['goal'],policies.selection(p))
            v['decision']=dict(source='user',kind='conversation_route',at=now(),evidence_ids=list(evidence_ids))
            return self.c.memory.put(p['key'],v,expected_version)
        return self.c.request(key,'conversation_route',dict(version=expected_version,stage_order=stage_order,topic_ids=topic_ids,evidence_ids=evidence_ids,rationale=rationale,confirmed=confirmed),apply)

    @staticmethod
    def session_context(profile,carry=None):
        conv=deepcopy(profile['value']['conversation']);by_id={t['id']:t for t in conv['topics']}
        bindings={i['id']:dict(topic=deepcopy(by_id[conv['item_topics'].get(i['id'],'free')]),
                              mode='free' if conv['item_topics'].get(i['id'])=='free' else 'planned',
                              block_id=uuid4().hex,focus_ids=[],return_to=None) for i in profile['value']['plan']}
        bindings.update(deepcopy((carry or {}).get('value',{}).get('conversation_items',{})))
        return dict(snapshot=conv,items=bindings)

    @classmethod
    def refresh_plan(cls,value):
        conv=value['conversation'];stages=[s['id'] for s in conv['route']]
        if not set(stages)<={s['id'] for s in value['goal']['skills']}:
            raise ValueError('Retain the registered communicative skills when editing this conversation goal')
        active={t['id'] for t in conv['topics'] if t['status']=='active' and t['id']!='free'}
        ids=list(dict.fromkeys(i for i in conv['item_topics'].values() if i in active))[:2]
        value['plan'],conv['item_topics']=cls.plan(value['goal'],conv['topics'],ids,stages)

    def select(self,key,sid,version,item_id,mode,topic_id,topic,confirmed):
        if not confirmed or mode not in ('planned','free','return'):raise ValueError('Explicitly choose a planned/free topic or return')
        custom=dump(ConversationTopic.model_validate(topic)) if topic else None
        if (custom and (mode!='free' or topic_id)) or (mode=='return' and (topic_id or custom)):
            raise ValueError('Choose one topic mechanism')
        def apply():
            sd=self.c.required('coach-session-'+sid);v=deepcopy(sd['value'])
            if sd['version']!=version:raise ValueError('Version conflict')
            if policies.session_selection(sd,item_id)['id']!=policies.CONVERSATION or not v.get('conversation'):
                raise ValueError('No conversation topic state in this lesson')
            practice=self.c.memory.get(v['current_practice_id']) if v.get('current_practice_id') else None
            if practice and practice['value']['stage'] not in ('awaiting_reuse','completed'):
                raise ValueError('Finish the active speaking block explicitly before changing its topic')
            sd=self.c.transition(key_for(key,'begin'),sid,version,'begin_item',item_id)
            v=deepcopy(sd['value']);binding=v['conversation']['items'][item_id];previous=deepcopy(binding)
            if mode=='return':
                if not binding.get('return_to'):raise ValueError('No planned return point')
                binding=deepcopy(binding['return_to']);binding['return_to']=None
            else:
                catalog=v['conversation']['snapshot']['topics']
                chosen=custom or next((t for t in catalog if t['id']==(topic_id or 'free') and t['status']=='active'),None)
                if not chosen:raise ValueError('Unknown or skipped topic in this lesson snapshot')
                if chosen['status']!='active':raise ValueError('Choose an active topic')
                if mode=='planned' and chosen['id']=='free':raise ValueError('Select free mode for the free topic')
                policies.check_activity(policies.choose('conversation'),'conversation',' '.join([chosen['communicative_goal'],chosen['criterion'],chosen['correctness_focus'],*chosen['questions']]))
                binding=dict(topic=deepcopy(chosen),mode=mode,block_id=uuid4().hex,focus_ids=[],
                             return_to=((binding.get('return_to') or previous) if previous['mode']=='planned' else binding.get('return_to')) if mode=='free' else None)
            v['conversation']['items'][item_id]=binding
            v['current_practice_id']=None
            v.setdefault('topic_choices',[]).append(dict(item_id=item_id,mode=mode,topic_id=binding['topic']['id'],at=now()))
            return self.c.memory.put(sd['key'],v,sd['version'])
        return self.c.request(key,'conversation_select',dict(sid=sid,version=version,item_id=item_id,mode=mode,topic_id=topic_id,topic=custom,confirmed=confirmed),apply)

    def rows(self,sid=None):
        observations={a['id']:a for a in (self.c.legacy.get(sid)['attempts'] if sid else self.c.legacy.observations())}
        rows=[]
        for doc in self.c.documents('coach-conversation-block-'):
            b=doc['value']
            if sid and b['session_id']!=sid:continue
            for r in b['records']:
                if r['attempt_id'] in observations:
                    rows.append(dict(r,attempt=observations[r['attempt_id']],topic=b['topic'],block_id=b['block_id'],session_id=b['session_id'],skill_id=b['skill_id']))
        return sorted(rows,key=lambda r:(r['attempt']['occurred_at'],r['attempt_id']))

    def save_block(self,key,sid,version,coach_version,attempts,annotations,save_requested):
        annotations=[dump(ConversationAnnotation.model_validate(a)) for a in annotations]
        if not save_requested:raise ValueError('Save only at an explicitly requested conversation checkpoint')
        keys=[a['idempotency_key'] for a in attempts]
        if not 1<=len(keys)<=20 or len(set(keys))!=len(keys) or {a['attempt_key'] for a in annotations}!=set(keys) or len(annotations)!=len(keys):
            raise ValueError('Annotate each supplied original reply once; maximum 20')
        def apply():
            sd=self.c.required('coach-session-'+sid)
            if sd['version']!=coach_version or not sd['value'].get('conversation'):raise ValueError('Reload conversation session state')
            policy=policies.session_selection(sd)
            if policy['id']!=policies.CONVERSATION:raise ValueError('Conversation policy required')
            item=next((i for i in sd['value']['items'] if i['id']==sd['value']['current_item_id'] and i['status']!='done'),None)
            if not item:raise ValueError('Begin the actual conversation item first')
            binding=sd['value']['conversation']['items'][item['id']]
            # Persist each bounded checkpoint separately while retaining the
            # same topic block and its correction-focus limit across saves.
            document_key='coach-conversation-block-'+key_for(sid,binding['block_id'],key)[:40]
            records=[]
            previous=self.rows();corrections={r['correction']['id']:r for r in previous if r.get('correction')}
            exposures=[r['correction'] for r in corrections.values()]
            annotated={a['attempt_key']:a for a in annotations};known={a['id'] for a in self.c.legacy.get(sid)['attempts']}
            focuses=set(binding['focus_ids']);links=next(s['pattern_ids'] for s in self.c.profile()['value']['goal']['skills'] if s['id']==item['skill_id'])
            for a in sorted(attempts,key=lambda a:datetime.fromisoformat(a['occurred_at'])):
                note=annotated[a['idempotency_key']];correction=note['correction']
                if a['pattern_id'] not in links or a['mode']!='free' or not a.get('observation','').strip():
                    raise ValueError('Save actual free-conversation replies linked to this communicative skill')
                if a['outcome']=='ambiguous' and note['demonstrated']:raise ValueError('Clarify ambiguous meaning before claiming a demonstrated skill')
                if 'focus_accuracy' in note['demonstrated'] and a['outcome']!='correct':raise ValueError('Target-focus correctness needs a correct original observation')
                if correction:
                    if not correction['meaning_preserved'] or a['outcome']=='ambiguous' or normalize(a['observation'])==normalize(correction['corrected_text']):
                        raise ValueError('Review meaning and an actual wording change before correcting')
                    if correction['kind']=='actual_error' and a['outcome']!='incorrect':raise ValueError('An optional alternative is not an actual error')
                    if not datetime.fromisoformat(a['occurred_at'])<=datetime.fromisoformat(correction['occurred_at'])<=datetime.fromisoformat(now()):
                        raise ValueError('Record the actual correction time after the reply and before saving')
                    focuses.add(correction['focus_id'])
                if a['assistance']=='independent' and any(normalize(a['observation'])==normalize(exposure['corrected_text']) and
                    timedelta(0)<=datetime.fromisoformat(a['occurred_at'])-datetime.fromisoformat(exposure['at'])<timedelta(minutes=10)
                    for exposure in exposures):raise ValueError('Immediate imitation is assisted, not independent')
                if note['reused_from']:
                    prior=corrections.get(note['reused_from'])
                    if not prior or a['assistance']!='independent' or a['outcome']!='correct' or a['context']==prior['attempt']['context'] or datetime.fromisoformat(a['occurred_at'])<datetime.fromisoformat(prior['correction']['at'])+timedelta(minutes=10):
                        raise ValueError('Reuse needs original independent evidence later in a different situation')
                    if 'delayed_reuse' not in note['demonstrated']:raise ValueError('Label the explicitly observed delayed reuse')
                elif 'delayed_reuse' in note['demonstrated']:raise ValueError('Link delayed reuse to a saved correction')
                if correction:exposures.append(dict(corrected_text=correction['corrected_text'],at=correction['occurred_at']))
            if len(focuses)>2:raise ValueError('Choose at most two correction focuses per conversation block')
            saved=self.c.save(key_for(key,'checkpoint'),sid,version,attempts)
            originals={a['idempotency_key']:a for a in self.c.legacy.get(sid)['attempts']}
            for a in attempts:
                original=originals[a['idempotency_key']]
                if original['id'] in known:raise ValueError('This reply was already saved; annotate it through its original checkpoint')
                note=deepcopy(annotated[a['idempotency_key']]);note.pop('attempt_key')
                if note['correction']:note['correction'].update(id=key_for(sid,original['id'],'correction'),at=note['correction'].pop('occurred_at'))
                records.append(dict(attempt_id=original['id'],**note))
            block=dict(learner_id=self.c.learner_id,session_id=sid,block_id=binding['block_id'],item_id=item['id'],skill_id=item['skill_id'],topic=deepcopy(binding['topic']),mode=binding['mode'],teaching_policy=policy,records=records)
            doc=self.c.memory.put(document_key,block,0)
            latest=self.c.required(sd['key']);v=deepcopy(latest['value']);v['conversation']['items'][item['id']]['focus_ids']=sorted(focuses)
            latest=self.c.memory.put(sd['key'],v,latest['version'])
            return dict(saved=True,session_version=saved['version'],coach_version=latest['version'],block=doc,
                        instruction='Continue the topic. A saved correction is teacher wording, not learner success.')
        return self.c.request(key,'conversation_checkpoint',dict(sid=sid,version=version,coach_version=coach_version,attempts=attempts,annotations=annotations,save_requested=save_requested),apply)

    def freeze_summary(self,sid):
        sd=self.c.required('coach-session-'+sid)
        if not sd['value'].get('conversation'):return None
        key='coach-conversation-summary-'+key_for(sid)[:40]
        old=self.c.memory.get(key)
        if old:return old
        rows=self.rows(sid);p=self.profile();conv=p['value']['conversation']
        independent=[dict(attempt_id=r['attempt']['id'],demonstrated=r['demonstrated']) for r in rows if r['attempt']['assistance']=='independent' and r['demonstrated']]
        corrections=[r['correction']['id'] for r in rows if r.get('correction')][-3:]
        planned=next((t for t in conv['topics'] if t['id']==next(iter(conv['item_topics'].values()),'free')),None)
        return self.c.memory.put(key,dict(session_id=sid,teaching_policy=policies.session_selection(sd,'__none__'),
            mode='text_conversation',independent_examples=independent[-5:],independent_example_total=len(independent),correction_ids=corrections,
            next_topic_proposal=deepcopy(planned),proposal_status='proposed_at_finish',
            evidence_ids=[r['attempt']['id'] for r in rows][-40:],total_records=len(rows),created_at=now(),
            interpretation='Last five independent examples, last three corrections and up to 40 basis references; full replies remain in paginated conversation history. Not fluency, CEFR, pronunciation or completion certification.'),0)

    def get(self,sid=None,limit=20,offset=0):
        if not 1<=limit<=100 or offset<0:raise ValueError('Invalid pagination')
        session=self.c.required('coach-session-'+sid) if sid else None
        if session:
            self.c.legacy.get(sid)
            if policies.session_selection(session,'__none__')['id']!=policies.CONVERSATION:
                raise ValueError('This lesson uses a different teaching policy')
        p=self.c.memory.get('coach-profile')
        current=bool(p and p['value'].get('conversation'))
        historical=(session or {}).get('value',{}).get('conversation')
        if not current and not historical:
            return dict(configured=False,available=not p or policies.selection(p)['id']==policies.CONVERSATION,
                        suggested_topics=suggested_topics(),suggested_route=deepcopy(ROUTE),
                        next_action='Ask interests, communication situations, correction preferences and agreed minutes one question at a time; then confirm the goal. No learner level is assessed.')
        conv=historical['snapshot'] if historical else p['value']['conversation'];rows=self.rows(sid)
        progress={k:dict(independent=0,assisted=0,evidence_ids=[]) for k in ('maintains_dialogue','develops_idea','asks_clarification','paraphrases','focus_accuracy','delayed_reuse')}
        for r in rows:
            for dimension in r['demonstrated']:
                progress[dimension]['independent' if r['attempt']['assistance']=='independent' else 'assisted']+=1
                progress[dimension]['evidence_ids'].append(r['attempt']['id'])
        for count in progress.values():count['evidence_ids']=count['evidence_ids'][-50:]
        summary=self.c.memory.get('coach-conversation-summary-'+key_for(sid)[:40]) if sid else None
        correction_rows=[r for r in rows if r.get('correction')]
        targets=[]
        for focus in dict.fromkeys(r['correction']['focus_id'] for r in reversed(correction_rows) if r['correction']['kind']=='actual_error'):
            rr=[r for r in correction_rows if r['correction']['focus_id']==focus and r['correction']['kind']=='actual_error']
            targets.append(dict(focus_id=focus,evidence_ids=[r['attempt']['id'] for r in rr][-10:],instruction='Revisit naturally in a different situation; independent reuse is still to be checked.'))
        return dict(configured=current,session_available=bool(historical),profile_version=p['version'] if p else None,learner_id=self.c.learner_id,conversation=deepcopy(conv),
                    mode='text_conversation',records=rows[offset:offset+limit],total=len(rows),next_offset=offset+limit if offset+limit<len(rows) else None,
                    progress=progress,summary=summary,next_conversation=(dict(plan=deepcopy(p['value']['plan']),verification_targets=targets[:2],free_topic_available=True) if current else None),
                    interpretation='Teacher-annotated original replies with dates and assistance. Counts cover matching history; each dimension lists its last 50 references. No fluency, CEFR, speech timing or pronunciation measurements.')

    def review_context(self,sid,allowed_ids):
        rows=self.rows(sid)
        return dict(records=[{k:v for k,v in r.items() if k!='attempt'} for r in rows if r['attempt']['id'] in allowed_ids][-10:],
                    limit=10,total=len(rows),
                    instruction='Use topic goals, actual saved replies and demonstrated dimensions to adapt the next conversation within the agreed goal; annotations are teacher interpretation. No invented CEFR or completion.')
