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


def estimate_tokens(text: str) -> int:
    """
    Estimate token count based on word count.
    Uses a rough approximation: 1 token ≈ 0.75 words (or 1.33 tokens per word).
    This is a common rule of thumb for English text with GPT models.
    """
    if not text:
        return 0
    # Split on whitespace and count words
    word_count = len(text.split())
    # Apply approximation: ~1.33 tokens per word
    return max(1, int(word_count * 1.33))


def _init_eliza() -> Tuple[dict, list, list]:
    """Initialize Eliza scripts and return (general_script, script, memory_inputs)."""
    if eliza_setup is None:
        # Try to locate the Eliza-GPT source tree relative to this repo and
        # load the eliza_py modules directly from files to avoid importing the
        # top-level package (which pulls in microdot and other deps).
        import sys
        import importlib.util

        # Search for eliza_gpt/eliza_gpt/eliza_py in the Lambda package
        from pathlib import Path
        here = Path(__file__).resolve().parent
        eliza_py_dir = None
        
        # In the deployed Lambda package, eliza_gpt/ is at the root alongside app.py
        candidate = here / 'eliza_gpt' / 'eliza_gpt' / 'eliza_py'
        if candidate.is_dir():
            eliza_py_dir = str(candidate)
        else:
            # Fallback: search upward for local dev/test environments
            for parent in [here] + list(here.parents):
                candidate_old = parent / 'Eliza-GPT' / 'src' / 'eliza_gpt' / 'eliza_py'
                if candidate_old.is_dir():
                    eliza_py_dir = str(candidate_old)
                    break
                candidate_src = parent / 'src' / 'eliza_gpt' / 'eliza_py'
                if candidate_src.is_dir():
                    eliza_py_dir = str(candidate_src)
                    break
        
        if not eliza_py_dir:
            logger.exception('Eliza eliza_py directory not found in expected locations')
            raise ImportError('Eliza eliza_py directory not found')

        try:
            # Add eliza_py directory to sys.path so relative imports (e.g., 'from utils.startup import setup') work
            if eliza_py_dir not in sys.path:
                sys.path.insert(0, eliza_py_dir)
            
            # Load eliza.py
            spec = importlib.util.spec_from_file_location('eliza_py.eliza', os.path.join(eliza_py_dir, 'eliza.py'))
            eliza_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(eliza_mod)

            # Load utils.startup
            spec2 = importlib.util.spec_from_file_location('eliza_py.utils.startup', os.path.join(eliza_py_dir, 'utils', 'startup.py'))
            startup_mod = importlib.util.module_from_spec(spec2)
            spec2.loader.exec_module(startup_mod)

            # Load utils.response
            spec3 = importlib.util.spec_from_file_location('eliza_py.utils.response', os.path.join(eliza_py_dir, 'utils', 'response.py'))
            response_mod = importlib.util.module_from_spec(spec3)
            spec3.loader.exec_module(response_mod)

            # assign into module globals to avoid parser-level 'global' issues
            globals()['GENERAL_SCRIPT_PATH'] = getattr(eliza_mod, 'GENERAL_SCRIPT_PATH')
            globals()['SCRIPT_PATH'] = getattr(eliza_mod, 'SCRIPT_PATH')
            globals()['eliza_setup'] = getattr(startup_mod, 'setup')
            globals()['generate_response'] = getattr(response_mod, 'generate_response')
        except Exception as e:
            logger.exception('Failed to load Eliza modules from files: %s', e)
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


def _extract_text_from_content(content) -> str:
    """Normalize various incoming message content shapes into a plain text string.

    Handles:
    - plain strings
    - dicts like {"type": "text", "text": "..."} or {"text": "..."}
    - lists of such dicts (e.g., multipart messages containing images and text)

    Non-text parts (image/base64) are ignored.
    Returns empty string when no textual content is found.
    """
    if content is None:
        return ''

    # Already a plain string
    if isinstance(content, str):
        return content

    # Dict-like content
    if isinstance(content, dict):
        # Common shapes: {'text': '...'}, {'content': '...'}, {'type':'text','text':'...'}
        text_val = content.get('text')
        if isinstance(text_val, str):
            return text_val
        content_val = content.get('content')
        if isinstance(content_val, str):
            return content_val
        # Some payloads use 'parts' as a list of strings
        parts = content.get('parts')
        if isinstance(parts, list):
            return ' '.join([p for p in parts if isinstance(p, str)])
        return ''

    # List-like content: aggregate textual parts and ignore others (like images/base64)
    if isinstance(content, (list, tuple)):
        pieces = []
        for el in content:
            if isinstance(el, str):
                pieces.append(el)
                continue
            if not isinstance(el, dict):
                # ignore unexpected element types
                continue

            # nested dict shapes similar to above
            text_val = el.get('text')
            if isinstance(text_val, str):
                pieces.append(text_val)
                continue
            content_val = el.get('content')
            if isinstance(content_val, str):
                pieces.append(content_val)
                continue
            parts = el.get('parts')
            if isinstance(parts, list):
                pieces.extend([p for p in parts if isinstance(p, str)])
            # otherwise ignore (e.g., image_url with base64 blobs)

        return ' '.join(pieces).strip()

    # Fallback: coerce to string for unexpected types to avoid returning lists/other types
    try:
        return str(content)
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


