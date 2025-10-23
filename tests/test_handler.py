import os
import json
import sys
import pytest

# Ensure Eliza-GPT src is on sys.path for imports
ROOT = os.path.dirname(os.path.dirname(__file__))
ELIZA_SRC = os.path.join(ROOT, 'Eliza-GPT', 'src')
if os.path.isdir(ELIZA_SRC) and ELIZA_SRC not in sys.path:
    sys.path.insert(0, ELIZA_SRC)

import importlib
eliza_app = importlib.import_module('lambda.app')


def make_event(body: dict, headers: dict = None, source_ip: str = '1.2.3.4'):
    return {
        'body': json.dumps(body),
        'headers': headers or {},
        'requestContext': {'http': {'sourceIp': source_ip}},
        'rawPath': '/v1/chat/completions'
    }


def test_happy_path(monkeypatch):
    # Allow all
    monkeypatch.setenv('ALLOWED_CALLER_CIDR', '0.0.0.0/0')
    # Ensure Eliza initializes quickly
    event = make_event({'messages': [{'role': 'user', 'content': 'Hello'}]})

    resp = eliza_app.lambda_handler(event, type('C', (), {'aws_request_id': 't'}))
    assert resp['statusCode'] == 200
    body = json.loads(resp['body'])
    assert 'choices' in body


def test_missing_messages(monkeypatch):
    monkeypatch.setenv('ALLOWED_CALLER_CIDR', '0.0.0.0/0')
    event = make_event({'not_messages': []})
    resp = eliza_app.lambda_handler(event, type('C', (), {'aws_request_id': 't2'}))
    assert resp['statusCode'] == 400
    body = json.loads(resp['body'])
    assert 'error' in body


def test_disallowed_ip(monkeypatch):
    monkeypatch.setenv('ALLOWED_CALLER_CIDR', '10.0.0.0/8')
    event = make_event({'messages': [{'role': 'user', 'content': 'hi'}]}, source_ip='1.2.3.4')
    resp = eliza_app.lambda_handler(event, type('C', (), {'aws_request_id': 't3'}))
    assert resp['statusCode'] == 403


def test_api_key_required(monkeypatch):
    monkeypatch.setenv('ALLOWED_CALLER_CIDR', '0.0.0.0/0')
    monkeypatch.setenv('REQUIRE_API_KEY', 'true')
    monkeypatch.setenv('API_KEY', 'secret')

    event = make_event({'messages': [{'role': 'user', 'content': 'hi'}]}, headers={})
    resp = eliza_app.lambda_handler(event, type('C', (), {'aws_request_id': 't4'}))
    assert resp['statusCode'] == 401

    event2 = make_event({'messages': [{'role': 'user', 'content': 'hi'}]}, headers={'Authorization': 'Bearer secret'})
    resp2 = eliza_app.lambda_handler(event2, type('C', (), {'aws_request_id': 't5'}))
    assert resp2['statusCode'] == 200
