"""Personal browser authorization and factual UI projections over public host APIs."""
import asyncio,hashlib,re,time
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient
from saver.auth import AuthProvider
from saver.store import Store,StoreError
from saver.memory import MemoryAPI
from saver.legacy_english import LegacyEnglishAPI
from saver.english_web import routes,COOKIE
from english_coach.coach import Coach
from english_coach.admin import AdminRead,AdminAction,SECTIONS
from english_coach.homework import Homework
from english_coach.methodologist import Worker,TestProvider

BASE='http://localhost:8000'
OWNER='synthetic-owner-secret'
PERSONAL='synthetic-family-secret'

def token(page):return re.search(r'name="csrf" value="([^"]+)"',page.text)[1]
def login(client,subject='',secret=OWNER):
    page=client.get('/english/login')
    return client.post('/english/login',headers={'Origin':BASE},data=dict(csrf=token(page),login=subject,secret=secret),follow_redirects=False)

def observation(key,assistance='independent',outcome='correct',at=None):
    return dict(idempotency_key=key,pattern_id='past_simple_questions',occurred_at=at or datetime.now(timezone.utc).isoformat(),outcome=outcome,assistance=assistance,context='family trip',mode='free',observation='Did you call Anna?')

@pytest.fixture
def web(tmp_path):
    store=Store(tmp_path/'memory.sqlite',tmp_path/'export');provider=AuthProvider(tmp_path/'auth.sqlite',BASE,hashlib.sha256(OWNER.encode()).hexdigest())
    def make(user):
        store.register_user(user,('english',))
        return Coach(MemoryAPI(store,user,'english',['english']),LegacyEnglishAPI(store,user,['english']))
    c=make('owner');c.configure('goal',dict(outcome='Simple questions',minutes=15,milestones=['Past events'],skills=[dict(id='past',outcome='Ask about yesterday',pattern_ids=['past_simple_questions'])]),confirmed=True)
    member=provider.create_learner('owner',['memory:english'],'family','Family test')
    app=Starlette(routes=routes(provider,make)+[Route('/enroll',provider.enroll,methods=['GET','POST'])])
    with TestClient(app,base_url=BASE) as client:
        p=client.get(member['enrollment_url']);assert client.post('/enroll',headers={'Origin':BASE},data=dict(csrf=token(p),secret=PERSONAL,confirmation=PERSONAL)).status_code==200
    store.register_user(member['learner_id'])
    return app,provider,c,make(member['learner_id']),member['learner_id']

def params(user,section='overview',**more):return dict(learner_id=user,section=section,days=0,**more)
def post(client,action,args,user='owner'):
    csrf=client.get('/english/api/bootstrap').json()['csrf']
    return client.post('/english/api/action',headers={'Origin':BASE,'X-CSRF-Token':csrf},json=dict(learner_id=user,action=action,args=dict(idempotency_key='ui-'+action,learner_confirmed=True,**args)))


def test_login_csrf_replay_cookie_headers_assets_and_logout(web):
    app,p,c,k,kid=web
    with TestClient(app,base_url=BASE) as client:
        assert client.get('/english',follow_redirects=False).status_code==303
        assert client.get('/english/api/bootstrap').status_code==401
        page=client.get('/english/login');csrf=token(page)
        assert client.post('/english/login',data=dict(csrf=csrf,secret=OWNER)).status_code==403
        assert client.post('/english/login',headers={'Origin':BASE},data=dict(csrf=csrf,secret=OWNER),follow_redirects=False).status_code==303
        assert client.post('/english/login',headers={'Origin':BASE},data=dict(csrf=csrf,secret=OWNER)).status_code==403
        r=client.get('/english');assert r.status_code==200 and r.headers['cache-control']=='no-store'
        assert "frame-ancestors 'none'" in r.headers['content-security-policy']
        assert COOKIE in client.cookies and 'login_hash' not in client.get('/english/api/bootstrap').text
        for asset in ('app.js','theme.js','styles.css'):assert client.get('/english/assets/'+asset).status_code==200
        assert client.get('/english/assets/auth.sqlite').status_code==404
        assert client.post('/english/api/logout',json={}).status_code==403
        csrf=client.get('/english/api/bootstrap').json()['csrf']
        assert client.post('/english/api/logout',headers={'Origin':BASE,'X-CSRF-Token':csrf},json={}).status_code==200
        assert client.get('/english/api/bootstrap').status_code==401