def _build_sse_body(response_text: str, chat_id: str, model_name: str = 'eliza-lambda', chunk_size: int = 64) -> str:
    """
    Build a single string body containing SSE-formatted data chunks followed by [DONE].
    Each content chunk is JSON per the spec, prefixed with 'data: ' and followed by two newlines.

    Note: This constructs the SSE stream as a single response body. If true HTTP streaming
    (progressive chunks during Lambda execution) is required, the API Gateway/Lambda setup
    must support streaming; this function provides the SSE format compatible with LiteLLM's parser.
    """
    if not response_text:
        # If empty response, just send DONE
        return 'data: [DONE]\n\n'

    parts = []
    # Chunk by fixed number of characters to approximate streaming partials.
    for i in range(0, len(response_text), chunk_size):
        seg = response_text[i:i + chunk_size]
        chunk_payload = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": seg},
                    "finish_reason": None
                }
            ]
        }
        parts.append('data: ' + json.dumps(chunk_payload) + '\n\n')

    # Final termination chunk
    parts.append('data: [DONE]\n\n')
    return ''.join(parts)


def lambda_handler(event, context):
    start = time.time()
    req_id = getattr(context, 'aws_request_id', None) or str(uuid.uuid4())
    caller_ip = extract_caller_ip(event)

    # Check if verbose request logging is enabled
    log_requests = os.environ.get('LOG_REQUESTS', 'false').lower() in ('1', 'true', 'yes')
    if log_requests:
        logger.info(json.dumps({
            'request_id': req_id,
            'event': event,
            'caller_ip': caller_ip,
            'log_type': 'request_verbatim'
        }))

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

    # Extract messages - only use the LAST user message text, ignore history and base64
    messages = payload.get('messages') or []
    
    # Find the most recent user message
    user_input = ''
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get('role') == 'user':
            user_input = _extract_text_from_content(msg.get('content'))
            if user_input:
                break
    
    if not user_input:
        return make_response(400, {'error': {'message': 'No user message provided', 'type': 'bad_request'}})

    general_script, script, memory_inputs = get_eliza_state()

    # Generate response from the single user input (Eliza is stateless per request)
    try:
        response_text = generate_response(user_input, script, general_script['substitutions'], [], memory_inputs)
        # Clean response of Eliza prompt suffix
        response_text = response_text.replace('Eliza: ', '').replace('\nYou: ', '')
    except Exception as e:
        logger.exception('Eliza generation failed: %s', e)
        return make_response(500, {'error': {'message': 'Internal error generating response', 'type': 'server_error'}})

    elapsed_ms = int((time.time() - start) * 1000)

    # Calculate token estimates
    prompt_tokens = estimate_tokens(user_input)
    completion_tokens = estimate_tokens(response_text)
    total_tokens = prompt_tokens + completion_tokens

    # Structured log
    log_entry = {
        'timestamp': int(time.time()),
        'request_id': req_id,
        'caller_ip': caller_ip,
        'path': event.get('rawPath') or event.get('path'),
        'status_code': 200,
        'latency_ms': elapsed_ms,
        'message_preview': response_text[:120],
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens
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
        'usage': {
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens
        }
    }

    # If the caller asked for streaming, return SSE formatted body
    # (payload is parsed earlier from the incoming event)
    try:
        stream_requested = False
        # payload may be in local scope of lambda_handler
        stream_requested = payload.get('stream') is True or payload.get('stream') == 'true'
    except Exception:
        stream_requested = False

    if stream_requested:
        model_name = os.environ.get('MODEL_NAME', 'eliza-lambda')
        chunk_size_env = os.environ.get('SSE_CHUNK_SIZE')
        try:
            chunk_size = int(chunk_size_env) if chunk_size_env else 64
        except Exception:
            chunk_size = 64

        sse_body = _build_sse_body(response_text, chat_id, model_name=model_name, chunk_size=chunk_size)
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/event-stream; charset=utf-8',
                'Cache-Control': 'no-cache'
            },
            'body': sse_body
        }

    return make_response(200, out)
