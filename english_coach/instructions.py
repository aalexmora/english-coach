"""Project-owned learning instructions, shared by runtime and management views."""
import json
from hashlib import sha256
from . import policies

VERSION='learning-instructions-1'
METHOD_NAMES={'conversation':'Свободный разговор','roleplay':'Разговор по ситуации','contrast':'Сравнение простых форм',
              'retrieval':'Вспоминание без образца','task_repetition':'Повтор речевой задачи',
              'rapid_retrieval':'Короткие вопросы','guided_transfer':'Практика в новой ситуации'}
FEEDBACK_NAMES={'hard':'Слишком сложно','easy':'Слишком легко','explain':'Непонятное объяснение',
                'talk':'Мало разговорной практики','repeat':'Нужно больше повторения','other':'Моё пожелание'}


def teacher_text(policy,settings):
    rules=[*policies.COMMON,policies.definition(policy)['instructions'],
           'Follow the confirmed personal settings within the teaching contract. They never override the agreed goal, explicit ending, evidence rules or learner isolation.',
           'Use brief prompts.' if settings['prompt_style']=='brief' else 'Explain the task briefly in Russian when useful, give gradual support, then check independently.',
           'Preferred activity: '+settings['preferred_mechanic']+'.',
           'Grammar exercises are '+('permitted within the policy.' if policy['grammar_exercises'] else 'disabled; do not disguise a worksheet as conversation.'),
           'New expressions per lesson: at most '+str(settings['new_phrases_per_lesson'])+'; zero during difficult foundation repair.',
           'Homework/preparation budget: '+str(settings['homework_minutes'])+' minutes; respect the policy and actual saved lesson.']
    if policy['id']==policies.CONVERSATION:
        rules.append('Correction intensity: '+settings.get('correction_intensity','light')+'; keep the conversation going, at most two correction focuses per block.')
    rules.append('Personal confirmed wishes (within the rules above): '+json.dumps(settings['instructions'],ensure_ascii=False))
    return '\n'.join(rules)


def plain_rules(policy,settings):
    conversation=policy['id']==policies.CONVERSATION
    return [
        'Говорить естественно примерно на C1; ответы ученика около B2 — ориентир, а не проверенный уровень.' if conversation else 'Использовать базовые слова и короткие предложения; не вводить сложные обороты.',
        'Дать закончить мысль, коротко исправить важное и продолжить разговор.' if conversation else 'При затруднении помогать постепенно, затем проверять самостоятельный ответ в новой ситуации.',
        'Задавать один вопрос и ждать ответа; уточнять непонятный смысл.',
        'Возвращаться к незавершённому плану; заканчивать или ставить на паузу только по вашей просьбе.',
        ('Грамматическая практика разрешена по вашему решению.' if policy['grammar_exercises'] else 'Грамматические упражнения выключены.') if conversation else 'Закреплять базовые конструкции; новое простое выражение — только в пределах согласованной нагрузки.',
        ('Необязательная подготовка: '+str(settings['homework_minutes'])+' минут.' if settings['homework_minutes'] else 'Подготовка к разговору выключена.') if conversation else 'ДЗ: '+str(settings['homework_minutes'])+' минут в двух подходах, с привычными словами.',
        'Объяснять чуть подробнее и помогать по шагам.' if settings['prompt_style']=='guided' else 'Давать короткие, понятные задания.',
    ]


def contract(policy,settings):
    exact=teacher_text(policy,settings)
    return dict(version=VERSION,digest=sha256(exact.encode()).hexdigest(),policy=policy,settings=settings,
                teacher=dict(rules=plain_rules(policy,settings),exact=exact,wishes=settings['instructions']),
                scope='Project learning instructions; additional client instructions are not independently verified.')


def example(policy,settings):
    """Bounded illustration of structured settings, never model/learner evidence."""
    conversation=policy['id']==policies.CONVERSATION
    prompt='What helps you relax after a busy day?' if conversation else {
        'contrast':'Что подходит: Did she go или Did she went?',
        'retrieval':'What did you do yesterday?',
        'rapid_retrieval':'Did you work yesterday?',
        'task_repetition':'Ещё раз расскажите одним предложением, что делали вчера.',
        'guided_transfer':'Представьте, что рассказываете другу о вчерашнем дне.',
    }.get(settings['preferred_mechanic'],'Did you call your friend yesterday?')
    if settings['prompt_style']=='guided':prompt=('Обсудим отдых после работы. ' if conversation else 'Один простой вопрос о прошлом. ')+prompt
    answer='I like watch movies.' if conversation else 'Did she went home?'
    correction=('A natural way to say it is “I like watching movies.” What kind of films do you enjoy?' if conversation else
                'После did используем простую форму: go. Попробуйте сказать весь вопрос.' if settings['prompt_style']=='guided' else
                'После did — go или went? Попробуйте ещё раз.')
    return dict(illustration=True,model_called=False,turns=[dict(role='Агент',text=prompt),dict(role='Условный ответ',text=answer),dict(role='Агент',text=correction)],
                note='Пример выбранного формата. Свободные пожелания показаны в инструкциях; их выполнение этим примером не проверяется.')
