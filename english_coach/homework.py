"""Original foundation exercises; answers live only in the host's observation ledger."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import re
from .models import HomeworkAnswer
from . import policies


def normalize(text):
    text = text.lower().strip().replace('’', "'")
    text = text.replace("i'll", 'i will').replace("she'll", 'she will').replace("we'll", 'we will')
    return re.sub(r'[^a-z0-9 ]', '', text).strip()


def exercises(pattern, evidence):
    description = (pattern['text'] + ' ' + pattern['id']).lower()
    errors = ' '.join(str(a.get('error_type', '')) + ' ' + a.get('observation', '') for a in evidence).lower()
    future = any(w in description for w in ('future', 'will', 'будущ'))
    be = any(w in description + errors for w in ('missing_be', 'missing be', 'am/is/are', 'copula', 'связк'))
    if future:
        goal = 'В коротком ответе о будущем сохранять be и использовать базовую форму после will.'
        rows = [
            ('gap', 'Вставь одно слово: I will ___ at home tomorrow.', ['be']),
            ('repair', 'Исправь только форму: She will goes home at six.', ['She will go home at six.']),
            ('gap', 'Вставь одно слово: We ___ meeting Anna at six. Время уже согласовано.', ['are']),
            ('meaning', 'Друг просит помощи сейчас. Выбери ответ: A — I will help you. B — I helped you.', ['A', 'I will help you.']),
            ('free', 'Тебя только что попросили позвонить маме вечером. Ответь одним коротким предложением.', []),
            ('free', 'Вы с другом уже договорились поужинать завтра в семь. Напиши ему короткое сообщение.', []),
        ]
    elif be:
        goal = 'Не терять am/is/are в простых предложениях.'
        rows = [
            ('gap', 'I ___ at home.', ['am']), ('gap', 'Anna ___ ready.', ['is']),
            ('repair', 'Исправь: We happy today.', ['We are happy today.']),
            ('meaning', 'Выбери о настоящем: A — He is here. B — He was here.', ['A', 'He is here.']),
            ('free', 'Напиши, где ты сейчас, одним коротким предложением.', []),
            ('free', 'Напиши другу, что вы готовы.', []),
        ]
    elif 'past' in description and ('question' in description or 'вопрос' in description):
        goal = 'Задавать короткий вопрос о прошлом с did и базовой формой.'
        rows = [
            ('gap', '___ you call Anna yesterday?', ['Did']),
            ('repair', 'Исправь: Did he went home?', ['Did he go home?']),
            ('gap', 'Where did they ___? (go)', ['go']),
            ('meaning', 'Спроси о вчера: A — Did you call? B — Will you call?', ['A', 'Did you call?']),
            ('free', 'Спроси друга, звонил ли он маме вчера.', []),
            ('free', 'Спроси, куда Анна пошла вчера.', []),
        ]
    else:
        # No fabricated mapping of an unfamiliar pattern to a different grammar target.
        goal = 'Закрепить одну конструкцию текущего урока простыми знакомыми словами.'
        rows = [('free', prompt, []) for prompt in (
            'Вспомни одну трудную реплику урока и сформулируй её заново полностью.',
            'Скажи ту же мысль о себе одним коротким предложением.',
            'Поменяй только время или место в своей реплике. Сохрани её смысл.',
            'Составь одну короткую реплику с этой конструкцией для друга.',
            'Позже составь новую реплику для семьи, без открытого образца.',
            'Позже составь новую короткую реплику для коллеги, без образца.')]
    items = [dict(id=str(i+1), kind=kind, phase='practice' if i < 4 else 'delayed',
                  prompt=prompt, accepted=answers, pattern_id=pattern['id'])
             for i, (kind, prompt, answers) in enumerate(rows)]
    return goal, items


class Homework:
    def __init__(self, coach):
        self.c = coach

    def issue(self, sid):
        from .coach import now, key_for
        key = 'coach-homework-' + key_for(sid)
        old = self.c.memory.get(key)
        if old:
            return old
        lesson = self.c.legacy.get(sid)
        if lesson['session']['status'] != 'finished':
            raise ValueError('Finish and save the lesson before issuing homework')
        session=self.c.memory.get('coach-session-'+sid)
        policy=policies.session_selection(session,'__none__') if session else policies.choose()
        settings=session['value']['settings_snapshot'] if session else self.c.profile()['value']['settings']
        conversation=policy['id']==policies.CONVERSATION
        minutes=settings.get('homework_minutes',0 if conversation else 12)
        if conversation and not minutes: return None
        observations = lesson['attempts'][-40:]
        if not observations:
            return None  # An empty lesson supplies no evidence for personalized work.
        latest_day = max(a['occurred_at'] for a in observations)[:10]
        observations = [a for a in observations if a['occurred_at'][:10] == latest_day]
        known = {p['id']:p for p in self.c.legacy.progress()['patterns']}
        candidates = {a['pattern_id'] for a in observations if a['pattern_id'] in known}
        def priority(pid):
            aa = [a for a in observations if a['pattern_id'] == pid]
            return (sum(a['outcome']=='incorrect' and a['assistance']=='independent' for a in aa),
                    sum(a['assistance']!='independent' for a in aa), max(a['occurred_at'] for a in aa))
        pid = max(candidates, key=priority)
        evidence = [a for a in observations if a['pattern_id'] == pid]
        if conversation:
            goal='Подготовить несколько мыслей для следующего разговора по согласованной теме.'
            items=[dict(id=str(i+1),kind='free',phase='practice',prompt=prompt,accepted=[],pattern_id=pid) for i,prompt in enumerate((
                'Выбери тему прошедшего разговора и подготовь короткое мнение с одной-двумя причинами.',
                'Вспомни полезное исправление. Позже вырази похожую мысль в другой ситуации своими словами, без образца.'))]
        else:
            goal, items = exercises(known[pid], evidence)
        at = now()
        value = dict(teaching_policy=policy,kind='conversation_preparation' if conversation else 'foundation_homework',optional=conversation,lesson_id=sid, date=at[:10], issued_at=at, goal=goal,
                     minutes=minutes,
                     split='Можно подготовить мысли в удобное время; обязательных повторов нет.' if conversation else '6–8 минут сейчас; 4–7 минут после перерыва, лучше позже или завтра.',
                     delayed_not_before=(datetime.fromisoformat(at)+timedelta(minutes=10)).isoformat(),
                     basis_attempt_ids=[a['id'] for a in evidence], status='issued',
                     selection='latest_saved_day_independent_errors_then_assistance',
                     methodology_status='provisional_verified_template',
                     note='Необязательная подготовка выдана по согласованной нагрузке и сохранённому разговору.' if conversation else 'ДЗ выдано по сохранённым ответам. Применение модельного разбора проверяется отдельно.',
                     criteria=['Ясность мысли, развитие мнения и корректность по выбранному разговорному фокусу.' if conversation else 'Сначала смысл, затем целевая форма, затем понятность простых слов.',
                               'Допустимые альтернативы принимаются; повтор с помощью не является самостоятельным.',
                               'Короткая задержка не доказывает долговременное освоение.'],
                     instruction='Если хочешь проверку, пришли ID подготовки и свои мысли. Можно обсудить их в следующем разговоре; обязательного повтора нет.' if conversation else 'Пришли ID ДЗ и ответы по номерам. Можно частями и в новом чате. Закрой образец перед вторым подходом.',
                     items=items, submissions=[], exposed_items=[], practice_session_id=None,
                     video=None, video_policy='Необязательно: максимум один проверенный ролик 2–5 минут, вместо части практики, с текстовой заменой.',
                     origin='Original agreed conversation preparation' if conversation else 'Original Coach exercises; workbook formats, not copied textbook exercises')
        return self.c.memory.put(key,value,0)

    def get(self, homework_id=None):
        if homework_id:
            if not homework_id.startswith('coach-homework-'):
                raise ValueError('Expected homework ID')
            doc = self.c.required(homework_id)
        else:
            docs = self.c.documents('coach-homework-')
            if self.c.active_policy()['id']==policies.CONVERSATION:
                docs=[d for d in docs if (d['value'].get('teaching_policy') or {}).get('id')==policies.CONVERSATION]
            doc = max(docs,key=lambda d:d['created_at']) if docs else None
        if not doc:
            return None
        result = deepcopy(doc)
        for item in result['value']['items']:
            item.pop('accepted',None)
        refs = {s['attempt_id'] for s in doc['value']['submissions']}
        result['evidence'] = [a for a in self.c.legacy.observations() if a['id'] in refs][-50:]
        result['evidence_note'] = 'Last 50 linked original observations; submissions retain all references.'
        return result

    def reveal(self, key, homework_id, version):
        def action():
            doc = self.c.required(homework_id)
            if doc['version'] != version:
                raise ValueError('Version conflict')
            v = deepcopy(doc['value'])
            v['exposed_items'] = [i['id'] for i in v['items'] if i['accepted']]
            v['delayed_not_before'] = (datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()
            doc = self.c.memory.put(doc['key'],v,version)
            return dict(homework_id=homework_id,version=doc['version'],
                        answers={i['id']:i['accepted'] for i in v['items'] if i['accepted']},
                        note='Ответы показаны по запросу. Следующий ответ на эти пункты будет учитываться как выполненный с помощью.')
        return self.c.request(key,'homework_keys',dict(id=homework_id,version=version),action)

    def submit(self, key, homework_id, version, answers):
        from .coach import now, key_for
        answers = [HomeworkAnswer.model_validate(a).model_dump() for a in answers]
        if not 1 <= len(answers) <= 6 or len({a['item_id'] for a in answers}) != len(answers):
            raise ValueError('Submit 1..6 different item answers')
        def action():
            if not homework_id.startswith('coach-homework-'):
                raise ValueError('Expected homework ID')
            doc = self.c.required(homework_id)
            if doc['version'] != version:
                raise ValueError('Version conflict')
            v = deepcopy(doc['value'])
            items = {i['id']:i for i in v['items']}
            for a in answers:
                if a['item_id'] not in items:
                    raise ValueError('Unknown homework item')
                item = items[a['item_id']]
                if item['phase']=='delayed' and now() < v['delayed_not_before']:
                    raise ValueError('Delayed tasks are not due yet; submit the first approach now')
                if item['kind']=='free' and (not a['reason'] or 'unclear' in (a['meaning'],a['grammar'],a['lexis'])):
                    raise ValueError('Teacher must check meaning, target grammar and vocabulary before recording a free answer')
            session = self.c.legacy.start_homework(key_for(key,'practice'),homework_id,v['goal'])
            v['practice_session_id'] = session['id']
            receipts = []
            attempts = []
            for a in answers:
                item = items[a['item_id']]
                assisted = a['assistance']
                if a['item_id'] in v['exposed_items']:
                    assisted = 'immediate_repeat'
                match = normalize(a['text']) in {normalize(s) for s in item['accepted']}
                if item['kind']=='free':
                    correct = a['meaning']=='preserved' and a['grammar']=='correct' and a['lexis']=='acceptable'
                else:
                    if a['acceptable_alternative'] and (not a['reason'] or a['meaning']!='preserved' or a['grammar']!='correct'):
                        raise ValueError('An alternative needs an explicit meaning and grammar assessment')
                    correct = match or a['acceptable_alternative']
                outcome = 'correct' if correct else 'incorrect'
                ak = key_for(key,a['item_id'])
                assessment = dict(meaning=a['meaning'],grammar=a['grammar'],lexis=a['lexis'],
                                  reason=a['reason'] or ('Целевая форма верна.' if correct else 'Проверь целевую форму и попробуй исправить.'),
                                  assistance=assisted, template_match=match, outcome=outcome)
                # The full learner text is stored once, in the original host attempt.
                import json
                observation = json.dumps(assessment,ensure_ascii=False)
                context = a['text'] if len(a['text'])<=200 else 'Homework item '+item['id']
                if len(a['text'])>200:
                    observation = json.dumps(dict(answer=a['text'],assessment=assessment),ensure_ascii=False)
                if len(observation)>2000:
                    raise ValueError('Answer plus assessment exceeds observation budget; use a shorter reply')
                attempts.append(dict(idempotency_key=ak,pattern_id=item['pattern_id'],occurred_at=now(),
                                     outcome=outcome,assistance=assisted,context=context,
                                     mode='free' if item['phase']=='delayed' or v.get('kind')=='conversation_preparation' else 'controlled',
                                     before_warmup=item['phase']=='delayed',error_type=None if correct else 'homework_target',observation=observation))
                receipts.append(dict(item_id=a['item_id'],**assessment))
            saved = self.c.legacy.checkpoint(key_for(key,'answers'),session['id'],session['version'],attempts)
            if len(v['submissions'])+len(answers)>200:
                raise ValueError('Homework submission limit reached; discuss a fresh assignment')
            for a,aid in zip(answers,saved['attempt_ids']):
                v['submissions'].append(dict(item_id=a['item_id'],attempt_id=aid,at=now()))
            completed = {s['item_id'] for s in v['submissions']}
            v['status'] = 'checked' if completed == set(items) else 'partial'
            # Complete this separate observation batch; a later partial submission starts
            # a new homework batch. Never reopen the lesson or merge with an active lesson.
            self.c.legacy.finish(key_for(key,'finish'),session['id'],saved['version'])
            updated = self.c.memory.put(doc['key'],v,version)
            return dict(homework_id=homework_id,version=updated['version'],status=v['status'],
                        checks=receipts,remaining_items=sorted(set(items)-completed),
                        attempt_ids=saved['attempt_ids'],
                        measurement='Completion, correctness and assistance are separate; unfinished work is not an error or mastery regression.')
        return self.c.request(key,'homework_submit',dict(id=homework_id,version=version,answers=answers),action)
