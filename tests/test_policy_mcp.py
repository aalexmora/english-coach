"""Official MCP SDK against two authenticated ASGI profiles; temporary data only."""
import asyncio,hashlib,re
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.testclient import TestClient
from saver.server import create_app


def test_policy_tools_two_personal_profiles(tmp_path,monkeypatch):
    monkeypatch.setenv('SAVER_ENGLISH_COACH','1');monkeypatch.setenv('COACH_PROVIDER','test')
    base='http://localhost:8000';login_hash=hashlib.sha256(b'synthetic-owner-password').hexdigest()
    def app():return create_app(tmp_path/'data',tmp_path/'export',base,login_hash)
    def host(wrapped):
        while hasattr(wrapped,'app'):wrapped=wrapped.app
        return wrapped
    first=app();p=host(first).state.provider
    member=p.create_learner('owner',['memory:english'],'member','Synthetic Katya')
    with TestClient(first,base_url=base) as browser:
        page=browser.get(member['enrollment_url'])
        csrf=re.search(r'name="csrf" value="([^"]+)"',page.text)[1]
        response=browser.post('/enroll',headers={'Origin':base},data=dict(csrf=csrf,secret='synthetic-member-password',confirmation='synthetic-member-password'))
        assert response.status_code==200
    sid=member['learner_id'];tokens=[p.issue('test',['memory:english'],base+'/mcp',subject).access_token for subject in ('owner',sid)]
    second=app();service=host(second)
    async def run():
        async with service.router.lifespan_context(service):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second),headers={'Authorization':'Bearer '+tokens[0]}) as ah, \
                       httpx.AsyncClient(transport=httpx.ASGITransport(app=second),headers={'Authorization':'Bearer '+tokens[1]}) as bh:
                async with streamable_http_client(base+'/mcp',http_client=ah) as (ar,aw,_),streamable_http_client(base+'/mcp',http_client=bh) as (br,bw,_):
                    async with ClientSession(ar,aw) as a,ClientSession(br,bw) as b:
                        await a.initialize();await b.initialize()
                        async def tool(client,name,args=None,denied=False):
                            r=await client.call_tool(name,args or {})
                            assert bool(r.isError)==denied,(name,r)
                            return r.structuredContent
                        catalog=await tool(b,'list_english_teaching_policies')
                        assert {p['id'] for p in catalog['items']}=={'foundation','conversation'}
                        await tool(b,'list_english_teaching_policies',dict(learner_id='owner'),True)
                        pattern=(await tool(b,'add_pattern',dict(idempotency_key='p',text='Discuss an experience')))['result']['id']
                        def goal(pid):return dict(outcome='Discuss an experience',minutes=15,milestones=['Develop an idea'],skills=[dict(id='events',outcome='Explain an experience',pattern_ids=[pid])])
                        await tool(a,'configure_english',dict(idempotency_key='configure',goal=goal('past_simple_questions'),learner_confirmed=True))
                        await tool(b,'configure_english',dict(idempotency_key='configure',goal=goal(pattern),learner_confirmed=True,policy_id='conversation'))
                        before=await tool(a,'get_english_context')
                        for section in ('overview','program','progress','vocabulary','lessons','methodologist','materials','settings'):
                            view=await tool(b,'get_english_admin_view',dict(section=section,days=0))
                            assert view['learner_id']==sid and view['source_versions']['profile']==1
                            assert 'accepted' not in str(view)
                        await tool(b,'get_english_admin_view',dict(section='progress',learner_id='owner'),True)
                        started=await tool(b,'start_coach_session',dict(idempotency_key='start'))
                        assert started['coach']['value']['teaching_policy']['id']=='conversation'
                        lesson=started['session']['id']
                        begun=await tool(b,'update_english_session',dict(session_id=lesson,expected_version=1,idempotency_key='begin',action='begin_item',item_id='step-events'))
                        await tool(b,'set_english_grammar_permission',dict(idempotency_key='no-consent',expected_version=begun['version'],enabled=True,scope='item',session_id=lesson,item_id='step-events'),True)
                        await tool(b,'set_english_settings',dict(idempotency_key='preparation',expected_version=1,settings=dict(homework_minutes=6),learner_confirmed=True))
                        context=await tool(b,'get_english_context')
                        assert context['lesson_runtime']['settings']['homework_minutes']==0
                        assert context['lesson_runtime']['future_settings']['homework_minutes']==6
                        assert context['lesson_runtime']['vocabulary_policy']['level']=='natural'
                        await tool(b,'set_english_grammar_permission',dict(idempotency_key='future',expected_version=2,enabled=True,learner_confirmed=True))
                        guard=dict(session_id=lesson,expected_version=begun['version'],turn=dict(activity='grammar_drill'))
                        assert not (await tool(b,'check_english_teaching_turn',guard))['allowed']
                        allowed=await tool(b,'set_english_grammar_permission',dict(idempotency_key='one-block',expected_version=begun['version'],enabled=True,learner_confirmed=True,scope='item',session_id=lesson,item_id='step-events'))
                        guard['expected_version']=allowed['version']
                        assert (await tool(b,'check_english_teaching_turn',guard))['allowed']
                        await tool(b,'set_english_grammar_permission',dict(idempotency_key='intrude',expected_version=1,enabled=True,learner_confirmed=True,learner_id='owner'),True)
                        await tool(a,'get_english_context',dict(learner_id=sid),True)
                        assert await tool(a,'get_english_context')==before
                        revoked=await tool(b,'set_english_grammar_permission',dict(idempotency_key='off',expected_version=allowed['version'],enabled=False,learner_confirmed=True,scope='item',session_id=lesson,item_id='step-events'))
                        guard['expected_version']=revoked['version']
                        assert not (await tool(b,'check_english_teaching_turn',guard))['allowed']
    asyncio.run(run())


