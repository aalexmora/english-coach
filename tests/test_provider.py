import asyncio
import json
import httpx
import pytest
from english_coach.methodologist import HTTPProvider, from_env
from english_coach.models import Review


@pytest.mark.parametrize('response_format', ['json_schema', 'json_object'])
def test_http_adapter_contract_without_live_credentials(monkeypatch, response_format):
    original=httpx.AsyncClient
    def respond(request):
        data=json.loads(request.content)
        assert request.headers['Authorization']=='Bearer synthetic-test-key'
        assert data['max_tokens']==800
        assert data['response_format']['type']==response_format
        if response_format == 'json_schema':
            assert data['response_format']['json_schema']['name']=='english_review'
            assert data['response_format']['json_schema']['strict'] is True
        assert data['messages'][0]['role']=='system'
        assert 'Required JSON schema' in data['messages'][0]['content']
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'findings':[],'changes':[]})}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    adapter=HTTPProvider('https://model.example.test/chat/completions','test',
                         'synthetic-test-key',1,800,response_format)
    assert asyncio.run(adapter.review({'only':'synthetic data'}))==dict(findings=[],changes=[])


def test_material_uses_external_model_with_strict_schema(monkeypatch):
    original=httpx.AsyncClient
    def respond(request):
        data=json.loads(request.content)
        assert data['response_format']['json_schema']['name']=='english_material'
        assert data['response_format']['json_schema']['strict'] is True
        assert 'untrusted' in data['messages'][0]['content']
        assert 'Could we clarify the plan?' in data['messages'][1]['content']
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"materials":[]}'}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    adapter=HTTPProvider('https://model.example.test/chat/completions','test',
                         'synthetic-test-key',1,800)
    assert asyncio.run(adapter.analyze_material({'text':'Could we clarify the plan?'}))=={'materials':[]}


def test_provider_explicit_configuration_and_limits(monkeypatch):
    monkeypatch.setenv('COACH_PROVIDER','disabled')
    _,timeout=from_env()
    assert timeout>0
    monkeypatch.setenv('COACH_PROVIDER','http')
    monkeypatch.delenv('COACH_MODEL_URL',raising=False)
    with pytest.raises(KeyError): from_env()
    monkeypatch.setenv('COACH_MODEL_TIMEOUT','999999')
    with pytest.raises(ValueError): from_env()
    with pytest.raises(ValueError): HTTPProvider('http://model.test','model','test',1,100)
    with pytest.raises(ValueError):
        HTTPProvider('https://model.test','model','test',1,100,'invalid')


def test_provider_rejects_truncated_or_empty_result(monkeypatch):
    original=httpx.AsyncClient
    responses=[
        {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]},
        {'choices':[{'finish_reason':'stop','message':{'content':''}}]},
    ]
    def respond(request):
        return httpx.Response(200,json=responses.pop(0))
    monkeypatch.setattr(httpx,'AsyncClient',
                        lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    adapter=HTTPProvider('https://model.example.test/chat/completions','test',
                         'synthetic-test-key',1,800,'json_object')
    with pytest.raises(ValueError,match='Incomplete'):
        asyncio.run(adapter.review({}))
    with pytest.raises(ValueError,match='Empty'):
        asyncio.run(adapter.review({}))


def test_review_schema_and_one_repair_for_invalid_plan(monkeypatch):
    schema=Review.model_json_schema()
    assert schema['properties']['changes']['items']['discriminator']['propertyName']=='kind'
    original=httpx.AsyncClient
    requests=[]
    plan=[dict(id='step-clarify',skill_id='clarify',task='Ask who owns the update',
               mechanic='roleplay',mechanic_version=1,status='pending',minutes=10)]
    common=dict(why='Try a related situation',evidence_ids=[],uncertainty='high',
                verify='Ask independently next time')
    bad=dict(findings=[],changes=[dict(kind='plan',plan=plan,minutes=20,**common)])
    good=dict(findings=[],changes=[dict(kind='plan',plan=plan,**common)])
    def respond(request):
        requests.append(json.loads(request.content))
        result=bad if len(requests)==1 else good
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(result)}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    adapter=HTTPProvider('https://model.example.test/chat/completions','test',
                         'synthetic-test-key',1,800)
    snapshot=dict(profile=dict(value=dict(plan=plan,goal=dict(minutes=20))))
    assert asyncio.run(adapter.review(snapshot))==good
    assert len(requests)==2
    assert 'previous JSON failed' in requests[1]['messages'][0]['content']


def test_provider_repairs_semantic_evidence_violation(monkeypatch):
    from test_coach import env, save_review, goal
    from english_coach.methodologist import ReviewRuleError
    plan=[dict(id='step-clarify',skill_id='clarify',task='Ask the owner',mechanic='roleplay',mechanic_version=1,status='pending',minutes=10)]
    snapshot=dict(profile=dict(value=dict(plan=plan,goal=goal())),observations=[],session=dict(value=dict(feedback=[])))
    bad=dict(findings=[dict(skill_id='clarify',hypothesis='No recent evidence',evidence_ids=['old-summary-id'],uncertainty='high',verify='Cold diagnostic')],changes=[])
    good=dict(findings=[dict(skill_id='clarify',hypothesis='No recent evidence',evidence_ids=[],uncertainty='high',verify='Cold diagnostic')],changes=[])
    requests=[]
    original=httpx.AsyncClient
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(bad if len(requests)==1 else good)}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    provider=HTTPProvider('https://model.example.test/chat/completions','test','synthetic',1,800)
    assert asyncio.run(provider.review(snapshot))==good
    assert len(requests)==2
    assert 'Finding must cite observations' in requests[1]['messages'][0]['content']
    assert 'old-summary-id' not in requests[1]['messages'][0]['content']


@pytest.mark.parametrize('content,category',[('{broken','invalid_json'),('','empty')])
def test_provider_failure_category_is_safe(monkeypatch,content,category):
    from english_coach.methodologist import ProviderResultError
    original=httpx.AsyncClient
    def respond(request):
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(respond),**kw))
    provider=HTTPProvider('https://model.example.test/chat/completions','test','secret',1,800)
    with pytest.raises(ProviderResultError) as caught:asyncio.run(provider.review({}))
    assert caught.value.category==category
    assert 'secret' not in str(caught.value) and '{broken' not in str(caught.value)
