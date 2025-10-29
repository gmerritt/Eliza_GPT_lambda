# Eliza-GPT Lambda

A zero-to-everything AWS Lambda deployment that exposes the classic Eliza chatbot as an OpenAI-compatible chat completion endpoint. This project provides complete infrastructure-as-code with one-command deployment from a fresh AWS account.

## What this project delivers

- **Lambda handler** (Python 3.10) wrapping Eliza-GPT with OpenAI-style chat completion JSON responses
- **CloudFormation template** (`template.yaml`) defining Lambda, IAM role, API Gateway HTTP API, and CloudWatch LogGroup
- **One-step deployment** (`deploy.sh`) that creates all AWS resources, packages code, and deploys the complete stack
- **Clean teardown** (`undeploy.sh`) that removes the stack and all deployment artifacts
- **Unit tests** (`tests/test_handler.py`) for local validation without AWS access
- **LiteLLM configuration** auto-generated with your deployed API URL

## Prerequisites

- AWS CLI installed and configured with valid credentials (run `aws configure` or set environment variables)
- IAM permissions to create S3 buckets, Secrets Manager secrets, CloudFormation stacks, IAM roles, API Gateway, and Lambda functions
- Python 3.10+ (for local testing only)

## Quick Start

# Eliza-GPT Lambda

A zero-to-everything AWS Lambda deployment that exposes the classic Eliza chatbot as an OpenAI-compatible chat completion endpoint. This project provides complete infrastructure-as-code with one-command deployment from a fresh AWS account.

## What this project delivers

- **Lambda handler** (Python 3.10) wrapping Eliza-GPT with OpenAI-style chat completion JSON responses
- **CloudFormation template** (`template.yaml`) defining Lambda, IAM role, API Gateway HTTP API, and CloudWatch LogGroup
- **One-step deployment** (`deploy.sh`) that creates all AWS resources, packages code, and deploys the complete stack
- **Clean teardown** (`undeploy.sh`) that removes the stack and all deployment artifacts
- **Unit tests** (`tests/test_handler.py`) for local validation without AWS access
- **LiteLLM configuration** auto-generated with your deployed API URL

## Prerequisites

- AWS CLI installed and configured with valid credentials (run `aws configure` or set environment variables)
- IAM permissions to create S3 buckets, Secrets Manager secrets, CloudFormation stacks, IAM roles, API Gateway, and Lambda functions
- Python 3.10+ (for local testing only)

## Quick Start

Deploy to a fresh AWS account with zero arguments:

```bash
chmod +x deploy.sh
./deploy.sh
```

This uses sensible defaults (S3 bucket: `eliza-gpt-deploy`, stack: `eliza-lambda-stack`, no API key).

Or customize the deployment:

```bash
./deploy.sh my-unique-bucket-name --stack-name eliza-stack --api-key my-api-key-123
```

That's it. The script will:

- Validate your AWS credentials
- Create the S3 bucket if it doesn't exist (with versioning enabled)
- Package the Lambda code and Eliza source
- Create a Secrets Manager secret for your API key
- Deploy the CloudFormation stack (Lambda, API Gateway, IAM role, logs)
- Output the deployed API URL
- Generate `litellm_config.yaml` for immediate use

## Deployment

Deploy the entire stack:

```bash
chmod +x deploy.sh
./deploy.sh my-deploy-bucket --stack-name eliza-lambda-stack --api-key my-dev-api-key
```

Or use defaults:

```bash
./deploy.sh
```

**Parameters:**

- `[s3-bucket]` (optional) — S3 bucket name for deployment artifacts. Default: `eliza-gpt-deploy`
- `--stack-name NAME` (optional) — CloudFormation stack name. Default: `eliza-lambda-stack`
- `--api-key KEY` (optional) — API key for authentication. Stored securely in Secrets Manager.
- `--api-key-ssm PARAM` (optional) — Use existing SSM Parameter for API key
- `--api-key-secret ARN` (optional) — Use existing Secrets Manager secret for API key
- `--log-requests` (optional) — Enable verbose logging of incoming requests. Default: disabled

**Examples:**

