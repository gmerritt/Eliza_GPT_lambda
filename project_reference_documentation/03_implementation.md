# 03 Implementation — Eliza-GPT Lambda

This document describes the final, current implementation of the Eliza-GPT Lambda project. It focuses on the implemented code, infrastructure, deployment flow, security, and how to run and test the system. It omits the development history and rationale — the content below describes the present state.

Summary (contract)

- Input: HTTP POST /v1/chat/completions JSON payload compatible with OpenAI Chat Completions (messages list, user/system roles)
- Output: JSON response matching OpenAI chat completion shape (id, object, created, model, choices[*].message, usage optional)
- Success modes: returns HTTP 200 with completion JSON for valid requests from allowed callers with valid API key (if enabled)
- Error modes: 400 for malformed requests, 401 for missing/invalid API key (when enabled), 403 for disallowed caller IP, 500 for internal errors

Architecture and components

- Lambda function (`lambda/app.py`) — primary request handler. Responsibilities:
  - Validate incoming event structure and required fields
  - Optionally enforce CIDR-based allow-listing (configured via CloudFormation parameter `AllowedCallerCIDR`)
  - Optionally enforce API key requirement. API key is retrieved either from Secrets Manager dynamic reference or SSM parameter depending on deployment configuration
  - Load Eliza chatbot code at runtime and produce replies in OpenAI-compatible JSON structure
  - Return consistent error responses and log structured messages to CloudWatch

- CloudFormation template (`template.yaml`) — infrastructure as code. Resources included:
  - Lambda function (Python 3.10 runtime) with an execution role and minimum required permissions
  - API Gateway (HTTP API) with a POST route `/v1/chat/completions` integrated with the Lambda
  - CloudWatch LogGroup for Lambda logs
  - Optional IAM permissions for reading a specific Secrets Manager secret (when API key secret is used)
  - Parameterization for `LambdaS3Bucket`, `LambdaS3Key`, `LambdaS3ObjectVersion`, `AllowedCallerCIDR`, and API key options

- Deployment helper (`deploy.sh`) — zero-to-everything automation. Behavior:
  - Accepts an optional positional `s3-bucket` and named flags: `--stack-name`, `--api-key`, `--api-key-ssm`, `--api-key-secret`
  - If no `s3-bucket` is provided, uses a single invariant default bucket name: `eliza-gpt-deploy` and attempts to create it in the configured region
  - Packages `lambda/` and `Eliza-GPT/src/eliza_gpt` into a zip artifact
  - Uploads artifact to S3 using a unique key (timestamped) so CloudFormation detects code changes
  - Creates a Secrets Manager secret when a plaintext `--api-key` is supplied and passes its ARN to CloudFormation instead of plaintext
  - Runs `aws cloudformation package` and `aws cloudformation deploy` with appropriate parameter overrides
  - Captures the API URL from CloudFormation outputs and writes `litellm_config.yaml` for LiteLLM integration

- Undeploy helper (`undeploy.sh`) — cleans up stack and artifacts. Behavior:
  - Accepts `s3-bucket` (or uses default) and `--stack-name`
  - Deletes the CloudFormation stack and waits for completion
  - Removes S3 objects uploaded by the deploy script (prefix `eliza_lambda_package-`)
  - Attempts to delete Secrets Manager secrets created by the deploy script (prefix `eliza/api_key/`)

- Tests
  - `tests/test_handler.py` — pytest unit tests for the Lambda handler. These run locally and do not require AWS access
  - `conftest.py` — test support to add local `Eliza-GPT/src` to `sys.path` so tests can import Eliza code without installing

Files of interest (where to look)

- `lambda/app.py` — Lambda handler and request processing
- `template.yaml` — CloudFormation definitions and parameters
- `deploy.sh` — deployment automation and litellm config generation
- `undeploy.sh` — teardown automation
- `tests/test_handler.py` — unit tests (run with `pytest`)
- `project_reference_documentation/03_implementation.md` — this file
- `README.md` — user-facing quick start and detailed instructions

How to deploy (minimal)

Make the scripts executable and run deploy with defaults:

```bash
chmod +x deploy.sh
./deploy.sh
```

Custom deployment with API key and custom stack name:

```bash
./deploy.sh my-bucket --stack-name my-eliza-stack --api-key sk-mysecret
```

What the deploy script outputs

- CloudFormation stack outputs (visible during/after deploy)
- A generated `litellm_config.yaml` containing `api_base` pointing at the deployed API Gateway URL and `api_key` (if provided during deploy). The script attempts to fetch the stack output `ApiUrl` and write it into the config.

Security

- API keys are stored in AWS Secrets Manager when provided to `deploy.sh` via `--api-key` and only the secret ARN is passed to CloudFormation
- Lambda execution role is scoped to required permissions (CloudWatch Logs and Secrets Manager read for the secret ARN)
- Secrets are referenced in the template via CloudFormation dynamic references (`{{resolve:secretsmanager:...}}`) so values are not present in template plaintext
- S3 bucket versioning is enabled to ensure auditability of deployment artifacts

Edge cases and notes

- The default bucket name `eliza-gpt-deploy` is invariant; provide your own bucket if you need a different name or to avoid name collisions in other accounts/regions
- If the default bucket already exists and is owned by another account, creation will fail. Pass a custom unique bucket name as the first positional arg to the script instead
- The deploy script assumes `aws` CLI is configured and available in PATH

How to test locally

- Run unit tests:

```bash
pytest tests/test_handler.py -q
```

- Quick local handler smoke test (python REPL):

```python
import json
from importlib import import_module
app = import_module('lambda.app')
resp = app.lambda_handler({'body': json.dumps({'messages':[{'role':'user','content':'hello'}]}), 'headers':{}, 'requestContext':{'http':{'sourceIp':'127.0.0.1'}}}, type('C', (), {'aws_request_id':'test'}))
print(resp)
```

Status

- Document created and added to `project_reference_documentation/03_implementation.md`.

If you want, I can also:

- Add a short `USAGE.md` with copy/paste commands and a DevOps checklist
- Add an optional safety check that aborts when the invariant default bucket exists but is owned by a different account

Finished working — mark the todo as completed? (I already updated the todo list.)
