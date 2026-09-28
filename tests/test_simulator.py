import json

import httpx
import pytest

from simulator.fleet import prepare_fleet, send_event


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