```bash
# Minimal deployment (no auth)
./deploy.sh my-deploy-bucket

# With API key authentication
./deploy.sh my-deploy-bucket --stack-name eliza-production --api-key sk-myapikey123

# Custom stack name, no auth
./deploy.sh my-deploy-bucket --stack-name my-custom-stack

# Enable verbose request logging for debugging
./deploy.sh my-deploy-bucket --log-requests

# Combine multiple options
./deploy.sh my-deploy-bucket --stack-name dev-eliza --api-key my-key --log-requests
```

### What happens during deployment

The `deploy.sh` script performs a complete zero-to-everything deployment:

1. **Validates AWS credentials** using STS GetCallerIdentity
2. **Creates S3 bucket** if it doesn't exist (with versioning enabled for deterministic deploys)
3. **Packages Lambda code** including `lambda/` directory and bundled `Eliza-GPT/src/eliza_gpt` source
4. **Uploads deployment artifact** with unique timestamped key so CloudFormation detects code changes
5. **Creates Secrets Manager secret** if API key provided (secret name: `eliza/api_key/<stack>-<timestamp>`)
6. **Deploys CloudFormation stack** with all infrastructure (Lambda, API Gateway, IAM, logs)
7. **Captures API URL** from stack outputs
8. **Generates `litellm_config.yaml`** with ready-to-use LiteLLM configuration

## Updates and Re-deployment

Run `deploy.sh` again with the same parameters to update your deployment. The script is fully idempotent:

- **Code changes**: Uploads a new uniquely-keyed artifact. CloudFormation detects the change and updates the Lambda.
- **Configuration changes**: Pass different parameters (e.g., new `AllowedCallerCIDR`) and CloudFormation updates the affected resources.
- **Versioning**: If S3 versioning is enabled (automatic), the script captures and uses `S3ObjectVersion` for deterministic deployments.

Each deployment publishes a new Lambda version, preserving previous versions for potential rollback.

## Undeploy and Cleanup

Remove all deployed resources and artifacts:

```bash
chmod +x undeploy.sh
./undeploy.sh my-deploy-bucket --stack-name eliza-lambda-stack
```

This completely removes:

- CloudFormation stack (Lambda, API Gateway, IAM role, logs)
- S3 deployment artifacts (objects with prefix `eliza_lambda_package-`)
- Secrets Manager secrets created during deployment (prefix `eliza/api_key/<stack>-`)

Note: Secrets are force-deleted without recovery. Edit `undeploy.sh` to enable a recovery window if desired.

## LiteLLM Integration

The deploy script automatically generates `litellm_config.yaml` with:

- Your API Gateway endpoint URL (retrieved from CloudFormation stack outputs)
- API key credentials (if provided during deployment)

Use this config to connect LiteLLM proxy to your deployed Eliza Lambda:

```bash
litellm --config litellm_config.yaml
```

## Security

- **API keys**: Never committed to Git. Deploy script creates a Secrets Manager secret and passes only the ARN to CloudFormation.
- **IAM permissions**: Lambda role has least-privilege access (CloudWatch Logs + Secrets Manager read for the specific secret).
- **Secret storage**: Lambda environment variables use CloudFormation dynamic references (`{{resolve:secretsmanager:...}}`) so secrets are never in cleartext in the template.
- **Artifact versioning**: S3 versioning is automatically enabled to ensure deployment determinism and auditability.

## Local testing

- Unit tests: run `pytest tests/test_handler.py -q` (these do not require AWS access).
- Manual call to handler (quick local smoke test):

```python
from lambda import app
resp = app.lambda_handler({'body': json.dumps({'messages':[{'role':'user','content':'hello'}]}), 'headers':{}, 'requestContext':{'http':{'sourceIp':'127.0.0.1'}}}, type('C', (), {'aws_request_id':'test'}))
print(resp)
```

## Project Structure

- `lambda/app.py` — Lambda handler entrypoint and request processing logic
- `template.yaml` — CloudFormation infrastructure-as-code template
- `deploy.sh` — Zero-to-everything deployment automation
- `undeploy.sh` — Complete cleanup automation
- `tests/test_handler.py` — Unit tests (run locally with `pytest`)
- `litellm_config.yaml` — Auto-generated LiteLLM configuration (created during deployment)

