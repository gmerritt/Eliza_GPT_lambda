Eliza-GPT Lambda — Technical Specification (02_spec.md)

Purpose

This document converts the planning notes into a concrete technical specification for delivering an AWS CloudFormation-deployed Lambda that implements the classic Eliza chatbot as a LiteLLM-compatible model endpoint.

Success criteria

- A CloudFormation YAML template (`template.yaml`) that deploys:
  - Lambda function (Python 3.10+) containing Eliza logic
  - IAM Role with least privilege for Lambda execution (CloudWatch Logs only)
  - API Gateway HTTP API (public) with a route (e.g., /v1/chat/completions or /eliza) integrated to the Lambda
  - CloudWatch LogGroup for Lambda logs
  - CloudFormation Parameters: AllowedCallerCIDR (string), LogGroupName (string), LambdaS3Key (if needed)
- Lambda handler that accepts LiteLLM/OpenAI-style JSON and returns OpenAI-like chat completion JSON
- Logging includes structured JSON with caller IP when available
- Configurable CIDR allow-list for caller IPs enforced by Lambda middleware (parameterized)
- `deploy.sh` packaging + deploy script using `aws cloudformation package` + `deploy`
- `project_reference_documentation/02_spec.md` (this file) + `project_reference_documentation/03_implementation_plan.md` (outline)

Assumptions & Constraints

- Python 3.10+ runtime.
- Eliza logic is importable from `src/eliza_gpt` (existing submodule). We'll create a small wrapper module `lambda_handler.py` that imports and calls the eliza code.
- LiteLLM will call the API via HTTP API Gateway. Caller IP will be extracted from `requestContext.http.sourceIp` or `X-Forwarded-For` header.
- We will implement a simple API key check (optional) and allow-list check via CloudFormation parameter to support quick lockdown.

File layout to add

- `template.yaml` — CloudFormation template (root)
- `lambda/` — folder containing Lambda source
  - `lambda/app.py` — Lambda handler entrypoint
  - `lambda/requirements.txt` — runtime dependencies (if any)
  - `lambda/zip_package.sh` — helper for building zip (optional)
- `deploy.sh` — packaging and deployment helper
- `project_reference_documentation/02_spec.md` — this spec (added)
- `project_reference_documentation/03_implementation_plan.md` — next steps (will be brief)
- `tests/` — unit tests for handler

CloudFormation design

Parameters
- AllowedCallerCIDR (String) — e.g. `0.0.0.0/0` default for dev, but recommended to set to LiteLLM's proxy CIDR in prod.
- LambdaS3Bucket (String) — bucket where packaged code will be uploaded (required for packaging)
- LogGroupName (String) — optional CloudWatch LogGroup name
- StackName (String) — optional override

Resources

1. LambdaExecutionRole (IAM::Role)
   - AssumeRolePolicyDocument for lambda.amazonaws.com
   - ManagedPolicy/Inline Policy allowing:
     - logs:CreateLogGroup, logs:CreateLogStream, logs:PutLogEvents on the LogGroup
2. ElizaLambdaFunction (AWS::Lambda::Function)
   - Runtime: python3.10
   - Handler: app.lambda_handler
   - Role: LambdaExecutionRole
   - Environment Variables:
     - ALLOWED_CALLER_CIDR (value from AllowedCallerCIDR)
     - LOG_GROUP_NAME (LogGroupName)
     - REQUIRE_API_KEY (optional flag)
   - Code: S3 Bucket and Key provided by `aws cloudformation package` step
   - Timeout: 10 seconds (configurable)
   - MemorySize: 256 MB
3. ApiGatewayHttpApi (AWS::ApiGatewayV2::Api)
   - ProtocolType: HTTP
4. ApiGatewayIntegration (AWS::ApiGatewayV2::Integration)
   - IntegrationType: AWS_PROXY (Lambda proxy integration)
5. ApiGatewayRoute and Stage
   - Route: POST /v1/chat/completions and POST /eliza
   - Stage: $default (or a named stage) with auto-deploy enabled
6. LambdaPermission (AWS::Lambda::Permission)
   - Allow ApiGateway to invoke the Lambda
7. LogGroup (AWS::Logs::LogGroup)
   - Name from parameter, retention optional

IAM least privilege
- Only grant Logs create/put permissions scoped to the specific LogGroup ARN

API contract (handler)

Input JSON (HTTP POST body): LiteLLM/OpenAI-compatible chat request. Minimal expected fields:
{
  "model": "eliza-lambda",
  "messages": [
    { "role": "system" | "user" | "assistant", "content": "..." },
    ...
  ],
  "max_tokens": optional
}