def test_separate_https_cabinet_origin_keeps_oauth_and_binds_tickets_and_sessions(web):
    app,p,c,k,kid=web
    origin='https://eng.example.test'
    separate=Starlette(routes=routes(p,lambda user:c,origin))
    with TestClient(separate,base_url=origin) as client:
        page=client.get('/english/login');ticket=client.cookies['ec-login']
        assert 'Secure' in page.headers['set-cookie']
        assert client.post('/english/login',headers={'Origin':BASE},data=dict(csrf=token(page),secret=OWNER)).status_code==403
        with TestClient(separate,base_url=BASE) as other:
            other.cookies.set('ec-login',ticket)
            assert other.post('/english/login',headers={'Origin':BASE},data=dict(csrf=token(page),secret=OWNER)).status_code==403
        page=client.get('/english/login')
        r=client.post('/english/login',headers={'Origin':origin},data=dict(csrf=token(page),secret=OWNER),follow_redirects=False)
        assert r.status_code==303 and 'Secure' in r.headers['set-cookie']
        assert client.get('/english/api/view',params=params('owner')).status_code==200
        csrf=client.get('/english/api/bootstrap').json()['csrf']
        assert client.post('/english/api/logout',headers={'Origin':'https://attacker.example','X-CSRF-Token':csrf},json={}).status_code==403
        with TestClient(separate,base_url=BASE) as other:
            other.cookies.set(COOKIE,client.cookies[COOKIE])
            assert other.get('/english/api/bootstrap').status_code==401
        assert client.post('/english/api/logout',headers={'Origin':origin,'X-CSRF-Token':csrf},json={}).status_code==200
    with TestClient(separate,base_url='https://attacker.example') as client:
        assert client.get('/english/login').status_code==403
    assert p.base==BASE and p.resource==BASE+'/mcp'


@pytest.mark.parametrize('origin',['https://eng.example.test/path','https://user:password@eng.example.test','http://eng.example.test'])
def test_invalid_cabinet_origin_rejected_before_serving(web,origin):
    app,p,c,k,kid=web
    with pytest.raises(ValueError):routes(p,lambda user:c,origin)


def test_cookie_expiry_deactivation_and_reactivation_do_not_restore_login(web):
    app,p,c,k,kid=web
    with TestClient(app,base_url=BASE) as client:
        assert login(client,kid,PERSONAL).status_code==303
        cookie=client.cookies[COOKIE];v=p.account(kid)['version']
        p.update_learner('owner',['memory:english'],'disable',kid,v,False,False)
        assert client.get('/english/api/bootstrap').status_code==401
        p.update_learner('owner',['memory:english'],'enable',kid,v+1,True,False)
        assert client.get('/english/api/bootstrap').status_code==401
        assert login(client,kid,PERSONAL).status_code==303
        value=p.get('english-browser',client.cookies[COOKIE]);p.put('english-browser',client.cookies[COOKIE],value,time.time()-1)
        assert client.get('/english/api/bootstrap').status_code==401
        assert login(client,kid,PERSONAL).status_code==303
        p.login_hash='0'*64  # owner's rotation doesn't invalidate an unrelated member credential
        assert client.get('/english/api/bootstrap').status_code==200