## Advanced Configuration

### CIDR allow-listing

Restrict API access by IP range using the `AllowedCallerCIDR` CloudFormation parameter. Edit `template.yaml` to change the default or pass via deploy parameters.

### Custom domain and TLS

The default deployment uses API Gateway's generated domain. For production, configure a custom domain in API Gateway and update DNS records.

### Monitoring and alarms

Consider adding:

- CloudWatch Alarms for Lambda errors and API Gateway 4xx/5xx rates
- CloudWatch Dashboard for request volume and latency metrics
- AWS WAF for advanced request filtering

### CI/CD integration

Run `deploy.sh` from GitHub Actions or similar CI systems. Required secrets: AWS credentials with deployment permissions.

## API Contract

A brief summary of the API request/response format is provided here for quick reference. The full API contract (including edge cases and error responses) is documented in `project_reference_documentation/02_spec.md`.

- Request: POST /v1/chat/completions with a JSON body containing a `messages` array. Each message is an object with `role` and `content`. The handler expects at least one `user` message.

Example request body:

```json
{
	"messages": [
		{"role": "user", "content": "Hello"}
	]
}
```

- Response: OpenAI-style chat completion JSON. Typical top-level fields include `id`, `object`, `choices`, and `usage`. The generated assistant message appears at `choices[0].message` and has `role: "assistant"` and `content` fields.

See `project_reference_documentation/02_spec.md` for full schema, status-code mapping, and error response examples.

## Logging and Troubleshooting

The Lambda emits structured JSON logs to CloudWatch Logs. The LogGroup name is derived from the CloudFormation-created Lambda function and typically looks like:

```
/aws/lambda/<stack-name>-ElizaLambdaFunction-<logical-id>
```

Log entries are single-line JSON objects containing fields such as `timestamp`, `request_id`, `caller_ip`, `path`, `status_code`, `latency_ms`, and a short `message_preview`. Example log line:

```json
{"timestamp":"2025-10-22T12:34:56Z","request_id":"abcd-1234","caller_ip":"203.0.113.5","path":"/v1/chat/completions","status_code":200,"latency_ms":12,"message_preview":"hello"}
```

### Verbose Request Logging

For debugging purposes, you can enable verbose request logging by deploying with the `--log-requests` flag. When enabled, the Lambda will log the complete incoming request event (including headers, body, and all API Gateway metadata) to CloudWatch Logs. This is useful for troubleshooting integration issues but should be used with caution in production due to increased log volume and potential exposure of sensitive data.

Example log entry with request logging enabled:

```json
{"request_id":"abcd-1234","event":{"headers":{"authorization":"Bearer ***","content-type":"application/json"},"body":"{\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]}","requestContext":{...}},"caller_ip":"203.0.113.5","log_type":"request_verbatim"}
```

Common troubleshooting tips:

- 401 Unauthorized: Verify the API key is present in Secrets Manager (or SSM) and that clients send `Authorization: Bearer <key>`.
- 403 Forbidden: Check `AllowedCallerCIDR` and confirm the caller IP (or `X-Forwarded-For`) falls within the allowed range.
- 400 Bad Request: The request body may be missing `messages` or contain malformed JSON. Validate payload formatting.
- 500 Internal Server Error: Inspect CloudWatch Logs for stack traces. Common causes include missing/incorrect Eliza packaging or runtime exceptions during response generation.

For local debugging, run the unit tests and invoke `lambda.app.lambda_handler` with an event that closely mirrors API Gateway v2 HTTP events.

## Project Documentation

The project contains extended reference and design documents under `project_reference_documentation/` that are useful for contributors and integrators:

- `01_planning.md` — planning and goals
- `02_spec.md` — API contract and detailed input/output schema (recommended for integrators)
- `03_implementation.md` — implementation notes and packaging instructions

Linking these documents from the top-level README helps new contributors find design rationale and operational guidance quickly.

## License and Attribution

This repository includes the `Eliza-GPT` submodule located in `Eliza-GPT/`. The submodule is distributed under its own license—please see `Eliza-GPT/LICENSE` for details and attribution requirements.

When redistributing or modifying this project, ensure you comply with the `Eliza-GPT` license and include the required attribution.
