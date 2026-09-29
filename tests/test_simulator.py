import json

import httpx
import pytest

from simulator.fleet import authenticate, prepare_fleet, send_event


def test_simulator_authentication_installs_csrf_header():
    def handler(request):
        assert json.loads(request.content) == {
            'username': 'atlas-admin',
            'password': 'demo-password',
        }
        return httpx.Response(200, json={'csrf_token': 'csrf-value'})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test') as client:
        authenticate(client, 'atlas-admin', 'demo-password', 'bridge-key')
        assert client.headers['X-CSRF-Token'] == 'csrf-value'
        assert client.headers['X-ATLAS-Bridge-Key'] == 'bridge-key'


def test_simulator_requires_operator_password():
    with httpx.Client(base_url='http://test') as client:
        with pytest.raises(RuntimeError, match='ATLAS_OPERATOR_PASSWORD'):
            authenticate(client, 'atlas-admin', None, 'bridge-key')


def test_simulator_requires_bridge_key():
    def handler(_request):
        return httpx.Response(200, json={'csrf_token': 'csrf-value'})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test') as client:
        with pytest.raises(RuntimeError, match='ATLAS_TELEMETRY_API_KEY'):
            authenticate(client, 'atlas-admin', 'demo-password', None)


def test_retry_uses_identical_event():
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(503 if len(seen) == 1 else 200, json={'duplicate': False})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test') as client:
        assert send_event(client, {'event_id': 'stable'}, sleep=lambda _: None) == {'duplicate': False}
    assert seen == [{'event_id': 'stable'}, {'event_id': 'stable'}]


def test_invalid_payload_is_not_retried():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(422)
    with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test') as client:
        with pytest.raises(httpx.HTTPStatusError):
            send_event(client, {}, sleep=lambda _: None)
    assert len(calls) == 1


def test_busy_fleet_does_not_create_partial_missions():
    calls = []
    def handler(request):
        calls.append(request.method)
        return httpx.Response(200, json=[{'id': 'running'}] if request.url.path == '/api/missions' else {'status': 'ok'})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url='http://test') as client:
        with pytest.raises(RuntimeError, match='Cancel'):
            prepare_fleet(client)
    assert calls == ['GET', 'GET']
