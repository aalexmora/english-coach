'use strict';

// All fixtures are fictional. This prototype has no API, credentials or learner persistence.
const icons = {
  leaf: '<path d="M20 4C9 2 3 8 5 16c7 3 15-1 15-12Z"/><path d="M5 20 15 9"/>',
  overview: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  program: '<path d="M4 5h7l2 3h7v12H4Z"/><path d="M8 12h8M8 16h5"/>',
  progress: '<path d="M4 20V4M4 20h16M8 15l4-5 4 2 5-7"/>',
  vocabulary: '<path d="M12 6C8 3 4 4 3 5v14c3-2 6-1 9 1 3-2 6-3 9-1V5c-3-2-6-1-9 1Zm0 0v14"/>',
  lessons: '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 11h16M8 15h2M14 15h2"/>',
  methodologist: '<path d="M12 3 3 7l9 4 9-4-9-4ZM6 9v6l6 3 6-3V9M21 8v8"/>',
  materials: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 15h5"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 5 2 4 3 1 1 4h6l1-4 3-1 2-4-2-5-3-1-1-3Z"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
  arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9 8a3 3 0 0 1 6 1c0 2-3 2-3 4M12 17h.01"/>'
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.info}</svg>`;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const badge = (text, color = '') => `<span class="badge ${color}">${esc(text)}</span>`;
const button = (text, action, attrs = '', style = '', glyph = 'arrow') => `<button class="btn ${style}" data-action="${action}" ${attrs}>${esc(text)}${glyph ? icon(glyph) : ''}</button>`;
const detailButton = (text, type, id, style = '') => button(text, 'detail', `data-type="${type}" data-id="${esc(id)}"`, style);
const navigateButton = (text, page, style = '') => button(text, 'navigate', `data-page="${page}"`, style);
const demoDate = new Date('2026-10-09T12:00:00+03:00');
const pages = {
  overview: ['Обзор', 'Вся картина обучения — в одном месте.'],
  program: ['Программа и план', 'От базовых вопросов к рабочему разговору.'],
  progress: ['Мой прогресс', 'Что получается самостоятельно, а что ещё требует проверки.'],
  vocabulary: ['Мой словарь', 'Простые слова и фразы, которые переходят в твою речь.'],
  lessons: ['Уроки и ДЗ', 'Сохранённые ответы, незавершённые задачи и закрепление.'],
  methodologist: ['Работа методолога', 'От конкретного ответа к понятному решению.'],
  materials: ['Материалы и методы', 'Откуда берутся ситуации, упражнения и способы практики.'],
  settings: ['Мои настройки', 'Цель, нагрузка и правила, по которым строятся занятия.']
};
let stages = [
  {id:'questions', title:'Базовые вопросы', short:'Вопросы', target:'Задать короткий вопрос о месте, времени и действии.', forms:'am / is / are · do / does', criterion:'Самостоятельно задать вопросы в новой ситуации, затем проверить их позднее.', prompt:'Ты впервые разговариваешь с новым коллегой. Узнай, где он работает и когда ему удобно созвониться.', reason:'Вопросы пока требуют помощи. Проверяем основу перед усложнением.', source:'Адаптированная последовательность Empower'},
  {id:'past', title:'Простое прошлое', short:'Простое прошлое', target:'Различать состояние и действие в прошлом.', forms:'was / were · did + базовая форма', criterion:'Описать событие и задать вопрос о нём без образца на следующем уроке.', prompt:'Вчера друг не пришёл на встречу. Узнай, где он был и что произошло.', reason:'Следующий шаг после самостоятельных базовых вопросов.', source:'Адаптация к текущим затруднениям'},
  {id:'story', title:'Связный рассказ', short:'Рассказ', target:'Рассказать, что произошло сначала и чем всё закончилось.', forms:'простое прошлое · first / then', criterion:'Связать несколько событий знакомыми словами в иной ситуации.', prompt:'Расскажи другу, почему вчера пришлось изменить планы.', reason:'Соединяем простые формы в понятный рассказ.', source:'Практика связной речи'},
  {id:'future', title:'Планы и договорённости', short:'Планы', target:'Назвать план, подтвердить время и ответить на просьбу.', forms:'will · going to · договорённости', criterion:'Выбрать подходящую форму по смыслу без подсказки.', prompt:'Друг предлагает встретиться завтра. Обсуди время и место.', reason:'Сначала закрепляем вопросы, затем уточняем будущие планы.', source:'Бытовые и рабочие ситуации'},
  {id:'time', title:'События и сроки', short:'Сроки', target:'Показать связь между событиями и сроками.', forms:'прошлое · длительность · причины', criterion:'Передать порядок событий в новом рассказе.', prompt:'Объясни коллеге, что было готово к началу встречи.', reason:'Более сложные формы после проверки простого прошлого.', source:'Маршрут Coach'},
  {id:'modal', title:'Возможности и советы', short:'Возможности', target:'Попросить, предложить помощь и дать простой совет.', forms:'can · should · must', criterion:'Выбрать просьбу или рекомендацию по коммуникативному смыслу.', prompt:'Коллеге нужна помощь. Предложи простой способ решить задачу.', reason:'Практикуем после закрепления базы.', source:'Коммуникативные задачи'},
  {id:'discussion', title:'Рабочая дискуссия', short:'Обсуждение', target:'Дать связный ответ и обсудить рабочее решение.', forms:'проверенные формы · знакомые слова', criterion:'Обсудить решение в новом контексте без предварительного образца.', prompt:'Обсуди с коллегой изменение времени встречи.', reason:'Переносим отдельные навыки в разговор.', source:'Адаптации рабочих задач'}
];
let skills = [
  {id:'questions', title:'Задавать вопросы', subtitle:'Порядок слов · do / does · was / were', color:'green'},
  {id:'past', title:'Рассказывать о прошлом', subtitle:'Состояние и действие · did + базовая форма', color:'orange'},
  {id:'future', title:'Обсуждать планы', subtitle:'Время, место и договорённости', color:'purple'},
  {id:'discussion', title:'Говорить в рабочей дискуссии', subtitle:'Связная речь в новой ситуации', color:''}
];
const taskTexts = {
  questions: [['Где работает новый коллега?', 'Where do you work?', 'Where you work?'], ['Когда вам удобно созвониться?', 'When can you call?', 'When you can call?'], ['Где Анна была вчера?', 'Where was Anna yesterday?', 'Where Anna was yesterday?']],
  past: [['Спроси, звонил ли друг вчера.', 'Did you call yesterday?', 'Did you called yesterday?'], ['Скажи, что вы были дома.', 'We were at home.', 'We was at home.'], ['Расскажи, что произошло после встречи.', 'I went home after the meeting.', 'I go home after the meeting.']],
  future: [['Подтверди согласованную встречу завтра.', 'We are meeting tomorrow.', 'We meeting tomorrow.'], ['Тебя только что попросили помочь.', 'I will help you.', 'I will helped you.'], ['Скажи, что завтра будешь дома.', 'I will be at home tomorrow.', 'I will at home tomorrow.']]
};
let lessons = Array.from({length:12}, (_, index) => {
  const date = new Date(demoDate); date.setDate(date.getDate() - index);
  const iso = date.toISOString().slice(0,10);
  return {id:`lesson-${String(index+1).padStart(2,'0')}`, date:iso, title: index < 4 ? 'Вопросы и простое прошлое' : index < 8 ? 'Планы и договорённости' : 'Вопросы в новой ситуации', status:'finished', time:'30 минут по плану', job:`review-${String(index+1).padStart(2,'0')}`};
});
let observations = lessons.flatMap((lesson, index) => Array.from({length:6}, (_, j) => {
  const skill = ['questions','past','questions','future','past','questions'][j];
  const templates = taskTexts[skill], template = templates[(j+index)%templates.length];
  const assistance = (j+index)%5 === 0 ? 'hint' : (j+index)%7 === 0 ? 'immediate_repeat' : 'independent';
  const outcome = j===2&&index%3===0 || index===0&&j===3 ? 'incorrect' : (j+index)%11 === 0 ? 'ambiguous' : (j+index*2)%4 === 0 ? 'incorrect' : 'correct';
  return {id:`answer-${index+1}-${j+1}`, lesson:lesson.id, date:lesson.date, skill, prompt:template[0], text:outcome==='correct'?template[1]:template[2], correction:template[1], assistance, outcome, mode:j===5?'free':j===2?'cold':'controlled', later:index%3===0&&j===5&&assistance==='independent'&&outcome==='correct'};
}));
let jobs = lessons.map((lesson,index) => ({id:lesson.job, lesson:lesson.id, date:lesson.date, time:'09:42', status:index===1?'failed':index===4?'stale':'applied', attempts:index===1?3:1, title:index===1?'Модель не ответила в пределах таймаута':index===4?'План изменился во время разбора':'Сначала закрепить короткие вопросы', evidence:observations.filter(a=>a.lesson===lesson.id&&a.skill==='questions').map(a=>a.id), why:'В самостоятельных вопросах порядок слов ещё нестабилен. Сохраняем простые слова и проверяем форму в другой ситуации.', before:'Перейти к более сложному рассказу о прошлом.', after:'Сначала короткая самостоятельная проверка вопросов. Незавершённый рассказ сохранить.', pending:index===2?1:0}));
const lexicalStates = {seen:['Показано',''], assisted:['С помощью','orange'], independent:['Самостоятельно','green'], transferred:['В новой ситуации','purple'], active:['Активное употребление','green']};
let phraseExamples = ['I am at home.','I am ready.','Please call me.','I am busy today.','I will call tomorrow.','I called last week.','We are on time.','I think we can meet.','I need help.','Can you call me?','I work here.','We can meet at six.','I will go home.','Please send it.','I need this file.','One more question.','Thank you for your help.','We can talk next time.'];
let phrases = [['at home','дома'],['ready','готов'],['call me','позвони мне'],['today','сегодня'],['tomorrow','завтра'],['last week','на прошлой неделе'],['on time','вовремя'],['I think','я думаю'],['need help','нужна помощь'],['can you','можешь ли ты'],['work here','работать здесь'],['at six','в шесть'],['go home','идти домой'],['send it','отправить это'],['this file','этот файл'],['one more','ещё один'],['thank you','спасибо'],['next time','в следующий раз']].map(([phrase,meaning],i)=>({id:`phrase-${i+1}`,phrase,meaning,state:['independent','assisted','active','seen','transferred'][i%5],date:lessons[i%lessons.length].date, uses:i%4+1,total:i%4+2, evidence:[observations[i*2%observations.length].id], situation:'Короткое сообщение другу', source:'Объяснение в демонстрационном уроке'}));
let materials = [
  {id:'material-1', title:'Перенос рабочей встречи', date:'2026-10-09', text:'We can meet at six.', meaning:'Мы можем встретиться в шесть.', origin:'Адаптировано', topic:'Договорённости', used:2, lesson:'lesson-01', exercise:'work-exercise-1', summary:'Уточнить время и подтвердить договорённость простыми словами.'},
  {id:'material-2', title:'Просьба прислать файл', date:'2026-10-06', text:'Can you send the file?', meaning:'Можешь прислать файл?', origin:'Адаптировано', topic:'Вопросы', used:1, lesson:'lesson-04', exercise:'work-exercise-2', summary:'Сформулировать короткую просьбу, сохраняя исходный смысл.'},
  {id:'material-3', title:'Короткий ответ о готовности', date:'2026-10-03', text:'I am ready.', meaning:'Я готов.', origin:'Выбранный фрагмент', topic:'Базовые формы', used:0, lesson:null, exercise:'work-exercise-3', summary:'Различать готовность и действие, не терять am/is/are.'}
];
let homework = [
  {id:'1', prompt:'Вставь одно слово: I ___ at home.', phase:'practice'},
  {id:'2', prompt:'Вставь одно слово: Anna ___ ready.', phase:'practice'},
  {id:'3', prompt:'Исправь только форму: We happy today.', phase:'practice'},
  {id:'4', prompt:'Выбери ответ о настоящем: A — He is here. B — He was here.', phase:'practice'},
  {id:'5', prompt:'Напиши, где ты сейчас, одним коротким предложением.', phase:'delayed'},
  {id:'6', prompt:'Напиши другу, что вы готовы.', phase:'delayed'}
];
const profileFixtures = {
  alexander: {stages, skills, lessons, observations, jobs, phrases, phraseExamples, materials, homework},
  katya: katyaFixture
};
const draftStore = {alexander: {}, katya: {}};
let draftAnswers = draftStore.alexander;
let activeProfile = learnerProfiles.alexander;
const demoPreferences = {katya: {grammar: false}};
const isConversation = () => activeProfile.kind === 'conversation';
function selectFixture(id) {
  activeProfile = learnerProfiles[id];
  ({stages, skills, lessons, observations, jobs, phrases, phraseExamples, materials, homework} = profileFixtures[id]);
  draftAnswers = draftStore[id];
}
const themeMedia = matchMedia('(prefers-color-scheme: dark)');
function applyTheme(mode, persist = false) {
  if (!['system', 'light', 'dark'].includes(mode)) mode = 'system';
  const theme = mode === 'system' ? (themeMedia.matches ? 'dark' : 'light') : mode;
  document.documentElement.dataset.themeMode = mode;
  document.documentElement.dataset.theme = theme;
  document.getElementById('theme-mode').value = mode;
  if (persist) {
    try { localStorage.setItem('english-coach-ui-theme', mode); }
    catch { toast('Тема применена. Браузер не разрешил сохранить выбор после перезагрузки.'); }
  }
}
themeMedia.addEventListener('change', () => {
  if (document.documentElement.dataset.themeMode === 'system') applyTheme('system');
});
let vocabularyTab = 'learned', planTab = 'current', lessonTab = 'lessons', toastTimer;
let localQuery = '', vocabularyState = 'all', vocabularyPage = 1, jobState = 'all';
let ui = {};
let detailFocusTarget = null;
const dateLabel = (iso, full = false) => new Date(iso+'T12:00:00+03:00').toLocaleDateString('ru-RU', {day:'numeric',month:full?'long':'short'});
const assistanceLabel = {independent:'Без подсказки',hint:'С подсказкой',immediate_repeat:'После образца'};
const outcomeLabel = {correct:'Верно',incorrect:'Нужно исправить',ambiguous:'Оценка не определена'};
const jobLabels = {applied:['Результат применён','green'],failed:['Ошибка · не применён','red'],stale:['Данные изменились','orange'],queued:['Ожидает',''],running:['Выполняется','purple']};
function inPeriod(item) {
  if(ui.period==='all')return true;
  const days = Math.floor((demoDate-new Date(item.date+'T12:00:00+03:00'))/86400000);
  return days>=0&&days<Number(ui.period);
}
function rows(skill) {return observations.filter(a=>inPeriod(a)&&(!skill||a.skill===skill));}
function stats(skill) {
  const all=rows(skill), known=all.filter(a=>a.outcome!=='ambiguous'), independent=known.filter(a=>a.assistance==='independent');
  return {all, independent, correct:independent.filter(a=>a.outcome==='correct').length, total:independent.length, assisted:known.filter(a=>a.assistance!=='independent').length, ambiguous:all.length-known.length, later:all.filter(a=>a.later).length};
}
const fraction = (s) => s.total ? `${s.correct}<small> / ${s.total}</small>` : '<small>Нет проверок</small>';
function noun(number, forms) {
  const last = number % 10, tens = number % 100;
  return forms[tens >= 11 && tens <= 14 ? 2 : last === 1 ? 0 : last >= 2 && last <= 4 ? 1 : 2];
}
function route(updates = {}, reset = false) {
  const params = reset ? new URLSearchParams() : new URLSearchParams(location.hash.slice(1));
  Object.entries(updates).forEach(([key,value])=>value===null?params.delete(key):params.set(key,String(value)));
  if(!params.has('page'))params.set('page','overview');
  if(!params.has('profile'))params.set('profile',activeProfile.id);
  location.hash=params.toString();
}
function readRoute() {
  const p=new URLSearchParams(location.hash.slice(1));
  ui={profile:p.get('profile')==='katya'?'katya':'alexander',page:pages[p.get('page')]?p.get('page'):'overview',period:['7','14','30','all'].includes(p.get('period'))?p.get('period'):'14',scenario:['normal','empty','failure'].includes(p.get('scenario'))?p.get('scenario'):'normal',detail:p.get('detail'),q:p.get('q')||''};
  selectFixture(ui.profile);
  vocabularyTab=p.get('vtab')==='source'?'source':'learned';
  planTab=['future','carry'].includes(p.get('plan'))?p.get('plan'):'current';
  lessonTab=p.get('ltab')==='homework'?'homework':'lessons';
  localQuery=p.get('filter')||''; vocabularyState=p.get('vstate')||'all';jobState=p.get('jstate')||'all';
  vocabularyPage=Math.max(1,Number(p.get('vp'))||1);
}
function pageInfo(id) {
  if (!isConversation()) return pages[id];
  return ({overview:['Обзор','Твои темы, мысли и следующий разговор.'],program:['Темы и план','Гибкий маршрут к свободному и корректному общению.'],progress:['Мой прогресс','Как развивается мысль и что получается без подсказки.'],vocabulary:['Мой словарь','Выражения, которые помогают точнее передать мысль.'],lessons:['Беседы и закрепление','Разговоры, исправления и необязательная подготовка.'],materials:['Материалы и методы','Открытые вопросы и темы по твоему выбору.']})[id] || pages[id];
}
function versionStrip() {
  return `<div class="version-strip" aria-label="Версии компонентов">${detailButton('UI ' + prototypeRelease.version,'release','ui','version-link')}${detailButton(activeProfile.method + ' · ' + activeProfile.methodVersion,'release','method','version-link')}<span>Демонстрационные версии · ${esc(activeProfile.name)}</span></div>`;
}
function heading() {
  const [title, subtitle] = pageInfo(ui.page);
  return `${versionStrip()}<div class="page-heading"><div><h1>${title}</h1><p>${subtitle}</p></div><div class="page-controls"><select class="select" id="period" aria-label="Период данных">${[['7','7 дней'],['14','14 дней'],['30','30 дней'],['all','Вся демоистория']].map(([v,t])=>`<option value="${v}" ${ui.period===v?'selected':''}>${t}</option>`).join('')}</select><select class="select demo-select" id="scenario" aria-label="Демонстрационный сценарий">${[['normal','Демо · с данными'],['empty','Демо · пустой словарь'],['failure','Демо · сбой разбора']].map(([v,t])=>`<option value="${v}" ${ui.scenario===v?'selected':''}>${t}</option>`).join('')}</select></div></div>`;
}
function sidebar() {
  document.getElementById('sidebar').innerHTML=`<a class="brand" href="#page=overview&profile=${ui.profile}"><span class="brand-mark">${icon('leaf')}</span>English Coach</a><div class="eyebrow nav-caption">Обучение · ${esc(activeProfile.name)}</div><nav class="nav-list">${Object.keys(pages).map(id=>`<a href="#page=${id}&profile=${ui.profile}&period=${ui.period}&scenario=${ui.scenario}" class="nav-link ${ui.page===id?'active':''}" ${ui.page===id?'aria-current="page"':''}>${icon(id)}${pageInfo(id)[0]}${id==='lessons'&&!isConversation()?'<span class="nav-count">ДЗ</span>':''}</a>`).join('')}</nav><div class="sidebar-bottom"><div class="sidebar-note"><strong>${activeProfile.note}</strong><br>${activeProfile.description}</div><div class="profile-mini"><span class="avatar">${activeProfile.initial}</span><div><strong>${esc(activeProfile.name)}</strong><small>Демонстрационный профиль</small></div></div></div>`;
}
function statusNotice() {
  return ui.scenario==='failure'?`<div class="notice">${icon('info')}<div><strong>Разбор не завершился. Ответы сохранены.</strong><br>В этом демосценарии модель не ответила. ${isConversation()?'План бесед сохранён; обязательных заданий нет.':'План не изменён; домашнее задание доступно.'}</div></div>`:'';
}
function statCards() {
  const s=stats(), lexical=ui.scenario==='empty'?0:phrases.filter(p=>inPeriod(p)&&['independent','transferred','active'].includes(p.state)).length;
  return `<div class="grid grid-4 section-space">
    <div class="card stat"><div class="stat-label">${icon('progress')}Самостоятельные ответы</div><div class="stat-number">${fraction(s)}</div><div class="stat-foot">Верно / все оценённые<br>${s.ambiguous} с неопределённой оценкой отдельно</div><button class="icon-button stat-open" aria-label="Посмотреть самостоятельные ответы" data-action="navigate" data-page="progress">${icon('chevron')}</button></div>
    <div class="card stat"><div class="stat-label">${icon('check')}Проверено позднее</div><div class="stat-number">${s.later}<small> ${s.later===1?"проверка":s.later<5?"проверки":"проверок"}</small></div><div class="stat-foot">Без образца, в другой ситуации<br>Примеры переноса из демоистории</div><button class="icon-button stat-open" aria-label="Посмотреть отложенные проверки" data-action="detail" data-type="retention" data-id="all">${icon('chevron')}</button></div>
    <div class="card stat"><div class="stat-label">${icon('vocabulary')}Фразы в самостоятельной речи</div><div class="stat-number">${lexical}<small> ${noun(lexical,['фраза','фразы','фраз'])}</small></div><div class="stat-foot">Из зарегистрированного словаря<br>Это не весь словарный запас</div><button class="icon-button stat-open" aria-label="Открыть словарь" data-action="navigate" data-page="vocabulary">${icon('chevron')}</button></div>
    <div class="card stat"><div class="stat-label">${icon('lessons')}Занятия с сохранениями</div><div class="stat-number">${lessons.filter(inPeriod).length}<small> ${noun(lessons.filter(inPeriod).length,['занятие','занятия','занятий'])}</small></div><div class="stat-foot">Количество учебных сессий<br>Показатель активности</div><button class="icon-button stat-open" aria-label="Открыть занятия" data-action="navigate" data-page="lessons">${icon('chevron')}</button></div></div>`;
}
function chart() {
  const visible=lessons.filter(inPeriod).slice().reverse();
  return `<div class="chart" role="group" aria-label="Правильные ответы по демонстрационным урокам">${visible.map(l=>{
    const aa=observations.filter(a=>a.lesson===l.id&&a.outcome==='correct'), independent=aa.filter(a=>a.assistance==='independent').length, assisted=aa.length-independent;
    return `<button class="bar-column" data-action="detail" data-type="lesson" data-id="${l.id}" aria-label="${dateLabel(l.date)}: ${independent} самостоятельных и ${assisted} с помощью"><span class="bar-track"><span class="bar" style="height:${independent*25}px"></span><span class="bar assisted" style="height:${assisted*25}px"></span></span><span class="bar-label">${dateLabel(l.date)}</span></button>`;
  }).join('')}</div><div class="chart-legend"><span><i class="legend-dot"></i>Верно самостоятельно</span><span><i class="legend-dot soft"></i>Верно с помощью</span></div><p class="rule-note">Число правильных ответов, не процент освоения. Нажми на день, чтобы увидеть задания.</p>`;
}
function routePreview() {
  return `<div class="route-preview">${stages.map((s,i)=>`<button class="route-step ${i===0?'current':''}" data-action="detail" data-type="stage" data-id="${s.id}"><span class="step-number">${i+1}</span><span>${s.short}</span></button>`).join('')}</div>`;
}
function overview() {
  if (isConversation()) return conversationOverview();
  const latest=ui.scenario==='failure'?'failed':'applied';
  return `${statusNotice()}<div class="grid grid-2"><section class="hero"><div><div class="eyebrow">Текущий этап · 01 / 07</div><h2>Сейчас — базовые вопросы.</h2><p>Учимся узнавать место, время и действие короткими фразами. Более сложные темы ждут самостоятельной проверки базы.</p><div class="hero-meta">${navigateButton('Посмотреть мой маршрут','program','primary')}${badge('Диагностика','dark')}</div></div><div class="hero-visual"><div class="stage-circle"><strong>01</strong></div><small>из 7 этапов маршрута</small></div></section><section class="card today"><div class="card-head"><span class="eyebrow">Следующий маленький шаг</span>${icon('arrow')}</div><div class="next-title">Узнать, где работает<br>новый коллега.</div><p class="next-description">Один короткий вопрос без образца. Затем — похожая задача в новой ситуации.</p><div class="tiny-meta"><span>${icon('clock')}5 минут по плану</span><span>${icon('vocabulary')}Знакомые слова</span></div>${detailButton('Почему это задание?','job',jobs[0].id,'soft')}</section></div>
    ${statCards()}
    <div class="grid grid-2 section-space"><section class="card"><div class="card-head"><h2>Как меняется практика</h2>${navigateButton('Подробнее','progress','ghost')}</div>${chart()}</section><section class="card"><div class="card-head"><h2>Домашнее закрепление</h2>${badge('12 минут','orange')}</div><div class="list-row"><span class="row-icon">${icon('vocabulary')}</span><div class="row-copy"><h3>Не терять am / is / are</h3><p>Одна тема · знакомые слова · два подхода</p></div></div><div class="homework-mini"><span>Сдано 0 из 6 заданий</span><span>Можно частями</span></div><div class="progress-track"><div class="progress-fill" style="width:0%"></div></div><p class="rule-note">6–8 минут сейчас. Остальное — после перерыва, лучше позднее или завтра.</p><div class="section-space">${detailButton('Открыть задания','homework','hw-01','soft')}</div></section></div>
    <div class="grid grid-2 section-space"><section class="card"><div class="card-head"><h2>Мой учебный маршрут</h2>${navigateButton('Вся программа','program','ghost')}</div>${routePreview()}<p class="rule-note">Следующий этап открывается по результатам самостоятельной проверки.</p></section><section class="card"><div class="card-head"><h2>Последнее решение</h2>${badge(jobLabels[latest][0],jobLabels[latest][1])}</div><div class="list-row"><span class="row-icon">${icon('methodologist')}</span><div class="row-copy"><h3>${latest==='applied'?'Закрепить основу перед сложным прошлым':'Ответы сохранены, разбор не применён'}</h3><p>9 октября · демонстрационный разбор</p></div></div><div class="health-pair"><span><i class="dot"></i>Ответы сохранены</span><span>${latest==='applied'?'План обновлён':'План сохранён без изменений'}</span></div><div class="section-space">${detailButton('Открыть разбор','job',jobs[0].id,'ghost')}</div></section></div><div class="live-date">Демонстрационный снимок: 9 октября 2026 · все показатели рассчитаны по вымышленным ответам.</div>`;
}
function program() {
  if (isConversation()) return conversationProgram();
  const taskSets={current:['Короткие вопросы коллеге — самостоятельная попытка','Простое прошлое: состояние и действие','План встречи — уточнить и подтвердить время'],future:['Самостоятельная проверка вопросов в новой ситуации','Вернуться к незавершённому рассказу','Повторить договорённость без открытого образца'],carry:['Закончить мысль о разговоре с клиентом','Проверить вопрос о месте встречи позднее']};
  return `<div class="notice info">${icon('info')}<div><strong>Моя цель</strong><br>Формулировать мысли на английском в рабочих и повседневных разговорах, используя понятные базовые формы.</div></div><div class="grid grid-2"><section><div class="card-head"><h2>Семь этапов программы</h2>${badge('0 завершено','')}</div><div class="program-list">${stages.map((s,i)=>`<button class="stage-card ${i===0?'current':''}" data-action="detail" data-type="stage" data-id="${s.id}"><span class="step-number">${String(i+1).padStart(2,'0')}</span><span class="stage-content"><h3>${s.title}</h3><p>${s.forms}</p></span>${badge(i===0?'Диагностика':'Впереди',i===0?'green':'')}${icon('chevron')}</button>`).join('')}</div></section><section><div class="card"><h2>План и точка продолжения</h2><div class="tabs" role="group" aria-label="Выбор плана">${[['current','Текущий'],['future','Будущий'],['carry','Переносы']].map(([v,t])=>`<button class="tab ${planTab===v?'active':''}" data-action="plan-tab" data-value="${v}" aria-pressed="${planTab===v}">${t}</button>`).join('')}</div><p class="muted" style="font-size:12px">${planTab==='current'?'Демо активной сессии · работа продолжается':planTab==='future'?'Шаблон следующего занятия, не текущая сессия':'Незавершённые задачи остаются в маршруте'}</p>${taskSets[planTab].map((t,i)=>`<div class="list-row"><span class="row-icon">${i+1}</span><div class="row-copy"><h3>${t}</h3><p>${i===0?'Приоритет: вопросы':'Сохранить исходный смысл'} · ${planTab==='carry'?'перенесено':'10 минут по плану'}</p></div></div>`).join('')}<p class="rule-note">Выполненный план не завершает урок. Пауза и окончание — по твоей команде.</p></div><div class="card section-space"><h2>Почему начинаем с базы</h2><p class="chart-note">Порядок слов в вопросах ещё требует проверки. Успех с подсказкой не заменяет ответ в новой ситуации без образца.</p>${detailButton('Посмотреть основание','job',jobs[0].id,'soft')}</div><div class="card section-space"><h2>История изменения плана</h2><p class="chart-note">Сложное прошлое отложено; незавершённый рассказ сохранён.</p>${detailButton('До и после','job',jobs[0].id,'ghost')}</div></section></div>`;
}
function progress() {
  if (isConversation()) return conversationProgress();
  const s=stats();
  return `<div class="grid grid-3"><div class="card stat"><div class="stat-label">Самостоятельная точность</div><div class="stat-number">${s.total?Math.round(s.correct/s.total*100)+'%':'—'}</div><div class="stat-foot">${s.correct} верно из ${s.total} оценённых ответов</div></div><div class="card stat"><div class="stat-label">Ответы с помощью</div><div class="stat-number">${s.assisted}</div><div class="stat-foot">Подсказки и повтор после образца отдельно</div></div><div class="card stat"><div class="stat-label">Неоднозначные наблюдения</div><div class="stat-number">${s.ambiguous}</div><div class="stat-foot">Исключены из расчёта точности</div></div></div><section class="card section-space"><div class="card-head"><h2>Навыки в работе</h2>${detailButton('Как считаем','metrics','all','ghost')}</div><div class="table-wrap"><table class="table"><thead><tr><th>Навык</th><th>Самостоятельно</th><th>С помощью</th><th>Что подтверждено</th><th></th></tr></thead><tbody>${skills.map(skill=>{const t=stats(skill.id);return `<tr class="clickable" tabindex="0" data-action="detail" data-type="skill" data-id="${skill.id}"><td><strong>${skill.title}</strong><small>${skill.subtitle}</small></td><td class="fraction">${fraction(t)}</td><td>${t.assisted}</td><td>${badge(t.total?'Есть наблюдения':'Данных недостаточно',t.total?'green':'')}</td><td>${icon('chevron')}</td></tr>`;}).join('')}</tbody></table></div><p class="rule-note">Верно / все самостоятельные оценённые ответы за выбранный период. Режимы заданий раскрываются в карточке навыка.</p></section><div class="grid grid-2 section-space"><section class="card"><h2>Результаты по урокам</h2>${chart()}</section><section class="card"><div class="card-head"><h2>Что стоит проверить</h2>${badge('2 приоритета','orange')}</div>${[['questions','Порядок слов в вопросе','Без подсказки в другой ситуации'],['past','Did + базовая форма','После перерыва, с новым событием']].map(([id,t,d])=>`<button class="link-row" data-action="detail" data-type="skill" data-id="${id}"><div class="list-row"><span class="row-icon orange">${icon('help')}</span><div class="row-copy"><h3>${t}</h3><p>${d}</p></div>${icon('chevron')}</div></button>`).join('')}<p class="rule-note">Приоритеты из демонстрационного решения. Это не диагностика реального ученика.</p></section></div>`;
}
function vocabulary() {
  const selected=phrases.filter(p=>inPeriod(p)&&(vocabularyState==='all'||p.state===vocabularyState)&&`${p.phrase} ${p.meaning}`.toLowerCase().includes(localQuery.toLowerCase()));
  const totalPages=Math.max(1,Math.ceil(selected.length/6)), page=Math.min(vocabularyPage,totalPages), visible=selected.slice((page-1)*6,page*6);
  return `<div class="tabs" role="group" aria-label="Тип словаря">${[['learned','Мой учебный словарь'],['source','Материал для обучения']].map(([v,t])=>`<button class="tab ${vocabularyTab===v?'active':''}" data-action="vocabulary-tab" data-value="${v}" aria-pressed="${vocabularyTab===v}">${t}</button>`).join('')}</div>${vocabularyTab==='source'?`<div class="notice info">${icon('info')}<div>Фразы из материалов — основа для будущих заданий. Они ещё не считаются твоим самостоятельным словарём.</div></div>${materialsView(true)}`:ui.scenario==='empty'?`<section class="card empty"><div class="row-icon">${icon('vocabulary')}</div><h3>Учебный словарь пока пуст</h3><p>Здесь появятся фразы, которые преподаватель объяснил и связал с твоими ответами. Это не означает, что ты не знаешь английских слов.</p>${button('Посмотреть материал для обучения','vocabulary-tab','data-value="source"','soft')}<p class="rule-note">Демонстрационный сценарий отсутствия зарегистрированных лексических проверок.</p></section>`:`<div class="grid grid-3"><div class="card stat"><div class="stat-label">В зарегистрированном словаре</div><div class="stat-number">${phrases.filter(inPeriod).length}<small> фраз</small></div><div class="stat-foot">Покрытие учёта за выбранный период</div></div><div class="card stat"><div class="stat-label">Есть самостоятельное употребление</div><div class="stat-number">${phrases.filter(p=>inPeriod(p)&&['independent','transferred','active'].includes(p.state)).length}</div><div class="stat-foot">Подтверждение в карточке каждой фразы</div></div><div class="card stat"><div class="stat-label">Новая лексика за урок</div><div class="stat-number">${isConversation()?'По смыслу':'0–1<small> простая фраза</small>'}</div><div class="stat-foot">${isConversation()?'Полезное выражение из текущего разговора':'Без новых слов при трудной грамматике'}</div></div></div><section class="card section-space"><div class="toolbar"><input class="input" id="vocabulary-search" aria-label="Поиск в словаре" placeholder="Найти фразу или значение" value="${esc(localQuery)}"><select class="select" id="vocabulary-state" aria-label="Состояние фразы"><option value="all">Все состояния</option>${Object.entries(lexicalStates).map(([v,[t]])=>`<option value="${v}" ${v===vocabularyState?'selected':''}>${t}</option>`).join('')}</select></div>${visible.length?`<div class="table-wrap"><table class="table"><thead><tr><th>Фраза и смысл</th><th>Состояние</th><th>Употребления</th><th>Последняя практика</th><th></th></tr></thead><tbody>${visible.map(p=>`<tr class="clickable" tabindex="0" data-action="detail" data-type="phrase" data-id="${p.id}"><td><strong>${p.phrase}</strong><small>${p.meaning}</small></td><td>${badge(...lexicalStates[p.state])}</td><td>${['seen','assisted'].includes(p.state)?'Ещё нет':p.uses+' / '+p.total}<br><small>${['seen','assisted'].includes(p.state)?'самостоятельных проверок':'верно / самостоятельные проверки'}</small></td><td>${dateLabel(p.date)}</td><td>${icon('chevron')}</td></tr>`).join('')}</tbody></table></div>`:'<div class="empty"><h3>Совпадений нет</h3><p>Попробуй другое слово или состояние фразы.</p></div>'}<div class="pagination"><span>${selected.length?`${(page-1)*6+1}–${Math.min(page*6,selected.length)} из ${selected.length}`:'0 фраз'} · страница ${page} / ${totalPages}</span><div class="pagination-actions"><button class="btn small" data-action="vocabulary-page" data-value="${page-1}" ${page===1?'disabled':''}>← Назад</button><button class="btn small" data-action="vocabulary-page" data-value="${page+1}" ${page===totalPages?'disabled':''}>Далее →</button></div></div></section><p class="rule-note">Учебные состояния — ориентир по наблюдениям, не оценка общего словарного запаса.</p>`}`;
}
function lessonView() {
  if (isConversation()) return conversationLessons();
  return `<div class="tabs" role="group" aria-label="Занятия или домашняя работа">${[['lessons','История уроков'],['homework','Домашняя работа']].map(([v,t])=>`<button class="tab ${lessonTab===v?'active':''}" data-action="lesson-tab" data-value="${v}" aria-pressed="${lessonTab===v}">${t}</button>`).join('')}</div>${lessonTab==='homework'?`<div class="grid grid-2"><div class="card"><div class="card-head"><h2>Не терять am / is / are</h2>${badge('Выдано','orange')}</div><p class="chart-note">ДЗ hw-01 · 9 октября · 12 минут в два подхода</p><div class="progress-track"><div class="progress-fill" style="width:0"></div></div><p class="rule-note">Сдано 0 из 6. Черновик прототипа не считается сохранённым ответом.</p>${detailButton('Открыть задания','homework','hw-01','primary')}</div><div class="card"><h2>Почему именно эта тема</h2><p class="chart-note">После нескольких ответов с помощью закрепляем простую связку be. Новую лексику в задания не добавляем.</p>${detailButton('Исходное наблюдение','evidence','answer-1-4','soft')}<p class="rule-note">Обоснование и задания в этом прототипе вымышлены.</p></div></div>`:`<section class="card"><div class="card-head"><h2>Сохранённые занятия</h2>${badge(lessons.filter(inPeriod).length+' занятий','')}</div><div class="table-wrap"><table class="table"><thead><tr><th>Урок</th><th>Статус</th><th>Ответы</th><th>Разбор</th><th></th></tr></thead><tbody>${lessons.filter(inPeriod).map(l=>{const job=jobs.find(j=>j.id===l.job), status=l.id==='lesson-01'&&ui.scenario==='failure'?'failed':job.status;return `<tr class="clickable" tabindex="0" data-action="detail" data-type="lesson" data-id="${l.id}"><td><strong>${dateLabel(l.date,true)}</strong><small>${l.title}</small></td><td>${badge('Завершён','')}</td><td>6 сохранено</td><td>${badge(...jobLabels[status])}</td><td>${icon('chevron')}</td></tr>`;}).join('')}</tbody></table></div></section>`}`;
}
function methodologist() {
  if (isConversation()) return conversationMethodologist();
  const visible=jobs.filter(inPeriod).map(j=>j.id===jobs[0].id&&ui.scenario==='failure'?{...j,status:'failed',attempts:3}:j).filter(j=>jobState==='all'||j.status===jobState);
  const latest=ui.scenario==='failure'?'failed':'applied';
  return `${statusNotice()}<div class="grid grid-3"><div class="card"><div class="stat-label">Последний разбор</div><div style="margin:16px 0">${badge(...jobLabels[latest])}</div><p class="stat-foot">9 октября · 09:42 · демопример</p></div><div class="card"><div class="stat-label">Ответы последнего урока</div><div style="margin:16px 0">${badge('Сохранены · 6 ответов','green')}</div><p class="stat-foot">Сохранение не зависит от результата модели</p></div><div class="card"><div class="stat-label">Предложения на согласование</div><div class="stat-number">1</div><p class="stat-foot">Пример предложения об увеличении нагрузки</p></div></div><section class="card section-space"><div class="card-head"><h2>Журнал решений</h2><select class="select" id="job-state" aria-label="Статус разбора"><option value="all">Все статусы</option>${Object.entries(jobLabels).map(([v,[t]])=>`<option value="${v}" ${v===jobState?'selected':''}>${t}</option>`).join('')}</select></div>${visible.length?visible.map(j=>`<article class="job-card"><div class="job-time"><strong>${dateLabel(j.date)}</strong>${j.time}</div><div class="job-copy">${badge(...jobLabels[j.status])}<h3 style="margin-top:10px">${j.status==='failed'?'Не удалось завершить разбор':j.title}</h3><p>${j.status==='failed'?'Ответы сохранены. Учебные изменения не применены.':j.status==='stale'?'Результат отклонён: профиль уже изменился. Старый вывод не перезаписал новый план.':j.why}</p><div class="job-meta"><span>${j.evidence.length} исходных наблюдения</span><span>${j.attempts} ${j.attempts===1?'попытка':'попытки'}</span><span>${j.pending?'1 предложение ожидает согласования':'Изменение нагрузки не применялось'}</span></div></div>${detailButton('Разбор','job',j.id,'small')}</article>`).join(''):'<div class="empty"><h3>Разборов с таким статусом нет</h3><p>Выбери другой статус или период.</p></div>'}</section><p class="rule-note">Успех обработки подтверждает работу сервиса. Учебный результат проверяется по самостоятельным ответам позднее.</p>`;
}
function materialsView(compact=false) {
  const items=materials.filter(inPeriod);
  return `<div class="grid ${compact?'grid-3':'grid-3'}">${items.map(m=>`<section class="card method-card"><div class="row-icon">${icon('materials')}</div><h2 style="margin-top:20px">${m.title}</h2><p>${m.summary}</p><div class="answer" style="font-size:18px;padding:15px">${m.text}</div><div class="materials-tag">${badge(m.origin,'purple')}${badge(m.topic,'')}</div><p class="rule-note">${m.used?'Использовано '+m.used+' раза':'Ещё не использовано'} · ${dateLabel(m.date)}</p><div class="section-space">${detailButton('Открыть материал','material',m.id,'ghost')}</div></section>`).join('')}</div>`;
}
function materialsPage() {
  if (isConversation()) return conversationMaterials();
  return `${materialsView()}<section class="card section-space"><div class="card-head"><h2>Как мы тренируем речь</h2>${badge('3 метода','green')}</div><div class="grid grid-3">${[['Извлечение без образца','Сначала свой ответ. Минимальная помощь — только если нужна.','retrieval'],['Повтор задачи','Повторяем смысловую задачу после разбора. Успех с помощью отмечаем отдельно.','repeat'],['Перенос в новую ситуацию','Проверяем знакомую форму позднее, с другим собеседником или обстоятельствами.','transfer']].map(([t,d,id])=>`<div class="method-card"><h3>${t}</h3><p>${d}</p>${detailButton('Основания и ограничения','method',id,'ghost')}</div>`).join('')}</div><p class="rule-note">Задания Coach — адаптации. Наличие источника не означает анализа всей книги.</p></section>`;
}
function settings() {
  if (isConversation()) return conversationSettings();
  return `<div class="notice info">${icon('info')}<div>Настройки показаны для просмотра. Прототип не меняет цель, профиль или подключение методолога.</div></div><div class="grid grid-2"><section class="card"><h2>Мой темп и формат</h2>${[['Цель','Рабочие и повседневные разговоры','Формулировать мысль знакомыми словами'],['Занятие','30 минут по плану','Продолжаем до твоей команды закончить или поставить на паузу'],['Домашняя работа','12 минут','Два подхода, можно выполнить часть'],['Лексика','Базовая','0–1 простая новая фраза за урок'],['Исправления','Коротко, главное','Дать возможность самому исправить ответ'],['Помощь','Постепенно','Самокоррекция → подсказка → выбор → образец']].map(([t,v,d])=>`<div class="settings-row"><div><strong>${t}</strong><p>${d}</p></div><span class="settings-value">${v}</span></div>`).join('')}</section><section><div class="card"><h2>Что считается прогрессом</h2><p class="chart-note">Самостоятельная формулировка, проверка после перерыва и использование в другой ситуации. Повтор после образца учитывается как помощь.</p>${detailButton('Правила показателей','metrics','all','soft')}</div><div class="card section-space"><h2>Технические сведения</h2><details><summary style="cursor:pointer;font-size:12px">Развернуть сведения о подключении</summary><div class="settings-row"><span class="muted">Режим</span><strong>Демо · API не подключён</strong></div><div class="settings-row"><span class="muted">Модель</span><span>Запросов к модели нет</span></div><div class="settings-row"><span class="muted">Данные</span><span>Вымышленные примеры</span></div><div class="settings-row"><span class="muted">Хранение черновиков</span><span>В памяти вкладки</span></div></details></div><div class="card section-space"><h2>Экспорт демообзора</h2><p class="chart-note">Скачать вымышленные показатели за выбранный период, с правилами расчёта и пометкой «demo».</p>${button('Скачать JSON','export','','soft','download')}</div></section></div>`;
}
function evidenceRows(ids) {
  const aa=ids.map(id=>observations.find(a=>a.id===id)).filter(Boolean);
  return aa.map(a=>`<button class="link-row" data-action="detail" data-type="evidence" data-id="${a.id}"><div class="list-row"><span class="row-icon ${a.outcome==='incorrect'?'orange':''}">${icon(a.outcome==='correct'?'check':'help')}</span><div class="row-copy"><h3>${esc(a.text)}</h3><p>${dateLabel(a.date)} · ${assistanceLabel[a.assistance]} · ${outcomeLabel[a.outcome]}</p></div>${icon('chevron')}</div></button>`).join('')||'<p class="muted">Подтверждающих ответов пока нет.</p>';
}
function showDetail(type,id) {
  if(type==='release')return releaseDetail(id);
  if(type==='family')return familyDetail();
  if(isConversation()){const content=conversationDetail(type,id);if(content!==null)return content;}
  const title=(t)=>`<h2 id="detail-title">${esc(t)}</h2>`;
  if(type==='stage') {
    const s=stages.find(s=>s.id===id);if(!s)return missing();
    return `${badge(s.id==='questions'?'Текущий этап · диагностика':'Впереди',s.id==='questions'?'green':'')}<div style="margin-top:18px">${title(s.title)}</div><p>${s.target}</p><div class="key-value"><span>Формы в работе</span><strong>${s.forms}</strong></div><h3>Почему этот этап</h3><p>${s.reason}</p><h3>Критерий следующего шага</h3><p>${s.criterion}</p><h3>Пример самостоятельной проверки</h3><div class="card"><p>${s.prompt}</p>${badge('Без открытого образца','green')}</div><h3>Методическая основа</h3><p class="muted">${s.source}. Задание — оригинальная адаптация Coach.</p><div class="drawer-actions">${detailButton('Вывод методолога','job',jobs[0].id,'soft')}${navigateButton('Вся программа','program')}</div>`;
  }
  if(type==='skill') {
    const skill=skills.find(s=>s.id===id);if(!skill)return missing();
    const s=stats(id), entries=s.all;
    return `${title(skill.title)}<p class="muted">${skill.subtitle}</p><div class="card"><div class="stat-label">Самостоятельно за выбранный период</div><div class="stat-number">${fraction(s)}</div><p class="rule-note">${s.assisted} ответов с помощью · ${s.ambiguous} неоднозначных отдельно</p></div><h3>Режимы проверки</h3>${[['controlled','Контролируемое задание'],['cold','До разминки'],['free','Свободная речь']].map(([mode,label])=>{const aa=s.independent.filter(a=>a.mode===mode);return `<div class="key-value"><span>${label}</span><strong>${aa.length?aa.filter(a=>a.outcome==='correct').length+' / '+aa.length:'Нет проверок'}</strong></div>`;}).join('')}<h3>Сохранённые ответы</h3>${evidenceRows(entries.map(a=>a.id))}<div class="drawer-actions">${detailButton('Методологический вывод','job',jobs[0].id,'soft')}</div>`;
  }
  if(type==='evidence') {
    const a=observations.find(a=>a.id===id);if(!a)return missing();
    return `${title('Исходный ответ')}<span class="code-id">${a.id}</span><div class="key-value"><span>Дата</span><strong>${dateLabel(a.date,true)}</strong></div><h3>Задание</h3><p>${a.prompt}</p><h3>Ответ ученика · демопример</h3><div class="answer ${a.outcome==='incorrect'?'wrong':''}">${a.text}</div><div class="arrow-flow">${badge(outcomeLabel[a.outcome],a.outcome==='incorrect'?'orange':a.outcome==='correct'?'green':'')}${badge(assistanceLabel[a.assistance],'')}</div><h3>Интерпретация преподавателя</h3><p>${a.outcome==='incorrect'?'Целевая форма требует исправления. Сначала предложить самостоятельную попытку.':a.outcome==='ambiguous'?'Смысл или целевая форма не оценены достаточно уверенно. Не включаем в точность.':'Форма подходит для данной задачи. Самостоятельность определяется фактической помощью.'}</p>${a.outcome==='incorrect'?`<details><summary>Показать пример исправления</summary><div class="answer">${a.correction}</div><p class="rule-note">Это формулировка преподавателя, не новый самостоятельный ответ ученика.</p></details>`:''}<div class="drawer-actions">${detailButton('Открыть урок','lesson',a.lesson,'primary')}${detailButton('Связанный разбор','job',lessons.find(l=>l.id===a.lesson).job)}</div>`;
  }
  if(type==='lesson') {
    const l=lessons.find(l=>l.id===id);if(!l)return missing();
    return `${badge('Завершён','')}<div style="margin-top:18px">${title('Урок '+dateLabel(l.date,true))}</div><p>${l.title}</p><span class="code-id">${l.id}</span><div class="key-value"><span>Методика этого урока</span><strong>Основа английского · ${l.id==='lesson-01'?'1.1-demo':'1.0-demo'}</strong></div><p class="rule-note">Текущая версия: ${activeProfile.methodVersion}. Это демонстрационные снимки методики.</p><div class="key-value"><span>Нагрузка</span><strong>${l.time}</strong></div><p class="rule-note">Фактическая длительность речи не измерялась.</p><h3>План занятия</h3><ul class="detail-list"><li>Короткие вопросы в знакомой ситуации</li><li>Проверить состояние и действие в прошлом</li><li>Подтвердить время следующей встречи</li></ul><h3>Сохранённые наблюдения</h3>${evidenceRows(observations.filter(a=>a.lesson===l.id).map(a=>a.id))}<h3>Незавершённое</h3><p>Проверка похожего вопроса в новой ситуации сохранена для продолжения.</p><div class="drawer-actions">${detailButton('Разбор методолога','job',l.job,'primary')}${detailButton('Домашнее закрепление','homework','hw-01')}</div><p class="rule-note">Все уроки и связи в прототипе — демонстрационные.</p>`;
  }
  if(type==='job') {
    const original=jobs.find(j=>j.id===id);if(!original)return missing();
    const j=id===jobs[0].id&&ui.scenario==='failure'?{...original,status:'failed',attempts:3}:original;
    return `${badge(...jobLabels[j.status])}<div style="margin-top:18px">${title('Разбор '+dateLabel(j.date,true))}</div><span class="code-id">${j.id}</span><div class="key-value"><span>Методика на входе</span><strong>${j.lesson==='lesson-01'?'1.1-demo':'1.0-demo'}</strong></div><div class="key-value"><span>Что запустило разбор</span><strong>Явное сохранение урока</strong></div><div class="key-value"><span>Попытки обработки</span><strong>${j.attempts}</strong></div><div class="key-value"><span>Входные данные</span><strong>6 ответов · 1 урок</strong></div><div class="key-value"><span>Модель этого разбора</span><strong>Не записана в демопримере</strong></div>${j.status==='applied'?`<h3>Наблюдение</h3><p>Порядок слов в самостоятельных вопросах пока неоднороден.</p><h3>Вывод методолога</h3><p>${j.why}</p>${badge('Гипотеза · требует проверки','orange')}<h3>Основания вывода</h3>${evidenceRows(j.evidence)}<h3>Что изменено</h3><div class="diff before"><small>Раньше</small>${j.before}</div><div class="diff after"><small>Теперь</small>${j.after}</div><h3>Как проверить решение</h3><p>На следующем уроке задать вопрос о месте и времени без подсказки. Затем изменить ситуацию.</p>${j.pending?'<div class="notice">Предложено увеличить нагрузку до 35 минут. Ожидает согласования; текущие 30 минут сохранены.</div>':''}`:`<div class="notice section-space">${icon('info')}<div><strong>Учебные изменения не применены.</strong><br>${j.status==='failed'?'Модель не ответила в пределах таймаута. Бюджет повторов исчерпан.':'Входная версия устарела, пока выполнялся разбор.'}</div></div><h3>Что сохранено</h3><p>Все исходные ответы и завершение урока. Домашнее задание доступно независимо от модельного разбора.</p><h3>Исходные ответы</h3>${evidenceRows(j.evidence)}`}<div class="drawer-actions">${detailButton('Исходный урок','lesson',j.lesson,'soft')}${navigateButton('Посмотреть план','program')}${detailButton('ДЗ','homework','hw-01')}</div><details class="section-space"><summary>Снимок и версии · демопример</summary><div class="key-value"><span>Профиль на входе</span><strong>demo-v1</strong></div><div class="key-value"><span>Программа на входе</span><strong>demo-v1</strong></div><p class="rule-note">Охват — 6 из 6 сохранённых ответов данного демоурока. Расход и точная длительность не записаны.</p></details>`;
  }
  if(type==='phrase') {
    const p=phrases.find(p=>p.id===id);if(!p)return missing();
    return `${badge(...lexicalStates[p.state])}<div style="margin-top:18px">${title(p.phrase)}</div><p class="callout-big">${p.meaning}</p><div class="key-value"><span>Последняя практика</span><strong>${dateLabel(p.date,true)}</strong></div><div class="key-value"><span>Состояние</span><strong>Демонстрационный пример</strong></div><h3>Как читать этот статус</h3><p>${p.state==='seen'?'Фраза показана. Самостоятельного употребления ещё не проверяли.':p.state==='assisted'?'Фраза получилась с помощью. Следующая проверка — без открытого образца.':'Есть пример самостоятельного употребления. Проверка в иной ситуации и позднее остаётся отдельным шагом.'}</p><h3>Пример употребления</h3><div class="answer">${phraseExamples[phrases.indexOf(p)]}</div><p class="rule-note">Демонстрационный пример. Значение фразы и грамматика проверяются отдельно.</p><div class="key-value"><span>Самостоятельные проверки</span><strong>${["seen","assisted"].includes(p.state)?"Ещё нет":p.uses+" / "+p.total}</strong></div>${detailButton("Связанный демоурок","lesson",lessons[phrases.indexOf(p)%lessons.length].id,"soft")}<h3>Следующий шаг</h3><p>Короткая новая ситуация со знакомыми словами, без открытого образца фразы.</p><div class="drawer-actions">${navigateButton('Учебный словарь','vocabulary','soft')}</div>`;
  }
  if(type==='homework') {
    if(isConversation()||id!=='hw-01')return missing();
    return `${badge('12 минут · два подхода','orange')}<div style="margin-top:18px">${title('Не терять am / is / are')}</div><span class="code-id">hw-01 · демонстрационное ДЗ</span><p class="section-space">6–8 минут сейчас. Второй подход после перерыва, лучше позднее или завтра. Ключи в прототипе не выдаются.</p><div class="notice info">${icon('info')}<div>Можно попробовать ввод ответов. Это черновик в памяти вкладки: он не отправляется методологу и не считается проверенным.</div></div>${homework.map(h=>`<div class="homework-item">${badge(h.phase==='practice'?'Первый подход':'Позднее · без образца',h.phase==='practice'?'':'purple')}<h3>${h.id}. ${h.prompt}</h3><div class="field"><label for="answer-${h.id}">Твой ответ</label><textarea class="input" id="answer-${h.id}" data-draft="${h.id}" placeholder="Коротко, знакомыми словами">${esc(draftAnswers[h.id]||'')}</textarea></div></div>`).join('')}<div class="drawer-actions">${button('Оставить демочерновик','save-draft','','primary','check')}${detailButton('Связанный разбор','job',jobs[0].id)}</div>`;
  }
  if(type==='metrics')return `${title('Как считаются показатели')}<ul class="detail-list"><li><strong>Самостоятельная точность</strong>Правильные самостоятельные ответы / все самостоятельные оценённые ответы. Неоднозначные оценки отдельно.</li><li><strong>Помощь</strong>Подсказки и повтор после образца не попадают в самостоятельный успех.</li><li><strong>Период</strong>Демонстрационные ответы за выбранные 7, 14, 30 дней или всю демоисторию. Один исходный ID считается один раз.</li><li><strong>Словарь</strong>Зарегистрированные фразы — покрытие учёта, не общий размер словарного запаса.</li><li><strong>Перенос</strong>Проверка после перерыва в другой ситуации. Короткий перерыв не доказывает долгосрочного освоения.</li><li><strong>Ограничения</strong>По тексту не измеряем CEFR, скорость, произношение и автоматизм. Все цифры этого прототипа — вымышленные примеры.</li></ul>`;
  if(type==='retention')return `${title('Проверки позднее')}<p>Демонстрационные самостоятельные ответы в новой ситуации на более позднюю дату. Это примеры наблюдений, а не сертификация освоения.</p>${evidenceRows(rows().filter(a=>a.later).map(a=>a.id))}`;
  if(type==='material') {
    const m=materials.find(m=>m.id===id);if(!m)return missing();
    return `${badge(m.origin,'purple')}<div style="margin-top:18px">${title(m.title)}</div><p>${m.summary}</p><div class="answer">${m.text}</div><p class="muted">${m.meaning}</p><h3>Почему выбран</h3><p>Короткая полезная ситуация, которую можно разыграть знакомыми словами.</p><div class="key-value"><span>Использование упражнения</span><strong>${m.used} раза</strong></div><div class="key-value"><span>ID упражнения</span><strong>${m.exercise}</strong></div><h3>Проверка переноса</h3><p>Изменить собеседника и время. Попросить свою формулировку без сохранённой фразы.</p><p class="rule-note">Полный исходник встречи не хранится в прототипе. Материал не является результатом ученика.</p><div class="drawer-actions">${m.lesson?detailButton('Пример использования','lesson',m.lesson,'soft'):navigateButton('Мой маршрут','program','soft')}</div>`;
  }
  if(type==='method')return `${title({retrieval:'Извлечение без образца',repeat:'Повтор коммуникативной задачи',transfer:'Перенос в новую ситуацию'}[id]||'Метод практики')}<h3>Как применяется</h3><p>Один короткий вопрос, собственная попытка, помощь по необходимости и следующая проверка без образца.</p><h3>Что проверяем</h3><p>Смысл, целевую форму и понятность знакомых слов. Повтор после объяснения не считаем самостоятельным освоением.</p><h3>Основания и ограничения</h3><p>В программе Coach предусмотрены извлечение, повтор задач и перенос. Этот прототип показывает интерфейс описания метода; научная оценка эффективности здесь не проводится.</p>${detailButton('Пример исходного ответа','evidence','answer-1-3','soft')}`;
  if(type==='search') {
    const q=ui.q.toLowerCase().trim(), results=[];
    stages.filter(s=>`${s.title} ${s.forms}`.toLowerCase().includes(q)).forEach(s=>results.push({title:s.title,sub:'Этап программы',type:'stage',id:s.id}));
    phrases.filter(p=>`${p.phrase} ${p.meaning}`.toLowerCase().includes(q)).forEach(p=>results.push({title:`${p.phrase} — ${p.meaning}`,sub:'Учебная фраза · демопример',type:'phrase',id:p.id}));
    lessons.filter(l=>`${l.id} ${l.title} ${l.date} ${dateLabel(l.date)}`.toLowerCase().includes(q)).forEach(l=>results.push({title:`Урок ${dateLabel(l.date,true)}`,sub:l.title,type:'lesson',id:l.id}));
    jobs.filter(j=>`${j.id} ${j.title}`.toLowerCase().includes(q)).forEach(j=>results.push({title:j.title,sub:j.id,type:'job',id:j.id}));
    materials.filter(m=>`${m.title} ${m.text}`.toLowerCase().includes(q)).forEach(m=>results.push({title:m.title,sub:'Рабочий материал',type:'material',id:m.id}));
    return `${title('Поиск: '+ui.q)}<p class="muted">Найдено ${results.length} в демонстрационных данных</p>${results.length?results.map(r=>`<button class="search-result" data-action="detail" data-type="${r.type}" data-id="${r.id}">${esc(r.title)}<small>${esc(r.sub)} →</small></button>`).join(''):'<div class="empty"><h3>Совпадений нет</h3><p>Попробуй «вопросы», «at home» или «lesson-01».</p></div>'}`;
  }
  return missing();
  function missing(){return title('Запись не найдена')+'<p>В демонстрационных данных нет такой записи.</p>';}
}
function render() {
  const previousDetail=ui.detail, previousPage=ui.page;
  readRoute();sidebar();
  document.getElementById('learner-profile').value=ui.profile;
  document.querySelector('.topbar .avatar').textContent=activeProfile.initial;
  applyTheme(document.documentElement.dataset.themeMode);
  document.getElementById('breadcrumb').textContent=pageInfo(ui.page)[0];
  document.getElementById('global-search').value=ui.q;
  const views={overview,program,progress,vocabulary,lessons:lessonView,methodologist,materials:materialsPage,settings};
  document.getElementById('main').innerHTML=heading()+views[ui.page]()+(ui.page==='settings'&&!isConversation()?familyManagementCard():'');
  const dialog=document.getElementById('detail-dialog');
  if(ui.detail) {
    const [type,...rest]=ui.detail.split(':');
    document.getElementById('detail-body').innerHTML=showDetail(type,rest.join(':'));
    if(!dialog.open)dialog.showModal();
    dialog.scrollTop=0;
  } else if(previousDetail||dialog.open) {
    const [type,...ids]=(previousDetail||'').split(':');
    detailFocusTarget=document.querySelector(`[data-action="detail"][data-type="${CSS.escape(type)}"][data-id="${CSS.escape(ids.join(':'))}"]`);
    if(dialog.open)dialog.close();
    else (detailFocusTarget||document.getElementById('main')).focus({preventScroll:true});
  } else if(previousPage&&previousPage!==ui.page)document.getElementById('main').focus({preventScroll:true});
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('menu-button').setAttribute('aria-expanded','false');
}
function toast(message) {
  clearTimeout(toastTimer);const el=document.getElementById('toast');el.textContent=message;el.classList.add('visible');
  toastTimer=setTimeout(()=>el.classList.remove('visible'),4500);
}
document.addEventListener('click',e=>{
  if(e.target.closest('.skip-link')){e.preventDefault();document.getElementById('main').focus();return;}
  const el=e.target.closest('[data-action]');if(!el)return;
  const {action,page,type,id,value}=el.dataset;
  if(action==='enable-grammar'&&isConversation()&&document.getElementById('grammar-consent')?.checked){demoPreferences.katya.grammar=true;route({detail:null});toast('Грамматические задания разрешены только в демопрофиле Кати. Настоящая методика не изменена.');}
  if(action==='disable-grammar'&&isConversation()){demoPreferences.katya.grammar=false;render();toast('Грамматические задания снова выключены в демопрофиле Кати.');}
  if(action==='navigate')route({page,detail:null,filter:null,vp:null});
  if(action==='detail')route({detail:type+':'+id});
  if(action==='close-detail')route({detail:null});
  if(action==='plan-tab')route({plan:value});
  if(action==='vocabulary-tab')route({vtab:value,vp:1,detail:null,filter:null});
  if(action==='lesson-tab')route({ltab:value});
  if(action==='vocabulary-page')route({vp:value});
  if(action==='save-draft')toast('Демочерновик оставлен в этой вкладке. Не отправлен и не проверен; после перезагрузки будет очищен.');
  if(action==='export') {
    const s=stats(), payload={demo:true,generated_at:'2026-10-09',learner_id:activeProfile.id,learner_name:activeProfile.name,methodology:{name:activeProfile.method,version:activeProfile.methodVersion},period:ui.period,independent:{correct:s.correct,total:s.total},assisted:s.assisted,ambiguous:s.ambiguous,rules:'Only independent known outcomes; unique fictional observation IDs. Not a real learner report.'};
    const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='english-coach-'+activeProfile.id+'-demo.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast('Скачан демонстрационный обзор, не отчёт реального ученика.');
  }
});
document.addEventListener('change',e=>{
  if(e.target.id==='learner-profile')route({profile:e.target.value,page:ui.page,period:ui.period,scenario:ui.scenario},true);
  if(e.target.id==='theme-mode')applyTheme(e.target.value,true);
  if(e.target.id==='grammar-consent')document.getElementById('enable-grammar').disabled=!e.target.checked;
  if(e.target.id==='period')route({period:e.target.value,vp:1});
  if(e.target.id==='scenario')route({scenario:e.target.value,detail:null});
  if(e.target.id==='vocabulary-state')route({vstate:e.target.value,vp:1});
  if(e.target.id==='job-state')route({jstate:e.target.value});
});
document.addEventListener('input',e=>{
  if(e.target.dataset.draft)draftAnswers[e.target.dataset.draft]=e.target.value;
});
document.addEventListener('keydown',e=>{
  if(e.target.id==='vocabulary-search'&&e.key==='Enter'){e.preventDefault();route({filter:e.target.value,vp:1});}
  if(e.target.tagName==='TR'&&e.target.dataset.action&&(e.key==='Enter'||e.key===' ')){
    e.preventDefault();e.target.click();
  }
});
document.addEventListener('focusout',e=>{
  if(e.target.id==='vocabulary-search'&&e.target.value!==localQuery)route({filter:e.target.value,vp:1});
});
document.getElementById('search-form').addEventListener('submit',e=>{
  e.preventDefault();const q=document.getElementById('global-search').value.trim();
  if(q)route({q,detail:'search:all'});
});
document.getElementById('menu-button').innerHTML=icon('menu');
document.getElementById('search-icon').innerHTML=icon('search');
document.getElementById('menu-button').addEventListener('click',()=>{
  const isOpen=document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('menu-button').setAttribute('aria-expanded',String(isOpen));
});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&document.getElementById('sidebar').classList.contains('open')){
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('menu-button').setAttribute('aria-expanded','false');
    document.getElementById('menu-button').focus();
  }
});
document.getElementById('detail-dialog').addEventListener('cancel',e=>{e.preventDefault();route({detail:null});});
document.getElementById('detail-dialog').addEventListener('close',()=>{
  if(!ui.detail)(detailFocusTarget?.isConnected?detailFocusTarget:document.getElementById('main')).focus({preventScroll:true});
});
document.getElementById('detail-dialog').addEventListener('click',e=>{if(e.target===e.currentTarget&&e.clientX<e.currentTarget.getBoundingClientRect().left)route({detail:null});});
window.addEventListener('hashchange',render);
render();
