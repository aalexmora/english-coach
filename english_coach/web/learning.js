'use strict';
const el=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const label={draft:'Черновик',active:'Активен',archived:'В архиве',queued:'Ожидает',running:'Обрабатывается',
 proposed:'Ожидает подтверждения',applied:'Применён',failed:'Ошибка',stale:'Устарел',rejected:'Отклонён',expired:'Истёк'};
const box=(name,content)=>'<section class="card"><h2>'+esc(name)+'</h2>'+content+'</section>';
const field=(name,text,value='',required=true)=>'<label>'+esc(text)+'<input class="input" name="'+name+'" value="'+esc(value)+'" '+(required?'required':'')+' maxlength="500"></label>';
let csrf='',actor='',profiles=[],selected=new URLSearchParams(location.hash.slice(1)).get('profile'),tab='profiles',detail=null;
const key=()=>crypto.randomUUID();
async function request(view,post=null,params={}){
 const u=new URL('/english/api/learning',location.origin);
 if(!post)u.searchParams.set('view',view);
 Object.entries(params).forEach(([k,v])=>u.searchParams.set(k,v));
 const r=await fetch(u,{method:post?'POST':'GET',credentials:'same-origin',
  headers:post?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},
  body:post?JSON.stringify(post):undefined});
 const v=await r.json();if(!r.ok)throw Error(v.error||'HTTP '+r.status);return v;
}
function message(t){el('learning-error').textContent=t;}
function button(action,name,extra=''){return '<button class="btn soft" data-action="'+action+'" '+extra+'>'+esc(name)+'</button>';}
function sourceOptions(target){
 const choices=profiles.filter(p=>p.profile_id!==target.profile_id&&p.language===target.language&&p.state!=='archived');
 if(target.language==='en')choices.unshift({profile_id:actor,name:'Мой основной English'});
 return '<option value="">Не копировать</option>'+choices.map(p=>'<option value="'+esc(p.profile_id)+'">'+esc(p.name)+'</option>').join('');
}
function profileCard(p){
 return '<article class="record"><div class="row-head"><div><b>'+esc(p.name)+'</b><p class="muted small">'+
 esc(p.language)+' · '+esc(label[p.state]||p.state)+'</p></div>'+
 (p.state==='archived'?
 button('restore','Восстановить','data-id="'+esc(p.profile_id)+'" data-version="'+p.version+'"'):
 button('select','Открыть','data-id="'+esc(p.profile_id)+'"'))+'</div></article>';
}
function createForm(){
 return box('Новый учебный профиль',
  '<form id="new-profile">'+field('name','Название, например Español для путешествий')+
  '<label>Изучаемый язык (ISO 639, например en, es, de)<input class="input" name="language" pattern="[a-z]{2,3}(-[A-Za-z]{2,4})?" value="es" maxlength="10" required></label>'+
  '<label>Язык объяснений<input class="input" name="explanation_language" value="ru" maxlength="10" required></label>'+
  '<p class="muted small">Сначала создадим пустой профиль. Затем предложим перенос знаний либо спросим ваш текущий уровень.</p>'+
  '<button class="btn primary">Создать профиль</button></form>');
}
function optionsForLevel(v=''){
 const levels=[['','Не знаю (методолог проведёт диагностику)'],['A0','Начинаю с нуля'],['A1','A1 · начинающий'],['A2','A2 · базовый'],['B1','B1 · средний'],['B2','B2 · уверенный'],['C1','C1 · продвинутый'],['C2','C2 · свободное владение']];
 return '<label>Примерный текущий уровень<select class="select" name="level">'+
 levels.map(([id,title])=>'<option value="'+id+'" '+(id===v?'selected':'')+'>'+esc(title)+'</option>').join('')+'</select></label>';
}
function goalForm(p,imported){
 return box('Цели · '+p.name,
  '<p>Укажи свою цель и интересы. Методолог сам составит программу для выбранного языка.</p>'+
  (imported?'<p class="notice">Импортированные знания — только контекст, не подтверждение освоения.</p>':'')+
  '<form id="goal-form" data-id="'+esc(p.profile_id)+'">'+
  '<label>Что хочешь уметь?<textarea class="input" name="goal" minlength="5" maxlength="500" required placeholder="Например: свободно общаться в путешествиях"></textarea></label>'+
  '<label>Интересы, через запятую<input class="input" name="interests" value="путешествия, повседневные ситуации" required></label>'+
  '<label>Минут на урок<input class="input" type="number" name="minutes" min="5" max="120" value="20" required></label>'+
  optionsForLevel(p.initial_level||'')+
  '<button class="btn primary">Согласовать цель и подготовить план</button></form>');
}
function onboarding(p,ctx){
 const hasGoal=Boolean(ctx?.readiness?.goal_version);
 if(hasGoal)return '';
 const imported=Boolean(ctx?.imported_context);
 return box('Начало обучения',
 '<p>Хочешь однократно скопировать учебные знания из другого профиля того же языка?</p>'+
 '<form id="copy-choice" data-id="'+esc(p.profile_id)+'"><label>Источник знаний<select class="select" name="source">'+sourceOptions(p)+'</select></label>'+
 '<button class="btn primary">Продолжить</button></form>'+
 '<p class="muted small">Если копирование не нужно, просто выбери «Не копировать» и укажи свой примерный уровень.</p>')+
 (imported?goalForm(p,true):'');
}
function proposedPlan(p,ctx){
 const proposal=ctx?.proposal;if(!proposal || ctx.readiness?.status!=='proposed')return '';
 const plan=proposal.value.plan;
 return box('Методолог предлагает программу',
  '<p>'+esc(plan.rationale)+'</p><ol class="route">'+plan.steps.map(s=>
    '<li><b>'+esc(s.topic)+'</b><p>'+esc(s.communicative_goal)+'</p></li>').join('')+'</ol>'+
  button('approve','Утвердить программу','data-id="'+esc(p.profile_id)+'" data-version="'+proposal.version+'"')+' '+
  button('reject','Отклонить','data-id="'+esc(p.profile_id)+'" data-version="'+proposal.version+'"'));
}
function projectInstructions(p){
 return 'В этом ChatGPT Project используй учебный профиль '+p.profile_id+
 '. Перед новым занятием получи get_language_learning_context(profile_id="'+p.profile_id+
 '"), проверь фактическую готовность плана. Работай только с этим profile_id во всех вызовах Learning tools. '+
 'Не переключайся на другой профиль по смыслу сообщений. Не считай подсказанные повторы самостоятельным освоением. '+
 'После каждого моего ответа дай короткую обратную связь и следующее задание по плану. '+
 'Занятие продолжается до моей явной просьбы закончить или сделать паузу.';
}
function readyProgram(p,ctx){
 const program=ctx?.program;if(!program)return '';
 return box('Действующий план',
  '<p class="muted small">Версия '+program.version+' · '+esc(label[ctx.readiness.status]||ctx.readiness.status)+
  ' · следующий этап: '+esc(program.value.next_step_id)+'</p>'+
  '<ol class="route">'+program.value.steps.map(s=>'<li><b>'+esc(s.topic)+
  '</b><p>'+esc(s.communicative_goal)+'</p></li>').join('')+'</ol>'+
  '<details><summary>Привязка к ChatGPT Project</summary>'+
  '<p class="muted">Добавь текст ниже в Project instructions. Инструкции не заменяют серверную проверку доступа.</p>'+
  '<pre id="project-instructions">'+esc(projectInstructions(p))+'</pre>'+
  button('copy-project','Копировать инструкции','data-id="'+esc(p.profile_id)+'"')+'</details>');
}
async function showProfile(id){
 selected=id;history.replaceState(null,'','#'+new URLSearchParams({profile:id}));const data=await request('profile',null,{profile_id:id});detail=data;
 const p=data.profile,ctx=data.context;
 el('learning-content').innerHTML='<div class="actions learning-inline-actions">'+button('back','← Все профили')+
 button('archive',p.state==='archived'?'Восстановить':'Архивировать','data-id="'+esc(id)+'" data-version="'+p.version+'" data-state="'+(p.state==='archived'?'active':'archived')+'"')+'</div>'+
 '<a class="text-link" href="/english#'+new URLSearchParams({profile:id,page:'home'})+'">На главную этого профиля →</a>'+
 box(p.name,'<p class="muted">'+esc(p.language)+' · '+esc(label[p.state]||p.state)+'</p><p>План: '+
 esc(label[ctx.readiness.status]||ctx.readiness.status)+' · '+(ctx.readiness.lesson_ready?'готов':'ожидает')+'</p>')+
 (ctx.goal?box('К чему идём','<p class="lead">'+esc(ctx.goal.value.goal)+'</p><p class="muted">'+ctx.goal.value.minutes+' минут на урок · '+esc(ctx.goal.value.interests.join(', '))+'</p>'):'')+
 onboarding(p,ctx)+proposedPlan(p,ctx)+readyProgram(p,ctx)+
 (ctx.readiness.status==='queued'||ctx.readiness.status==='running'?
 box('Разбор в работе','<p>Job ID: '+esc(ctx.readiness.job_id)+'</p>'+button('reload','Проверить готовность')):'')+
 (ctx.readiness.status==='failed'||ctx.readiness.status==='stale'?
 box('Разбор не применён','<p>История ответов сохранена. Обновление плана не применено.</p>'+button('retry','Повторить разбор','data-id="'+esc(p.profile_id)+'" data-job="'+esc(ctx.readiness.job_id)+'"')):'');
}
async function showProfiles(){
 const data=await request('profiles');csrf=data.csrf;actor=data.actor;profiles=data.profiles;
 el('learning-content').innerHTML='<div class="columns">'+
 box('Мои профили',profiles.length?profiles.map(profileCard).join(''):'<p>Профилей пока нет.</p>')+
 createForm()+'</div>';
}
async function showJobs(){
 const data=await request('jobs');
 el('learning-content').innerHTML=box('Задания методолога',
 button('reload','Обновить статус')+
 (data.jobs.length?data.jobs.map(j=>
 '<article class="record"><div class="row-head"><b>'+esc(j.profile_name)+
 '</b><span class="badge">'+esc(label[j.status]||j.status)+'</span></div>'+
 '<p class="muted small">'+esc(j.kind)+' · '+esc(j.job_id)+'</p></article>').join(''):
 '<p class="muted">Заданий пока нет.</p>')+
 '<p class="muted small">Статусы читаются отдельно. Прогресс считается применённым только при серверном статусе applied.</p>');
}
async function navigate(){
 message('');
 for(const name of ['profiles','jobs']){const b=el(name+'-tab');b.className='btn '+(tab===name?'primary':'soft');b.setAttribute('aria-current',tab===name?'page':'false');}
 if(tab==='jobs')await showJobs();else if(selected)await showProfile(selected);else await showProfiles();
}
document.addEventListener('click',async ev=>{
 const b=ev.target.closest('button');if(!b)return;
 try{
  if(b.dataset.tab){tab=b.dataset.tab;selected=null;history.replaceState(null,'',location.pathname);await navigate();return;}
  const action=b.dataset.action,id=b.dataset.id;
  if(action==='back'){selected=null;history.replaceState(null,'',location.pathname);await navigate();return;}
  if(action==='select'){await showProfile(id);return;}
  if(action==='restore'){
    if(!confirm('Восстановить учебный профиль?'))return;
    await request(null,{action:'update',profile_id:id,idempotency_key:key(),
      expected_version:Number(b.dataset.version),state:'active'});
    await showProfiles();return;
  }
  if(action==='reload'){await navigate();return;}
  if(action==='retry'){
    if(!confirm('Повторить разбор методолога на актуальных данных?'))return;
    await request(null,{action:'retry',profile_id:id,
      job_id:b.dataset.job,idempotency_key:key()});
    await showProfile(id);return;
  }
  if(action==='approve'||action==='reject'){
    const result=await request(null,{action:'approve',profile_id:id,idempotency_key:key(),
       expected_proposal_version:Number(b.dataset.version),approved:action==='approve'});
    message(result.approved?'План утверждён.':'Предложение отклонено.');await showProfile(id);return;
  }
  if(action==='archive'){
    if(!confirm('Изменить состояние профиля? История сохраняется.'))return;
    await request(null,{action:'update',profile_id:id,idempotency_key:key(),
      expected_version:Number(b.dataset.version),state:b.dataset.state});
    selected=null;history.replaceState(null,'',location.pathname);await showProfiles();return;
  }
  if(action==='copy-project'){
    await navigator.clipboard.writeText(projectInstructions(detail.profile));
    message('Инструкции скопированы. Вставь их в ChatGPT Project instructions.');return;
  }
 }catch(e){message('Не удалось выполнить действие: '+e.message);}
});
document.addEventListener('submit',async ev=>{
 const f=ev.target;if(!['new-profile','copy-choice','goal-form'].includes(f.id))return;
 ev.preventDefault();const b=f.querySelector('button');b.disabled=true;
 try{
  const data=Object.fromEntries(new FormData(f));
  if(f.id==='new-profile'){
    const created=await request(null,{action:'create',idempotency_key:key(),name:data.name,
      language:data.language,explanation_language:data.explanation_language});
    await showProfiles();await showProfile(created.profile_id);return;
  }
  if(f.id==='copy-choice'){
    if(data.source){
      await request(null,{action:'import',profile_id:f.dataset.id,
        source_profile_id:data.source,idempotency_key:key()});
      await showProfile(f.dataset.id);
      message('Учебный контекст однократно перенесён. История попыток и оценки не копировались.');
    } else {
      el('learning-content').insertAdjacentHTML('beforeend',goalForm(detail.profile,false));
      message('Теперь укажи свой приблизительный уровень или выбери диагностику.');
    }
    return;
  }
  if(f.id==='goal-form'){
    await request(null,{action:'configure',profile_id:data.id||f.dataset.id,
      idempotency_key:key(),goal:data.goal,minutes:Number(data.minutes),
      interests:data.interests.split(',').map(s=>s.trim()).filter(Boolean),
      level:data.level||null,confirmed:true});
    message('Цель сохранена. План поставлен в очередь методолога.');await showProfile(f.dataset.id);
  }
 }catch(e){message('Не удалось сохранить: '+e.message);}finally{b.disabled=false;}
});
const theme=el('learning-theme');
theme.value=document.documentElement.dataset.themeMode||'system';
theme.addEventListener('change',()=>window.coachTheme(theme.value,true));
(async()=>{try{const data=await request('profiles');csrf=data.csrf;actor=data.actor;profiles=data.profiles;await navigate();}catch(e){message('Кабинет недоступен: '+e.message);}})();
