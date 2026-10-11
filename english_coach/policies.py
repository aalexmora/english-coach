"""Versioned teaching contracts. No learner storage or provider authorization."""
from copy import deepcopy
import re
from .models import Settings, ConversationSettings

FOUNDATION = 'foundation'
CONVERSATION = 'conversation'
VERSIONS = {FOUNDATION:'1.0.0', CONVERSATION:'1.0.0'}
FOUNDATION_MECHANICS = ('roleplay','contrast','retrieval','task_repetition','rapid_retrieval','guided_transfer')
COMMON = [
    'Ask one question, then wait. Only an explicit learner request ends or pauses the lesson.',
    'Preserve meaning; clarify unclear or unfinished speech. Identical wording is not a correction.',
    'Teacher speech is not learner evidence. Hints and imitation are not independent success.',
    'No certified CEFR, fluency, pronunciation, speed or pauses inferred from text.',
]
REGISTRY = {
    FOUNDATION: dict(name='Основа английского', vocabulary='basic',
        instructions='Use short sentences and basic familiar words. No complex professional chunks, idioms or forced synonyms. Teach at most one new simple phrase, zero during difficult repair. Require learner reproduction in supported repair, then check unprimed delayed transfer. Homework: 10–15 minutes in two approaches, one main basic gap.',
        changes=['Базовая лексика, практика форм и ДЗ 10–15 минут выделены в отдельную политику.']),
    CONVERSATION: dict(name='Свободный разговор', vocabulary='natural',
        instructions='Use natural, precise, varied English around C1, accessible to a partner whose expected replies are around B2. These are teaching targets, not an assessed learner CEFR. Respond to meaning; offer planned and learner-chosen free topics. Let the learner finish their thought. Briefly correct one important error after the turn and continue the topic; immediately clarify only if meaning is blocked. Choose at most two recurring or consequential correction focuses per block. Distinguish an actual error from an optional more natural phrasing. No compulsory repetition. Create natural later opportunities for independent reuse. Simplify or explain briefly in Russian on request. Grammar drills are disabled unless explicit scoped permission is present. Preparation is optional and must be agreed; it is a story or opinion, never a hidden worksheet.',
        changes=['Разговорный режим с естественной речью преподавателя около C1.',
                 'Краткие исправления после мысли; грамматические задания выключены по умолчанию.']),
}
POLICY_VERSIONS = {(ident,VERSIONS[ident]):deepcopy(info) for ident,info in REGISTRY.items()}
DRILL_TEXT = re.compile(r'_{2,}|fill\s+(?:in\s+)?(?:the\s+)?(?:blanks?|gaps?)|complete\s+(?:the\s+)?gaps?|insert\s+(?:the\s+)?(?:missing\s+)?word|translate\s+(?:these|the|each)\s+sentences?|conjugat(?:e|ion)|tense\s+table|заполн\w*\s+пропуск|встав\w*\s+(?:одно\s+)?слов|перевед\w*\s+(?:эти\s+)?предложен|таблиц\w*\s+врем[её]н|подстав\w*\s+(?:форм|слов)', re.I)


def choose(policy_id=FOUNDATION):
    if policy_id not in REGISTRY: raise ValueError('Unknown teaching policy')
    return dict(id=policy_id, version=VERSIONS[policy_id], grammar_exercises=policy_id==FOUNDATION)


def selection(profile):
    value = profile['value'] if 'value' in profile else profile
    return checked(value.get('teaching_policy') or choose())


def checked(value):
    if set(value) != {'id','version','grammar_exercises'} or value.get('id') not in REGISTRY:
        raise ValueError('Unknown teaching policy assignment')
    if (value['id'],value['version']) not in POLICY_VERSIONS or type(value['grammar_exercises']) is not bool:
        raise ValueError('Unsupported teaching policy version or permission')
    if value['id']==FOUNDATION and not value['grammar_exercises']:
        raise ValueError('Foundation policy includes basic grammar practice')
    return deepcopy(value)


def definition(policy):
    checked(policy)
    return POLICY_VERSIONS[(policy['id'],policy['version'])]


def session_selection(session, item_id=None):
    value=session['value']
    result=checked(value.get('teaching_policy') or choose())
    item_id=item_id if item_id is not None else value.get('current_item_id')
    if result['id']==CONVERSATION and item_id in value.get('grammar_permissions',{}):
        result['grammar_exercises']=value['grammar_permissions'][item_id]
    return checked(result)


def defaults(policy):
    return (Settings() if policy['id']==FOUNDATION else ConversationSettings()).model_dump(mode='json')


def settings_for(policy, value):
    model=Settings if policy['id']==FOUNDATION else ConversationSettings
    result=model.model_validate(value).model_dump(mode='json')
    check_activity(policy,result['preferred_mechanic'])
    return result


def allowed_mechanics(policy):
    if policy['id']==FOUNDATION: return FOUNDATION_MECHANICS
    return ('conversation','roleplay',*FOUNDATION_MECHANICS[1:]) if policy['grammar_exercises'] else ('conversation','roleplay')


def check_activity(policy, mechanic, text='', activity='communicative'):
    if mechanic not in allowed_mechanics(policy): raise ValueError('Mechanic requires explicit grammar permission for this policy')
    if policy['id']==CONVERSATION and not policy['grammar_exercises'] and (activity=='grammar_drill' or DRILL_TEXT.search(text)):
        raise ValueError('Grammar drills require explicit scoped learner permission')


def compatible(policy, item):
    try:
        check_activity(policy,item['mechanic'], ' '.join(str(item.get(k,'')) for k in ('task','first_prompt','transfer_prompt','situation')),
                       item.get('activity','communicative'))
        return True
    except ValueError: return False


def contract(policy):
    policy=checked(policy)
    info=definition(policy)
    return dict(**policy,name=info['name'],vocabulary=info['vocabulary'],instructions=info['instructions'],
                allowed_mechanics=list(allowed_mechanics(policy)),common_guarantees=COMMON,
                grammar_permission_scope='profile or explicitly granted session item',
                semantic_limit='Structured kinds and obvious worksheet wording are checked; the teacher must also review the meaning of prompts.')


def catalog():
    return [dict(contract(choose(ident)),changes=[dict(version=VERSIONS[ident],date='2026-10-09',items=info['changes'])])
            for ident,info in REGISTRY.items()]