@pytest.mark.parametrize('operation',[('view',{'section':'progress','query':'family'}),('detail',{'kind':'lesson','id':'foreign'}),('detail',{'kind':'job','id':'coach-job-foreign'}),('detail',{'kind':'source','id':'coach-source-foreign'}),('detail',{'kind':'discovery','id':'coach-discovery-foreign'})])
def test_foreign_profile_denied_before_any_read(web,operation):
    app,p,c,k,kid=web
    with TestClient(app,base_url=BASE) as client:
        login(client,kid,PERSONAL);op,args=operation
        r=client.get('/english/api/'+op,params={'learner_id':'owner',**args});assert r.status_code==403
        assert 'Did you' not in r.text
        assert post(client,'settings',dict(expected_version=1,settings=c.profile()['value']['settings']),user='owner').status_code==403
        assert client.get('/english/api/bootstrap').json()['default_learner_id']==kid


def test_explicit_admin_grant_ambiguity_and_cross_id_detail(web):
    app,p,c,k,kid=web
    own=c.start('start');p.update_learner('owner',['memory:english'],'grant',kid,p.account(kid)['version'],True,True,True)
    with TestClient(app,base_url=BASE) as client:
        login(client);assert client.get('/english/api/bootstrap').json()['default_learner_id'] is None
        assert client.get('/english/api/view').status_code==403
        assert client.get('/english/api/view',params=params(kid)).json()['configured'] is False
        assert client.get('/english/api/detail',params=dict(learner_id=kid,kind='lesson',id=own['session']['id'])).status_code==403
        assert post(client,'feedback',dict(attempt_id='foreign',text='bad',expected_coach_version=1),kid).status_code==400


@pytest.mark.parametrize('section',SECTIONS)
def test_sections_are_read_only_empty_profile_safe_and_keys_not_exposed(web,section):
    _,_,c,k,_=web;s=c.start('s');c.finalize('end',s['session']['id'],1,1,[observation('a','hint')],True)
    before=deepcopy(c.documents('coach-'));ledger=deepcopy(c.legacy.observations());history=deepcopy(c.history())
    out=AdminRead(c).read(section,days=0);assert out['coverage']['complete_matching_aggregates'] and out['source_versions']['profile']==1
    assert 'accepted' not in str(out)
    assert AdminRead(k).read(section,days=0)['configured'] is False
    assert c.documents('coach-')==before and c.legacy.observations()==ledger and c.history()==history


def test_all_matching_metrics_and_pagination_moscow_boundaries(web,monkeypatch):
    _,_,c,_,_=web
    monkeypatch.setattr('saver.store.utc',lambda:'2026-10-08T20:00:00+00:00')
    s=c.start('s')
    class Fixed(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,9,8,tzinfo=timezone.utc)
    monkeypatch.setattr('saver.store.datetime',Fixed)
    # UTC midnight boundary: 21:00 UTC starts the next Moscow date.
    aa=[observation('before',at='2026-10-08T20:59:00+00:00'),observation('after',at='2026-10-08T21:00:00+00:00')]
    aa += [observation(str(n),outcome='incorrect' if n%2 else 'correct',at='2026-10-09T05:00:00+00:00') for n in range(24)]
    aa += [observation('amb','independent','ambiguous','2026-10-09T05:00:00+00:00'),observation('hint','hint','correct','2026-10-09T05:00:00+00:00'),observation('repeat','immediate_repeat','correct','2026-10-09T05:00:00+00:00')]
    c.save('cp',s['session']['id'],1,aa)
    read=AdminRead(c);one=read.read('progress',days=0,start='2026-10-09',end='2026-10-09',limit=7);two=read.read('progress',days=0,start='2026-10-09',end='2026-10-09',limit=7,offset=7)
    assert one['total']==28 and len(one['items'])==7 and one['metrics']==two['metrics']
    assert one['metrics']['independent']==dict(correct=13,total=25,accuracy=13/25,ambiguous=1)
    assert one['metrics']['hint']['total']==1 and one['metrics']['immediate_repeat']['total']==1
    assert not {a['id'] for a in one['items']} & {a['id'] for a in two['items']}
    assert one['timezone']=='Europe/Moscow' and one['rules_version']
    assert read.read('progress',days=0,start='2026-10-09',end='2026-10-09',query='does not exist')['metrics']['independent']['accuracy'] is None
    d=read.detail('lesson',s['session']['id'],limit=7,offset=21);assert d['value']['records_page']['total']==29 and len(d['value']['attempts'])==7


