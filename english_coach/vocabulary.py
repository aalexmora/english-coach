"""Policy-selected lexical targets linked to original observations."""
from copy import deepcopy
from datetime import datetime, timedelta
import re
from . import policies
from .homework import normalize


class Vocabulary:
    def __init__(self, coach):
        self.c = coach

    def context(self, policy=None):
        policy=policy or self.c.active_policy()
        docs = self.c.documents('coach-lexical-')
        return dict(level=policies.definition(policy)['vocabulary'],targets=[dict(id=d['key'],version=d['version'],phrase=d['value']['phrase'],
                                              meaning=d['value']['meaning'],state=d['value']['state'],
                                              independent_uses=d['value'].get('independent_uses',0),independent_total=d['value'].get('independent_total',0),assisted_total=d['value'].get('assisted_total',0)) for d in docs][-12:],
                    interpretation='Evidence-linked pilot states; not a vocabulary size estimate or mastery certification.',
                    rule='Select useful natural expressions; no compulsory lexical drills. Hide the phrase in later independent checks.' if policy['id']==policies.CONVERSATION else 'At most one new simple phrase per lesson; none during difficult grammar repair. Hide the phrase in independent prompts.')

    def teach(self,key,sid,version,phrase,meaning,basic_reviewed):
        from .coach import key_for, now
        target = 'coach-lexical-'+key_for(normalize(phrase))
        def action():
            session = self.c.required('coach-session-'+sid)
            if session['version']!=version or session['value']['phase'] not in ('active','branch'):
                raise ValueError('Expected current active lesson version')
            policy=policies.session_selection(session)
            basic=policy['id']==policies.FOUNDATION
            pattern=r"[A-Za-z][A-Za-z '\-]{0,79}" if basic else r"[A-Za-z][A-Za-z ,;:'!?\-]{0,159}"
            if not basic_reviewed or not re.fullmatch(pattern,phrase) or len(phrase.split())>(5 if basic else 12) or not 1<=len(meaning)<=200:
                raise ValueError('Review a short BASIC phrase and its meaning before teaching; no complex chunks or idioms' if basic else 'Review a useful natural expression and meaning before teaching')
            old = self.c.memory.get(target)
            if not old:
                limit=session['value']['settings_snapshot'].get('new_phrases_per_lesson',1)
                repair=any(p['value']['current_session_id']==sid and p['value']['stage'] in ('repair','reproduce','task_retry') for p in self.c.documents('coach-practice-'))
                count=sum(d['value']['origin_session_id']==sid for d in self.c.documents('coach-lexical-'))
                if repair or count>=limit:
                    raise ValueError('New phrase budget exhausted or grammar repair pending; use familiar words')
                value=dict(teaching_policy=policy,phrase=phrase,meaning=meaning,origin_session_id=sid,source='teacher_basic_review' if basic else 'teacher_natural_language_review',
                           state='seen',records=[],independent_uses=0,first_taught_at=now())
            else:
                value=deepcopy(old['value'])
            value['last_exposed_at']=now()
            value['teaching_note']='Explain briefly in the conversation; no compulsory repetition. Later independent reuse must hide the expression.' if not basic else 'Explain the meaning briefly, give one simple example, then one assisted use. A later check must hide the phrase.'
            return self.c.memory.put(target,value,old['version'] if old else 0)
        return self.c.request(key,'lexical_teach',dict(sid=sid,version=version,phrase=phrase,meaning=meaning,basic_reviewed=basic_reviewed),action)

    def record(self,key,target,version,attempt_id,kind,situation,lexically_correct):
        from .coach import now
        if not target.startswith('coach-lexical-') or kind not in ('understood','assisted','independent','transferred') or not 1<=len(situation)<=100:
            raise ValueError('Expected lexical target, evidence kind and short situation label')
        def action():
            doc=self.c.required(target)
            if doc['version']!=version:
                raise ValueError('Version conflict')
            attempt=next((a for a in self.c.legacy.observations() if a['id']==attempt_id),None)
            if not attempt:
                raise ValueError('Lexical evidence needs an actual original observation')
            v=deepcopy(doc['value'])
            if datetime.fromisoformat(attempt['occurred_at'])<datetime.fromisoformat(v['first_taught_at']):
                raise ValueError('Evidence predates teaching this phrase')
            if kind in ('independent','transferred'):
                if attempt['assistance']!='independent' or (lexically_correct and normalize(v['phrase']) not in normalize(attempt['context']+' '+attempt['observation'])):
                    raise ValueError('Independent phrase use needs unassisted original wording')
                if datetime.fromisoformat(attempt['occurred_at'])<datetime.fromisoformat(v['last_exposed_at'])+timedelta(minutes=10):
                    raise ValueError('Phrase was exposed recently; record assisted use and verify later without a model')
            if kind=='assisted' and attempt['assistance']=='independent':
                raise ValueError('Record actual assistance in the original observation first')
            if any(r['attempt_id']==attempt_id for r in v['records']):
                raise ValueError('Observation already linked to this phrase')
            v['records'].append(dict(attempt_id=attempt_id,kind=kind,situation=situation,at=attempt['occurred_at'],lexically_correct=lexically_correct))
            eligible=[r for r in v['records'] if r['kind'] in ('independent','transferred')]
            independent=sorted([r for r in eligible if r.get('lexically_correct',True)],key=lambda r:r['at'])
            dates={r['at'][:10] for r in independent};contexts={r['situation'] for r in independent}
            transfers=[r for r in independent if r['kind']=='transferred']
            if kind=='transferred' and not any(r['situation']!=situation for r in v['records'] if r['attempt_id']!=attempt_id):
                raise ValueError('Transfer requires a different previously practiced situation')
            active=len(independent)>=3 and len(dates)>=2 and len(contexts)>=2 and bool(transfers)
            later_week=bool(independent) and datetime.fromisoformat(independent[-1]['at'])-datetime.fromisoformat(independent[0]['at'])>=timedelta(days=7)
            v.update(state='stable' if active and later_week else 'active' if active else kind if lexically_correct else v['state'],
                     independent_uses=len(independent),independent_total=len(eligible),assisted_total=sum(r['kind']=='assisted' for r in v['records']),last_observed_at=now(),
                     interpretation='Pilot operational evidence threshold; grammar accuracy and certified mastery are separate.')
            return self.c.memory.put(target,v,version)
        return self.c.request(key,'lexical_record',dict(target=target,version=version,attempt_id=attempt_id,kind=kind,situation=situation,lexically_correct=lexically_correct),action)