def test_conversation_journey_through_personal_mcp(tmp_path,monkeypatch):
    from datetime import datetime,timezone
    monkeypatch.setenv('SAVER_ENGLISH_COACH','1');monkeypatch.setenv('COACH_PROVIDER','test')
    base='http://localhost:8000'
    def make():return create_app(tmp_path/'data',tmp_path/'export',base,hashlib.sha256(b'synthetic-owner-code').hexdigest())
    def unwrap(app):
        while hasattr(app,'app'):app=app.app
        return app
    first=make();provider=unwrap(first).state.provider
    member=provider.create_learner('owner',['memory:english'],'member','Synthetic learner')
    with TestClient(first,base_url=base) as browser:
        page=browser.get(member['enrollment_url']);csrf=re.search(r'name="csrf" value="([^"]+)"',page.text)[1]
        assert browser.post('/enroll',headers={'Origin':base},data=dict(csrf=csrf,secret='synthetic-private-code',confirmation='synthetic-private-code')).status_code==200
    token=provider.issue('test',['memory:english'],base+'/mcp',member['learner_id']).access_token
    second=make();service=unwrap(second)
    async def journey():
        async with service.router.lifespan_context(service):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=second),headers={'Authorization':'Bearer '+token}) as http:
                async with streamable_http_client(base+'/mcp',http_client=http) as (read,write,_):
                    async with ClientSession(read,write) as client:
                        await client.initialize()
                        async def call(name,args=None,error=False):
                            r=await client.call_tool(name,args or {})
                            assert bool(r.isError)==error,str(r.content)
                            return r.structuredContent
                        initial=await call('get_english_conversation');assert not initial['configured']
                        p=await call('onboard_english_conversation',dict(idempotency_key='setup',learner_confirmed=True,
                            data=dict(outcome='Speak freely',minutes=15,interests=['films'],situations=['friends'],comfortable_topic_ids=['culture','travel'],reported_level='B2')))
                        assert p['value']['conversation']['proficiency']['assessed'] is False
                        s=await call('start_coach_session',dict(idempotency_key='start'));sid=s['session']['id'];item=s['coach']['value']['items'][0]['id']
                        sd=await call('update_english_session',dict(idempotency_key='begin',session_id=sid,expected_version=s['coach']['version'],action='begin_item',item_id=item))
                        occurred=datetime.now(timezone.utc).isoformat();corrected=datetime.now(timezone.utc).isoformat()
                        data=dict(idempotency_key='block',session_id=sid,expected_version=1,expected_coach_version=sd['version'],save_requested=True,
                            attempts=[dict(idempotency_key='a',pattern_id=p['value']['goal']['skills'][0]['pattern_ids'][0],occurred_at=occurred,outcome='incorrect',assistance='independent',context='a film',mode='free',observation='I have watched it last year.')],
                            annotations=[dict(attempt_key='a',demonstrated=['develops_idea'],correction=dict(kind='actual_error',focus_id='past_time',corrected_text='I watched it last year.',reason='A completed event in the past.',meaning_preserved=True,occurred_at=corrected))])
                        saved=await call('save_english_conversation_block',data)
                        assert (await call('save_english_conversation_block',data))==saved
                        read=await call('get_english_conversation',dict(session_id=sid));assert len(read['records'])==1
                        assert read['records'][0]['attempt']['observation']=='I have watched it last year.'
                        view=await call('get_english_admin_view',dict(section='progress',days=0,limit=1))
                        assert view['learner_id']==member['learner_id'] and view['total']==1
                        assert view['metrics']['independent']['total']==1 and view['metrics']['independent']['correct']==0
                        assert view['conversation_progress']['dimensions']['develops_idea']['independent']==1
                        await call('get_english_conversation',dict(learner_id='owner'),True)
                        free=await call('select_english_conversation_topic',dict(idempotency_key='free',session_id=sid,expected_version=saved['coach_version'],item_id=item,mode='free',topic_id='free',learner_confirmed=True))
                        end=await call('finalize_english_lesson',dict(idempotency_key='end',session_id=sid,expected_version=saved['session_version'],expected_coach_version=free['version'],attempts=[],explicit_end=True))
                        assert end['conversation_summary']['value']['mode']=='text_conversation'
                        read=await call('get_english_conversation',dict(session_id=sid));assert len(read['summary']['value']['independent_examples'])==1
    asyncio.run(journey())