def test_vocabulary_full_list_over_twelve_and_material_separation(web):
    _,_,c,_,_=web
    # Synthetic projection fixture documents, not evidence of an actual learner.
    for n in range(25):c.memory.put('coach-lexical-fixture-'+str(n),dict(phrase='at home '+str(n),meaning='fixture',state='seen',records=[]),0)
    c.memory.put('coach-material-fixture',dict(phrase='source wording',state='seen'),0)
    r=AdminRead(c);first=r.read('vocabulary',days=0,limit=10);last=r.read('vocabulary',days=0,limit=10,offset=20)
    assert first['total']==25 and last['total']==25 and len(last['items'])==5 and first['counts']=={'seen':25}
    assert not any(d['key'].startswith('coach-material-') for d in first['items'])


def test_explicit_actions_cas_idempotency_and_original_feedback(web):
    app,p,c,k,kid=web;s=c.start('s');saved=c.save('save',s['session']['id'],1,[observation('original')]);original=deepcopy(c.legacy.observations())
    with TestClient(app,base_url=BASE) as client:
        login(client);settings=deepcopy(c.profile()['value']['settings']);settings['instructions']='Use only basic words.'
        body=dict(expected_version=1,settings=settings)
        assert post(client,'settings',body).status_code==200
        assert post(client,'settings',body).json()['version']==2
        csrf=client.get('/english/api/bootstrap').json()['csrf']
        r=client.post('/english/api/action',headers={'Origin':BASE,'X-CSRF-Token':csrf},json=dict(learner_id='owner',action='settings',args=dict(idempotency_key='stale',learner_confirmed=True,expected_version=1,settings=settings)))
        assert r.status_code==409
        assert post(client,'feedback',dict(attempt_id=original[0]['id'],text='Too hard',expected_coach_version=saved['coach_version'])).status_code==200
        assert post(client,'feedback',dict(attempt_id=original[0]['id'],text='Too hard',expected_coach_version=saved['coach_version'])).status_code==200
        assert len(c.required('coach-session-'+s['session']['id'])['value']['feedback'])==1
        assert c.legacy.observations()==original
        for bad in [dict(expected_version=True,settings=settings),dict(expected_version=2,settings=settings,sql='invalid')]:assert post(client,'settings',bad).status_code==400
        assert k.memory.get('coach-profile') is None


def test_explicit_key_reveal_and_retry_enqueue_only(web):
    _,_,c,_,_=web;s=c.start('s');done=c.finalize('end',s['session']['id'],1,1,[observation('a','independent','incorrect')],True)
    read=AdminRead(c);act=AdminAction(c);hid=done['homework']['key'];jid=done['review_job']
    assert 'accepted' not in str(read.detail('homework',hid))
    before=read.detail('homework',hid)['value'];args=dict(idempotency_key='reveal',learner_confirmed=True,homework_id=hid,expected_version=before['version'])
    answers=act.execute('reveal_homework',args);assert answers['answers'] and act.execute('reveal_homework',args)==answers
    assert c.required(hid)['value']['exposed_items']
    class Broken:
        async def review(self,snapshot):raise RuntimeError('synthetic secret provider payload')
    assert asyncio.run(Worker(c,Broken(),max_attempts=1).run_once())['value']['status']=='failed'
    detail=read.detail('job',jid)['value'];assert 'synthetic secret' not in str(detail)
    retry=dict(idempotency_key='retry',learner_confirmed=True,job_id=jid,expected_version=detail['current_session_versions']['original'],expected_coach_version=detail['current_session_versions']['coach'])
    queued=act.execute('retry',retry);assert queued['status']=='queued' and act.execute('retry',retry)==queued
    assert len(c.documents('coach-job-'))==2 and len(c.legacy.observations())==1
    with pytest.raises(ValueError):act.execute('retry',dict(retry,idempotency_key='no-confirm',learner_confirmed=False))