Processing rules:
- If `supports_system_message: False` (configured in LiteLLM), LiteLLM will map system messages to user. Our handler should accept system messages, but if present and unsupported by Eliza, we will append system content into the start of the conversation as a note or ignore it — Spec will choose to prepend system content to the user prompt to preserve intent.
- Eliza is a rule-based bot; we will call the Eliza API with the last user message or the conversation history depending on the Eliza wrapper's API.
- The handler will compute a response string and return OpenAI-like response JSON.

Output JSON (OpenAI-like):
{
  "id": "eliza-<uuid>",
  "object": "chat.completion",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "<eliza response>" },
      "finish_reason": "stop"
    }
  ],
  "usage": { "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0 }
}

Errors: return HTTP status codes and body { "error": { "message": "...", "type": "..." } }

Caller IP and allow-listing

- The Lambda handler will extract caller IP using the following precedence:
  1. If header `X-Forwarded-For` exists, take the first IP in the comma-separated list
  2. Else, if API Gateway v2 event has `requestContext.http.sourceIp`, use it
  3. Else, use `event['requestContext']['identity']['sourceIp']` (legacy)

- Allow-list evaluation:
  - The CloudFormation parameter `AllowedCallerCIDR` may contain one or more comma separated CIDRs.
  - At handler start, parse env var `ALLOWED_CALLER_CIDR`. If empty or `0.0.0.0/0` accept all. Otherwise, verify caller IP is within at least one allowed CIDR using the `ipaddress` stdlib module. If not allowed, return 403.

Auth options (specify in template/environment)
- Option A: No API key, rely purely on allow-list CIDR and API Gateway (for internal LiteLLM deployments).
- Option B: Simple API key header check. Set `REQUIRE_API_KEY=true` and `API_KEY` env var via CloudFormation secrets or parameter; handler checks Authorization: Bearer <api_key>.
- Option C: Use API Gateway JWT or Lambda authorizer (not in this initial spec; we'll document as recommendation).

Logging

- Use Python logging with a JSON formatter (small helper in `lambda/logging.py`) to emit structured logs to CloudWatch.
- Logged fields:
  - timestamp
  - request_id (from Lambda context.aws_request_id)
  - caller_ip
  - path
  - status_code
  - latency_ms
  - message_preview (first 120 chars of Eliza response)
  - error (if any)

Testing plan

Unit tests (fast, run locally)
- Test `lambda/app.py` handler logic with simulated API Gateway v2 events:
  - Happy path: valid messages, allowed caller IP -> returns 200 and well-formed OpenAI-like JSON
  - Disallowed IP -> returns 403
  - Missing messages -> returns 400
  - System message present with `supports_system_message=False` mapping -> verify behavior
  - API key required but missing/incorrect -> returns 401

Integration tests (optional CI stage)
- Deploy to a temporary stack, call API endpoint, verify response and CloudWatch log entries (caller IP present). This will be optional because it requires real AWS credentials.

Implementation tasks (overview)

1. Create `template.yaml` CloudFormation resource definitions above. Use `AWS::ApiGatewayV2` HTTP API.
2. Create `lambda/app.py` handler that:
   - Accepts event/context,
   - Parses body, headers,
   - Extracts caller IP, enforces allow-list and API key checks,
   - Invokes Eliza reply logic from `src/eliza_gpt` (wrap the import),
   - Logs structured entry, and
   - Returns appropriately formatted JSON.
3. Add `deploy.sh` to build zip (use `aws cloudformation package` flow).
4. Add unit tests in `tests/test_handler.py` using pytest and small fixtures.
5. Add README update with instructions and LiteLLM `config.yaml` example.

LiteLLM configuration examples (to include in README and docs)

1) OpenAI-compatible model block (example):

model_list:
  - model_name: eliza-lambda
    litellm_params:
      model: openai/eliza-lambda
      api_base: https://<api-gateway-host>/v1
      api_key: ""  # if auth is handled elsewhere
      supports_system_message: False

2) Pass-through endpoint mapping example (path prefix to API Gateway):

general_settings:
  pass_through_endpoints:
    - path_prefix: /eliza
      target_url: https://<api-gateway-host>/v1
      headers:
        Authorization: "Bearer <api_key>"  # or leave blank if not required

Operational considerations

- Monitor CloudWatch Logs for errors and latency spikes.
- Add CloudWatch Alarms for high error rates or invocation errors.
- Consider adding WAF to the API Gateway in production and move allow-listing to WAF when available.
- If package size becomes large, move dependencies to a Lambda Layer or use container image Lambda.

Security review notes

- Ensure `AllowedCallerCIDR` default is conservative for production (do not leave as 0.0.0.0/0 in production).
- Avoid hardcoding API keys in source control; prefer SSM Parameter Store or Secrets Manager for secrets (discussed in improvements section).

Next steps

- Implement the CloudFormation template and Lambda source as specified above.
- Write unit tests and a README with `config.yaml` examples.


