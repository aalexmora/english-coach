'use strict';

// Fictional product scenarios, never copied from a learner ledger.
const prototypeRelease = {
  version: '0.2.0-demo', date: '2026-10-09',
  changes: [
    ['Новое', 'Два демонстрационных профиля: база Александра и разговор Кати.'],
    ['Новое', 'Версии интерфейса и каждой методики с отдельными журналами изменений.'],
    ['Новое', 'Светлая, тёмная и системная темы; сохраняется только выбор внешнего вида.'],
    ['Изменено', 'Планы, словари, разборы, поиск и экспорт относятся к выбранному demo-профилю.']
  ]
};
const learnerProfiles = {
  alexander: {
    id: 'alexander', name: 'Александр', initial: 'А', kind: 'foundation',
    method: 'Основа английского', methodVersion: '1.1-demo',
    goal: 'Рабочие и повседневные разговоры простыми словами',
    note: 'Сначала — база', description: 'Короткие фразы. Знакомые слова. Один шаг за раз.',
    changes: [['Правило', 'Простая лексика и базовые формы.'], ['Закрепление', 'Домашняя работа 10–15 минут в два подхода.'], ['Помощь', 'Самостоятельная попытка, затем помощь по необходимости.']]
  },
  katya: {
    id: 'katya', name: 'Катя', initial: 'К', kind: 'conversation',
    method: 'Свободный разговор', methodVersion: '1.0-demo',
    goal: 'Свободно и корректно говорить по-английски',
    note: 'Мысль → разговор', description: 'Развивать мысль. Исправлять главное. Продолжать тему.',
    changes: [['Разговор', 'Естественная речь агента около C1; предполагаемый уровень ученицы B2.'], ['Исправления', 'Короткая правка после законченной мысли и возвращение к содержанию.'], ['Выбор', 'Тематические и свободные беседы. Грамматические задания выключены; включение по согласию.']]
  }
};
const katyaStages = [
  {id:'katya-connect', title:'Поддерживать разговор', short:'Диалог', target:'Развить ответ и задать встречный вопрос.', forms:'уточняющие вопросы · личный пример', criterion:'Самостоятельно поддержать обмен репликами на новой теме.', prompt:'What is something you have changed your mind about recently?', reason:'Начинаем с комфортных тем, чтобы увидеть, как развивается мысль.', source:'Разговорная политика · demo'},
  {id:'katya-story', title:'Рассказывать о впечатлениях', short:'Истории', target:'Связно рассказать о событии и объяснить, почему оно запомнилось.', forms:'последовательность · значимые детали', criterion:'Рассказать новую историю без готового текста.', prompt:'Tell me about a trip that turned out differently from what you expected.', reason:'Рассказ соединяет точность и свободное выражение мысли.', source:'Разговорная политика · demo'},
  {id:'katya-opinion', title:'Развивать мнение', short:'Мнение', target:'Объяснить позицию, привести пример и ответить на уточнение.', forms:'причины · примеры · нюансы', criterion:'Обсудить незнакомый вопрос без заготовленного ответа.', prompt:'What makes a film worth watching a second time?', reason:'Переходим от короткого ответа к аргументу.', source:'Разговорная политика · demo'},
  {id:'katya-compare', title:'Обсуждать разные взгляды', short:'Выбор', target:'Сравнить варианты и спокойно выразить несогласие.', forms:'сравнение · вежливое несогласие', criterion:'Уточнить чужую позицию и объяснить свою.', prompt:'Would you rather plan a holiday carefully or leave room for surprises?', reason:'Пробуем сохранять диалог при разных мнениях.', source:'Разговорная политика · demo'},
  {id:'katya-free', title:'Свободные темы', short:'Свободно', target:'Выбрать тему и вести менее подготовленный разговор.', forms:'перефразирование · уточнение смысла', criterion:'Выразить мысль другими словами, когда нужное слово не вспоминается.', prompt:'What would you like to talk about today?', reason:'Свободная тема доступна на любом этапе, без грамматического теста.', source:'Тема по выбору ученицы'}
];
const katyaSkills = [
  {id:'katya-connect',title:'Поддерживать диалог',subtitle:'Развить ответ · задать встречный вопрос',color:'green'},
  {id:'katya-story',title:'Рассказывать связно',subtitle:'Событие · подробности · впечатления',color:'orange'},
  {id:'katya-opinion',title:'Объяснять мнение',subtitle:'Позиция · причина · пример',color:'purple'},
  {id:'katya-free',title:'Перефразировать мысль',subtitle:'Выразить смысл без готового образца',color:''}
];
const katyaLessons = [
  {id:'katya-lesson-01',date:'2026-10-09',title:'Путешествия и неожиданные впечатления',status:'finished',time:'Нагрузка ещё не согласована',job:'katya-review-01'},
  {id:'katya-lesson-02',date:'2026-10-07',title:'Что делает фильм запоминающимся',status:'finished',time:'Нагрузка ещё не согласована',job:'katya-review-02'},
  {id:'katya-lesson-03',date:'2026-10-04',title:'Свободная тема: маленькие изменения',status:'finished',time:'Нагрузка ещё не согласована',job:'katya-review-03'}
];
const katyaObservations = [
  {id:'katya-answer-1',lesson:'katya-lesson-01',date:'2026-10-09',skill:'katya-story',prompt:'Tell me about a place you visited last year.',text:'I have been there last year.',correction:'I went there last year.',assistance:'independent',outcome:'incorrect',mode:'free',later:false,followup:'What made the strongest impression on you?',focus:'Время конкретного события'},
  {id:'katya-answer-2',lesson:'katya-lesson-01',date:'2026-10-09',skill:'katya-connect',prompt:'What surprised you about the trip?',text:'I expected it to be crowded, but we found a quiet place by the sea. Have you ever had a similar experience?',correction:'',assistance:'independent',outcome:'correct',mode:'free',later:false,focus:'Развитие ответа и встречный вопрос'},
  {id:'katya-answer-3',lesson:'katya-lesson-01',date:'2026-10-09',skill:'katya-free',prompt:'Explain what you mean by a slower holiday.',text:'I mean having enough time to enjoy a place instead of trying to see everything.',correction:'',assistance:'independent',outcome:'correct',mode:'free',later:false,focus:'Перефразирование'},
  {id:'katya-answer-4',lesson:'katya-lesson-02',date:'2026-10-07',skill:'katya-opinion',prompt:'What makes a film memorable?',text:'For me, it is the way the characters change. The story can be simple if their choices feel real.',correction:'',assistance:'independent',outcome:'correct',mode:'free',later:false,focus:'Мнение с причиной'},
  {id:'katya-answer-5',lesson:'katya-lesson-02',date:'2026-10-07',skill:'katya-story',prompt:'Tell me about a film you watched recently.',text:'I watched it last weekend, and I kept thinking about the ending.',correction:'',assistance:'independent',outcome:'correct',mode:'free',later:true,focus:'Самостоятельная форма в другой ситуации'},
  {id:'katya-answer-6',lesson:'katya-lesson-03',date:'2026-10-04',skill:'katya-connect',prompt:'Describe one small change you made.',text:'It depends on how much time I have.',correction:'',assistance:'hint',outcome:'correct',mode:'free',later:false,focus:'Формулировка с подсказкой'}
];
const katyaJobs = katyaLessons.map((l,i)=>({id:l.job,lesson:l.id,date:l.date,time:'18:20',status:'applied',attempts:1,title:i===0?'Продолжить рассказ и проверить исправление в разговоре':'Добавить уточняющий вопрос к следующей теме',evidence:katyaObservations.filter(a=>a.lesson===l.id).map(a=>a.id),why:'Сохраняем смысл беседы; выбранную форму проверяем естественно в следующем разговоре.',before:'Поговорить о путешествиях.',after:'Обсудить неожиданное впечатление и задать встречный вопрос. Грамматический блок не добавлен.',pending:0}));
const katyaPhraseRows = [
  ['what stood out','что особенно запомнилось','seen','What stood out for you?'],
  ['in my experience','по моему опыту','seen','In my experience, a simple plan works best.'],
  ['it depends on','это зависит от','assisted','It depends on how much time I have.'],
  ['what I mean is','я имею в виду','seen','What I mean is that we need more time.'],
  ['on the other hand','с другой стороны','seen','On the other hand, there is less pressure.'],
  ['I changed my mind','я передумала','seen','I changed my mind after talking to a friend.'],
  ['from my point of view','с моей точки зрения','seen','From my point of view, the ending makes sense.'],
  ['a similar experience','похожий опыт','independent','Have you ever had a similar experience?']
];
const katyaPhrases = katyaPhraseRows.map(([phrase,meaning,state,example],i)=>({id:'katya-phrase-'+(i+1),phrase,meaning,state,example,date:i===7?'2026-10-09':katyaLessons[i%3].date,uses:state==='independent'?1:0,total:state==='independent'?1:0,evidence:i===2?['katya-answer-6']:i===7?['katya-answer-2']:[],situation:'Разговор о впечатлениях',source:'Вымышленный разговорный пример'}));
const katyaMaterials = [
  {id:'katya-material-1',title:'Путешествие без спешки',date:'2026-10-09',text:'What made the strongest impression on you?',meaning:'Что произвело самое сильное впечатление?',origin:'Тема разговора',topic:'Путешествия',used:1,lesson:'katya-lesson-01',exercise:'katya-topic-1',summary:'Обсудить впечатление и уточнить, почему оно запомнилось.'},
  {id:'katya-material-2',title:'Фильм, к которому хочется вернуться',date:'2026-10-07',text:'What makes a film worth watching a second time?',meaning:'Почему фильм хочется посмотреть ещё раз?',origin:'Открытый вопрос',topic:'Мнения',used:1,lesson:'katya-lesson-02',exercise:'katya-topic-2',summary:'Объяснить мнение и обсудить другую точку зрения.'},
  {id:'katya-material-3',title:'Твоя свободная тема',date:'2026-10-09',text:'What would you like to talk about today?',meaning:'О чём ты хотела бы поговорить сегодня?',origin:'Выбор ученицы',topic:'Свободная тема',used:0,lesson:null,exercise:'katya-topic-3',summary:'Выбрать тему, которая сейчас интересна. Без обязательного worksheet.'}
];
const katyaFixture = {stages:katyaStages,skills:katyaSkills,lessons:katyaLessons,observations:katyaObservations,jobs:katyaJobs,phrases:katyaPhrases,phraseExamples:katyaPhraseRows.map(r=>r[3]),materials:katyaMaterials,homework:[]};
