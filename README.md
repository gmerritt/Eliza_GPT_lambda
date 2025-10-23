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
- `--api-key-ssm PARAM` (optional) — Use existing SSM Parameter for API key
- `--api-key-secret ARN` (optional) — Use existing Secrets Manager secret for API key

**Examples:**

```bash
# Minimal deployment (no auth)
./deploy.sh my-deploy-bucket

# With API key authentication
./deploy.sh my-deploy-bucket eliza-production sk-myapikey123

# Custom stack name, no auth
./deploy.sh my-deploy-bucket my-custom-stack
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