def test_real_host_routes_and_read_mcp_catalog(tmp_path,monkeypatch):
    from saver.server import create_app
    monkeypatch.setenv('SAVER_ENGLISH_COACH','1');monkeypatch.setenv('COACH_PROVIDER','test')
    app=create_app(tmp_path/'data',tmp_path/'export',BASE,hashlib.sha256(OWNER.encode()).hexdigest())
    with TestClient(app,base_url=BASE) as client:
        assert login(client).status_code==303
        assert client.get('/english/api/view',params=params('owner')).json()['configured'] is False
        assert client.get('/english/api/view',params=params('owner','settings')).json()['ui_version']=='0.5.2'
        assert client.get('/health').status_code==200


def test_restore_and_archive_keep_active_lesson_and_original_history(web):
    from english_coach.material import MaterialIntake
    _,_,c,_,_=web;s=c.start('s');active=deepcopy(c.required(s['coach']['key']));settings=deepcopy(c.profile()['value']['settings']);settings['instructions']='Simple forms.'
    act=AdminAction(c);act.execute('settings',dict(idempotency_key='setting',learner_confirmed=True,expected_version=1,settings=settings))
    restored=act.execute('restore',dict(idempotency_key='restore',learner_confirmed=True,expected_version=2,source_version=1,part='settings'))
    assert restored['version']==3 and restored['value']['settings']==active['value']['settings_snapshot']
    assert c.required(s['coach']['key'])==active and c.legacy.observations()==[]
    receipt=asyncio.run(MaterialIntake(c,TestProvider(),2).submit('material','Could we clarify the next step? The team discussed the date and agreed who would own it.'))
    source=AdminRead(c).detail('source',receipt['source_id'])['value']
    result=act.execute('archive',dict(idempotency_key='archive',learner_confirmed=True,source_id=source['key'],expected_version=source['version']))
    assert result['value']['status']=='archived' and c.legacy.observations()==[]


def test_review_proposal_preview_and_explicit_acceptance(web):
    _,_,c,_,_=web;s=c.start('s');c.save('save',s['session']['id'],1,[observation('a')],review=True)
    worker=Worker(c,TestProvider());claimed=worker.claim();raw=asyncio.run(TestProvider().review(claimed['value']['snapshot']))
    raw['changes'].append(dict(kind='load',minutes=20,why='Offer a longer agreed lesson',evidence_ids=[],uncertainty='high',verify='Ask about burden'))
    job=worker.finish(claimed,raw);before=c.profile();active=deepcopy(c.required(s['coach']['key']))
    d=AdminRead(c).detail('job',job['key'])['value']
    assert d['before_plan'] and d['after_plan'] and d['proposals'][0]['status']=='proposed'
    assert c.profile()==before and before['value']['goal']['minutes']==15
    result=AdminAction(c).execute('proposal',dict(idempotency_key='accept',learner_confirmed=True,job_id=job['key'],proposal_id=d['proposals'][0]['id'],expected_version=before['version'],accept=True))
    assert result['value']['goal']['minutes']==20 and c.required(s['coach']['key'])==active
    assert len(c.legacy.observations())==1


def test_json_browser_login_preserves_csrf_and_returns_no_credentials(web):
    app,p,c,k,kid=web
    with TestClient(app,base_url=BASE) as client:
        page=client.get('/english/login');assert 'login.js' in page.text
        r=client.post('/english/login',headers={'Origin':BASE,'Accept':'application/json'},data=dict(csrf=token(page),secret=OWNER))
        assert r.status_code==200 and r.json()=={'next':'/english'}
        assert client.get('/english/api/view',params=params('owner','progress')).status_code==200
        assert client.get('/english/assets/login.js').status_code==200
        assert 'HttpOnly' in r.headers['set-cookie'] and 'SameSite=strict' in r.headers['set-cookie']


