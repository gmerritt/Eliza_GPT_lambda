import os
import json
import time
import uuid
import logging
import ipaddress
from typing import Tuple, List

# Try to import the Eliza implementation. Tests will add Eliza-GPT/src to sys.path
try:
    from eliza_gpt.eliza_py.eliza import GENERAL_SCRIPT_PATH, SCRIPT_PATH
    from eliza_gpt.eliza_py.utils.startup import setup as eliza_setup
    from eliza_gpt.eliza_py.utils.response import generate_response
except Exception:
    # Leave imports lazy for environments where package path differs.
    GENERAL_SCRIPT_PATH = None
    SCRIPT_PATH = None
    eliza_setup = None
    generate_response = None


logger = logging.getLogger('eliza_lambda')
logger.setLevel(logging.INFO)


def _init_eliza() -> Tuple[dict, list, list]:
    """Initialize Eliza scripts and return (general_script, script, memory_inputs)."""
    global GENERAL_SCRIPT_PATH, SCRIPT_PATH, eliza_setup
    if eliza_setup is None:
        # Try to add a likely path relative to this file to import eliza_gpt
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        possible = [
            os.path.join(repo_root, 'Eliza-GPT', 'src'),
            os.path.join(repo_root, '..', 'Eliza-GPT', 'src'),
        ]
        for p in possible:
            if os.path.isdir(p) and p not in sys.path:
                sys.path.insert(0, p)
        try:
            from eliza_gpt.eliza_py.eliza import GENERAL_SCRIPT_PATH, SCRIPT_PATH
            from eliza_gpt.eliza_py.utils.startup import setup as eliza_setup
            from eliza_gpt.eliza_py.utils.response import generate_response
        except Exception as e:
            logger.exception('Failed to import Eliza modules: %s', e)
            raise

    general_script, script, memory_inputs, _ = eliza_setup(GENERAL_SCRIPT_PATH, SCRIPT_PATH)
    return general_script, script, memory_inputs


_ELIZA_STATE = None


def get_eliza_state():
    global _ELIZA_STATE
    if _ELIZA_STATE is None:
        _ELIZA_STATE = _init_eliza()
    return _ELIZA_STATE


def extract_caller_ip(event) -> str:
    # Prefer X-Forwarded-For header
    headers = event.get('headers') or {}
    xff = headers.get('X-Forwarded-For') or headers.get('x-forwarded-for')
    if xff:
        # first IP in the list
        return xff.split(',')[0].strip()

    # API Gateway v2
    try:
        return event['requestContext']['http']['sourceIp']
    except Exception:
        pass

    # Legacy
    try:
        return event['requestContext']['identity']['sourceIp']
    except Exception:
        return ''


def ip_allowed(caller_ip: str, allowed_cidrs: str) -> bool:
    if not allowed_cidrs:
        return True
    # Accept 0.0.0.0/0 as allow-all
    if allowed_cidrs.strip() == '0.0.0.0/0':
        return True
    try:
        ip = ipaddress.ip_address(caller_ip)
    except Exception:
        return False
    for cidr in [c.strip() for c in allowed_cidrs.split(',') if c.strip()]:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            if ip in net:
                return True
        except Exception:
            logger.warning('Invalid CIDR in ALLOWED_CALLER_CIDR: %s', cidr)
    return False


def make_response(status_code: int, body: dict):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(body)
    }


def lambda_handler(event, context):
    start = time.time()
    req_id = getattr(context, 'aws_request_id', None) or str(uuid.uuid4())
    caller_ip = extract_caller_ip(event)

    allowed_cidrs = os.environ.get('ALLOWED_CALLER_CIDR', '')
    require_api_key = os.environ.get('REQUIRE_API_KEY', 'false').lower() in ('1', 'true', 'yes')
    api_key = os.environ.get('API_KEY')

    # Allow-list check
    if not ip_allowed(caller_ip, allowed_cidrs):
        logger.info(json.dumps({'request_id': req_id, 'caller_ip': caller_ip, 'status': 403, 'message': 'Caller IP not allowed'}))
        return make_response(403, {'error': {'message': 'Caller IP not allowed', 'type': 'forbidden'}})

    # Parse body
    try:
        body = event.get('body')
        if isinstance(body, str):
            payload = json.loads(body) if body else {}
        else:
            payload = body or {}
    except Exception:
        return make_response(400, {'error': {'message': 'Malformed JSON', 'type': 'bad_request'}})

    # API key check
    if require_api_key:
        headers = event.get('headers') or {}
        auth = headers.get('Authorization') or headers.get('authorization')
        if not auth or not api_key or auth != f'Bearer {api_key}':
            return make_response(401, {'error': {'message': 'Invalid or missing API key', 'type': 'unauthorized'}})

    # Extract messages
    messages = payload.get('messages') or []
    # If there are system messages, prepend their content to the first user message
    system_texts = [m.get('content', '') for m in messages if m.get('role') == 'system']
    user_messages = [m.get('content', '') for m in messages if m.get('role') in ('user', 'system') or m.get('role') == 'assistant']

    if not user_messages:
        return make_response(400, {'error': {'message': 'No messages provided', 'type': 'bad_request'}})

    general_script, script, memory_inputs = get_eliza_state()

    # For ELIZA, pass the entire conversation as sequence of messages
    try:
        # The Eliza generate_response expects a single input string; v1 used messages loop
        # We'll call generate_response for each user message and take the last response
        memory_stack = []
        response_text = ''
        for msg in user_messages:
            response_text = generate_response(msg, script, general_script['substitutions'], memory_stack, memory_inputs)

        # Clean response of Eliza prompt suffix (v1 removed 'Eliza: ' and '\nYou: ')
        response_text = response_text.replace('Eliza: ', '').replace('\nYou: ', '')

    except Exception as e:
        logger.exception('Eliza generation failed: %s', e)
        return make_response(500, {'error': {'message': 'Internal error generating response', 'type': 'server_error'}})

    elapsed_ms = int((time.time() - start) * 1000)

    # Structured log
    log_entry = {
        'timestamp': int(time.time()),
        'request_id': req_id,
        'caller_ip': caller_ip,
        'path': event.get('rawPath') or event.get('path'),
        'status_code': 200,
        'latency_ms': elapsed_ms,
        'message_preview': response_text[:120]
    }
    print(json.dumps(log_entry))

    # Build OpenAI-like response
    chat_id = f'eliza-{uuid.uuid4().hex}'
    out = {
        'id': chat_id,
        'object': 'chat.completion',
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': response_text},
                'finish_reason': 'stop'
            }
        ],
        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}
    }

    return make_response(200, out)
