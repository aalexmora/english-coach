"""Real TCP + official SDK; temporary data only. No production secrets."""
import asyncio,base64,hashlib,os,re,socket,subprocess,sys,time
from urllib.parse import urlparse,parse_qs
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def test_coach_over_tcp_oauth_and_restart(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}'
    secret='temporary-network-test-secret'
    env=dict(os.environ,SAVER_ENGLISH_COACH='1',COACH_PROVIDER='test',SAVER_DATA=str(tmp_path/'data'),SAVER_EXPORT=str(tmp_path/'export'),SAVER_URL=base,SAVER_LOGIN_HASH=hashlib.sha256(secret.encode()).hexdigest())
    def start():
        script = ("import asyncio, uvicorn; from english_coach.methodologist import TestProvider\n"
                  "original = TestProvider.review\n"
                  "async def delayed(self, snapshot):\n"
                  "    await asyncio.sleep(1)\n"
                  "    return await original(self, snapshot)\n"
                  "TestProvider.review = delayed\n"
                  f"uvicorn.run('saver.server:create_app', factory=True, host='127.0.0.1', port={port}, access_log=False)")
        proc=subprocess.Popen([sys.executable,'-c',script],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                if httpx.get(base+'/health').status_code==200: return proc
            except httpx.ConnectError: pass
            if proc.poll() is not None: raise AssertionError('Server exited')
            time.sleep(.05)
        proc.terminate(); proc.wait(); raise AssertionError('Server did not start')
    def oauth(scope):
        with httpx.Client(base_url=base) as c:
            reg=c.post('/register',json=dict(redirect_uris=['https://chatgpt.com/connector/oauth/test'],token_endpoint_auth_method='client_secret_post',grant_types=['authorization_code','refresh_token'],response_types=['code'],scope=scope))
            assert reg.status_code==201,reg.text
            info=reg.json(); verifier='x'*64
            challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            auth=c.get('/authorize',params=dict(client_id=info['client_id'],redirect_uri=info['redirect_uris'][0],response_type='code',scope=scope,code_challenge=challenge,code_challenge_method='S256',resource=base+'/mcp',state='state'))
            page=c.get(auth.headers['location'])
            csrf=re.search('name="csrf" value="([^"]+)"',page.text)[1]
            login=c.post('/login',headers={'Origin':base},data=dict(csrf=csrf,secret=secret))
            code=parse_qs(urlparse(login.headers['location']).query)['code'][0]
            token=c.post('/token',data=dict(grant_type='authorization_code',client_id=info['client_id'],client_secret=info['client_secret'],code=code,code_verifier=verifier,redirect_uri=info['redirect_uris'][0],resource=base+'/mcp'))
            assert token.status_code==200,token.text
            return token.json()['access_token']
    async def call(token,phase,entry_id=None):
        async with httpx.AsyncClient(headers={'Authorization':'Bearer '+token}) as http:
            async with streamable_http_client(base+'/mcp',http_client=http) as (read,write,_):
                async with ClientSession(read,write) as client:
                    await client.initialize()
                    if phase.startswith('coach'):
                        names={item.name for item in (await client.list_tools()).tools}
                        assert {'submit_english_material','archive_english_material',
                                'start_english_practice','get_english_context','check_english_teaching_turn',
                                'request_english_review','finalize_english_lesson','get_english_homework','submit_english_homework','issue_english_homework',
                                'reveal_english_homework_answers','get_english_vocabulary','teach_english_phrase','record_english_phrase_evidence'} <= names
                        async def tool(name, args):
                            if name=='get_english_context' and not args:
                                compact=await client.call_tool(name,{})
                                assert compact.structuredContent['configured']
                                assert 'lesson_runtime' in compact.structuredContent or compact.structuredContent.get('full_context_required')
                                args={'detail':'full'}
                            result=await client.call_tool(name,args)
                            assert not result.isError,result
                            return result.structuredContent
                        if phase=='coach-speaking-read':
                            from datetime import datetime,timezone
                            ctx=await tool('get_english_context',{})
                            assert ctx['methodology']['coach_version']=='0.10.2'
                            assert ctx['methodology']['profile_version']==ctx['profile']['version']
                            assert ctx['work_material'][0]['phrase']=='Could we clarify the delivery date before we commit?'
                            practice=next(p for p in ctx['speaking']['open_practices'] if p['key']==entry_id['practice'])
                            assert practice['value']['stage']=='reproduce'
                            assert practice['evidence']
                            sid=entry_id['sid']
                            session=await tool('get_session',dict(session_id=sid))
                            response=dict(idempotency_key='full-sentence',pattern_id='past_simple_questions',occurred_at=datetime.now(timezone.utc).isoformat(),
                                          outcome='correct',assistance='immediate_repeat',context='client delivery',mode='free',observation='Observed full learner sentence')
                            args=dict(practice_id=practice['key'],expected_version=practice['version'],session_id=sid,
                                      expected_session_version=session['session']['version'],idempotency_key='reproduction',action='respond',attempt=response)
                            practice=await tool('update_english_practice',args)
                            assert practice==await tool('update_english_practice',args)
                            session=await tool('get_session',dict(session_id=sid))
                            await tool('update_english_session',dict(session_id=sid,expected_version=session['coach']['version'],idempotency_key='speaking-end',action='finish',explicit_end=True))
                            # Explicitly allow the transfer lesson on the prior plan while the final review is queued.
                            started=await tool('start_coach_session',dict(idempotency_key='transfer-lesson',accept_outdated=True))
                            assert started['coach']['value']['retrieval_opening'][0]['pattern_id']=='past_simple_questions'
                            sid=started['session']['id']
                            await tool('update_english_session',dict(session_id=sid,expected_version=started['coach']['version'],idempotency_key='transfer-begin',action='begin_item',item_id='step-clarify'))
                            practice=await tool('update_english_practice',dict(practice_id=practice['key'],expected_version=practice['version'],session_id=sid,
                                               expected_session_version=1,idempotency_key='transfer-context',action='transfer',task='Explain the delay to your manager'))
                            response.update(idempotency_key='transfer-observation',assistance='independent',context='manager delivery',occurred_at=datetime.now(timezone.utc).isoformat())
                            practice=await tool('update_english_practice',dict(practice_id=practice['key'],expected_version=practice['version'],session_id=sid,
                                               expected_session_version=1,idempotency_key='transfer-record',action='respond',attempt=response))
                            assert practice['value']['stage']=='completed'
                            ctx=await tool('get_english_context',{})
                            assert ctx['skills']['clarify']['independent_correct']==1
                            assert ctx['profile']['value']['settings']['preferred_mechanic']=='task_repetition'
                            return
                        if phase=='coach':
                            goal=dict(outcome='Negotiate a delivery plan',minutes=15,milestones=['Clarify','Propose'],
                                      skills=[dict(id='clarify',outcome='Ask about constraints',pattern_ids=['past_simple_questions'])])
                            configured=await tool('configure_english',dict(idempotency_key='configure',goal=goal,learner_confirmed=True))
                            assert configured['version']==1
                            meeting=('Could we clarify the delivery date before we commit? '
                                     'The team then discussed a different handoff with several possible owners.')
                            material_args=dict(idempotency_key='meeting-1',text=meeting)
                            material=await tool('submit_english_material',material_args)
                            assert material==await tool('submit_english_material',material_args)
                            assert material['status'] in ('queued','running','applied')
                            assert material['job_id'].startswith('material-job-')
                            for _ in range(100):
                                status=await tool('get_learning_material_job',dict(job_id=material['job_id']))
                                if status['status'] in ('applied','failed','expired'):break
                                await asyncio.sleep(.1)
                            assert status['status']=='applied',status
                            assert status['result']['saved_count']==1
                            ctx=await tool('get_english_context',{})
                            assert ctx['work_material'][0]['phrase']=='Could we clarify the delivery date before we commit?'
                            assert ctx['lesson_brief'] and ctx['work_patterns']
                            assert ctx['skills']['clarify']['independent_total']==0
                            started=await tool('start_session',dict(idempotency_key='coach-start'))
                            assert started['say_first']==ctx['say_first']
                            sid=started['session']['id']
                            gate=await tool('check_english_teaching_turn',dict(session_id=sid,expected_version=started['coach']['version'],turn=dict(praises_correctness=True)))
                            assert not gate['allowed'] and 'correctness_praise_not_supported' in gate['violations']
                            assert started['coach']['value']['items'][0]['mechanic']=='roleplay'
                            from datetime import datetime,timezone
                            attempt=dict(idempotency_key='attempt',pattern_id='past_simple_questions',occurred_at=datetime.now(timezone.utc).isoformat(),
                                         outcome='correct',assistance='hint',context='delivery',mode='free')
                            cp=await tool('save_checkpoint',dict(session_id=sid,expected_version=1,idempotency_key='checkpoint',attempts=[attempt]))
                            assert cp['result']['review_job'] is None
                            saveargs=dict(session_id=sid,expected_version=2,idempotency_key='explicit-save',attempts=[],
                                          feedback=[dict(id='f',kind='change_exercise',text='Please use contrast',mechanic='contrast')])
                            saved=await tool('save_english_progress',saveargs)
                            assert saved==await tool('save_english_progress',saveargs)
                            assert saved['session_status']=='active'
                            wrong=await client.call_tool('finish_session',dict(session_id=sid,expected_version=3,idempotency_key='premature'))
                            assert wrong.isError
                            denied=await client.call_tool('commit_memory',dict(project_id='english',idempotency_key='bypass',
                                        writes=[dict(key='coach-profile',expected_version=1,value={})]))
                            assert denied.isError
                            return dict(sid=sid,job_id=saved['review_job'])
                        for _ in range(60):
                            job=await tool('get_english_review',dict(job_id=entry_id['job_id']))
                            if job['value']['status'] in ('applied','failed','stale'): break
                            await asyncio.sleep(.1)
                        assert job['value']['status']=='applied',job
                        ctx=await tool('get_english_context',{})
                        assert ctx['profile']['value']['settings']['preferred_mechanic']=='contrast'
                        assert ctx['skills']['clarify']['independent_total']==0
                        assert ctx['unfinished']
                        session=await tool('get_session',dict(session_id=entry_id['sid']))
                        assert len(session['attempts'])==1
                        assert session['session']['status']=='active'
                        assert session['session']['plan_authority']=='english-coach'
                        finished=await tool('update_english_session',dict(session_id=entry_id['sid'],expected_version=session['coach']['version'],
                                           idempotency_key='explicit-end',action='finish',explicit_end=True))
                        new=await tool('start_coach_session',dict(idempotency_key='new-chat'))
                        assert new['coach']['value']['items'][0]['status']=='carried'
                        assert new['coach']['value']['items'][0]['mechanic']=='contrast'
                        assert new['coach']['value']['settings_snapshot']['preferred_mechanic']=='contrast'
                        sid=new['session']['id']
                        switched=await tool('switch_english_mechanic',dict(idempotency_key='try-task-repetition',session_id=sid,expected_version=new['coach']['version'],item_id='step-clarify',mechanic='task_repetition',learner_confirmed=True))
                        session=await tool('get_session',dict(session_id=sid))
                        begun=await tool('update_english_session',dict(session_id=sid,expected_version=session['coach']['version'],idempotency_key='speaking-begin',action='begin_item',item_id='step-clarify'))
                        practice=await tool('start_english_practice',dict(session_id=sid,expected_version=begun['version'],idempotency_key='speaking-start',pattern_id='past_simple_questions',task='Ask the client about the delayed release'))
                        from datetime import datetime,timezone
                        for n,(outcome,help_type) in enumerate([('incorrect','independent'),('correct','hint')]):
                            response=dict(idempotency_key='speaking-attempt-'+str(n),pattern_id='past_simple_questions',occurred_at=datetime.now(timezone.utc).isoformat(),
                                          outcome=outcome,assistance=help_type,context='client delivery',mode='free',error_type='question_formation')
                            practice=await tool('update_english_practice',dict(practice_id=practice['key'],expected_version=practice['version'],session_id=sid,
                                               expected_session_version=n+1,idempotency_key='speaking-respond-'+str(n),action='respond',attempt=response))
                        assert practice['value']['stage']=='reproduce'
                        return dict(sid=sid,practice=practice['key'])
                    if phase=='write':
                        tools=await client.list_tools()
                        assert len(tools.tools)>=13
                        args=dict(project_id='english',idempotency_key='network-test',entry=dict(type='note',title='Network smoke',content='Synthetic data',source='test'))
                        a=await client.call_tool('create_entry',args)
                        assert not a.isError,a
                        b=await client.call_tool('create_entry',args)
                        assert a.structuredContent==b.structuredContent
                        eid=a.structuredContent['result']['id']
                        wrong=await client.call_tool('get_entry',dict(project_id='b2b',entry_id=eid))
                        assert wrong.isError
                        denied=await client.call_tool('create_entry',dict(args,project_id='b2b'))
                        assert denied.isError
                        denied_kids=await client.call_tool('get_kids_context',{})
                        assert denied_kids.isError
                        return eid
                    if phase=='kids':
                        async def tool(name, args):
                            r=await client.call_tool(name,args)
                            assert not r.isError,r
                            return r.structuredContent
                        profile=await tool('save_kids_profile',dict(idempotency_key='child',profile=dict(age_min=8,age_max=10)))
                        plan=dict(topic='Check a claim',goal='Find a counterexample',duration_minutes=10,
                                  outline=['Story','Question','Reflection'],opening_story='All birds fly?',questions=['What about penguins?'])
                        p=await tool('save_kids_plan',dict(idempotency_key='plan',plan=plan,parent_confirmed=True))
                        p=p['result']
                        s=await tool('start_kids_session',dict(idempotency_key='start',plan_id=p['id'],expected_plan_version=p['version']))
                        s=s['result']
                        s=await tool('update_kids_session',dict(session_id=s['id'],expected_version=s['version'],idempotency_key='pause',
                                     update=dict(action='pause',resume_note='Await answer',observations=[dict(idempotency_key='answer',
                                     kind='question',text='Do penguins fly?',evidence='independent')])))
                        forbidden=await client.call_tool('get_english_context',{})
                        assert forbidden.isError
                        forbidden=await client.call_tool('submit_english_material',
                                                         dict(idempotency_key='kids-denied',text='Could we clarify the delivery date?'))
                        assert forbidden.isError
                        wrong=await client.call_tool('get_project_state',dict(project_id='english'))
                        assert wrong.isError
                        return s['result']['id']
                    if phase=='kids-read':
                        r=await client.call_tool('get_kids_context',dict(session_id=entry_id))
                        assert not r.isError,r
                        assert r.structuredContent['session']['status']=='paused'
                        assert len(r.structuredContent['session']['observations'])==1
                        return
                    result=await client.call_tool('get_entry',dict(project_id='english',entry_id=entry_id))
                    assert not result.isError and result.structuredContent['id']==entry_id
    proc=start()
    try:
        assert httpx.post(base+'/mcp',headers={'Authorization':'Bearer invalid'}).status_code==401
        token=oauth('memory:english')
        eid=asyncio.run(call(token,'write'))
        kids_token=oauth('memory:kids')
        kids_id=asyncio.run(call(kids_token,'kids'))
        coach_info=asyncio.run(call(token,'coach'))
        # No HTTP requests while the delayed provider finishes. Reading through
        # the public host API cannot accidentally start another request worker.
        from saver.store import Store
        from saver.memory import MemoryAPI
        store=Store(tmp_path/'data'/'memory.sqlite', tmp_path/'export')
        memory=MemoryAPI(store, store.user, 'english', ['english'])
        for _ in range(80):
            job=memory.get(coach_info['job_id'])
            if job['value']['status']=='applied':
                break
            time.sleep(.1)
        assert job['value']['status']=='applied', job['value']['status']
        assert job['value']['attempts']==1
    finally: proc.terminate(); proc.wait(timeout=10)
    proc=start()
    try:
        asyncio.run(call(token,'read',eid))
        asyncio.run(call(kids_token,'kids-read',kids_id))
        speaking_info=asyncio.run(call(token,'coach-read',coach_info))
    finally: proc.terminate(); proc.wait(timeout=10)
    proc=start()
    try:
        asyncio.run(call(token,'coach-speaking-read',speaking_info))
    finally: proc.terminate(); proc.wait(timeout=10)