def test_methodology_workflow_via_authenticated_ui_and_scoped_views(web):
    app,p,c,k,kid=web
    with TestClient(app,base_url=BASE) as client:
        assert login(client).status_code==303
        for section in ('home','methodology','roadmap','decisions'):
            r=client.get('/english/api/view',params=params('owner',section));assert r.status_code==200
            assert r.json()['management']['profile_version']==c.profile()['version']
        settings=deepcopy(c.profile()['value']['settings']);settings['prompt_style']='guided'
        args=dict(expected_profile_version=c.profile()['version'],expected_draft_version=0,data=dict(policy_id='foundation',grammar_exercises=True,settings=settings,minutes=15))
        assert post(client,'method_draft',args).json()['ok']
        doc=c.required('coach-method-draft')
        r=post(client,'method_publish',dict(expected_profile_version=c.profile()['version'],expected_draft_version=doc['version'],mode='future'))
        assert r.status_code==200 and r.json()['ok']
        assert c.profile()['value']['settings']['prompt_style']=='guided'
        assert k.memory.get('coach-method-draft') is None and k.memory.get('coach-profile') is None
        # A pending draft is isolated even when the caller supplies the same action key.
        assert client.get('/english/api/view',params=params(kid,'methodology')).status_code==403
    with TestClient(app,base_url=BASE) as client:
        assert login(client,kid,PERSONAL).status_code==303
        assert client.get('/english/api/view',params=params('owner','methodology')).status_code==403
        v=client.get('/english/api/view',params=params(kid,'methodology')).json()
        assert v['management']['draft'] is None and v['configured'] is False


def test_language_profile_home_data_is_owned_read_only_and_keeps_original_learning(web,tmp_path):
    from saver.learning_profiles import init_learning_profiles,create_learning_profile,update_learning_profile
    from english_coach.language_learning import LanguageLearning
    app,provider,owner,member,kid=web
    init_learning_profiles(provider)
    a=create_learning_profile(provider,'owner',['memory:english'],'home-es','Viajes','es')
    b=create_learning_profile(provider,'owner',['memory:english'],'home-en','Work','en')
    foreign=create_learning_profile(provider,kid,['memory:english'],'foreign','Private','es')
    archived=create_learning_profile(provider,'owner',['memory:english'],'archive','Archived','es')
    update_learning_profile(provider,'owner',['memory:english'],archived['profile_id'],'archive-it',1,state='archived')
    store=Store(tmp_path/'memory.sqlite',tmp_path/'export')
    for p,goal in [(a,'Spanish for a family trip'),(b,'English for work meetings'),(foreign,'Private family goal')]:
        store.register_user(p['storage_scope_id'],('english',))
        coach=LanguageLearning(MemoryAPI(store,p['storage_scope_id'],'english',['english']),p['language'])
        coach.configure('goal',goal,20,['travel'],confirmed=True)
    with TestClient(app,base_url=BASE) as client:
        assert login(client).status_code==303
        own=client.get('/english/api/learning',params={'view':'profiles'}).json()['profiles']
        assert {p['profile_id'] for p in own}=={a['profile_id'],b['profile_id'],archived['profile_id']}
        for p,goal in [(a,'Spanish for a family trip'),(b,'English for work meetings')]:
            url={'view':'profile','profile_id':p['profile_id']}
            before=client.get('/english/api/learning',params=url).json()
            assert before['context']['goal']['value']['goal']==goal
            assert before['context']['readiness']['status']=='queued'
            assert before['context']['program'] is None and before['context']['active_session'] is None
            assert before['context']['recent_lessons']==[]
            assert client.get('/english/api/learning',params=url).json()==before
        for p in [foreign,archived]:
            assert client.get('/english/api/learning',params={'view':'profile','profile_id':p['profile_id']}).status_code==403
        legacy=client.get('/english/api/view',params=params('owner','home')).json()
        assert legacy['goal']['outcome']=='Simple questions'
        assert client.get('/english/learning').status_code==200
