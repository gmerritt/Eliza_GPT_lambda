Eliza-GPT Lambda — Project Plan

Overview

This project will create an AWS Lambda-based service that exposes the classic Eliza chatbot (from the Eliza-GPT submodule) as a LiteLLM-compatible model endpoint. The Lambda will accept LiteLLM-style requests and return OpenAI-like chat completions emulating Eliza's behavior. The deliverable will include CloudFormation (or AWS SAM) infrastructure, Lambda handler code, configuration docs (including a sample LiteLLM `config.yaml` block), logging to CloudWatch (including caller IP), an optional allow-list for caller IPs (CIDR/subnet based), tests, and deployment instructions.

Goals

- Provide a lightweight Lambda that performs Eliza-style chat completions.
- Ensure compatibility with LiteLLM calls (include necessary config.yaml example).
- Add optional allow-listing of caller IP addresses (CIDR support) configurable via environment variable or CloudFormation parameter.
- Emit structured logs to CloudWatch and log caller IP address when available.
- Deliver CloudFormation templates, a minimal packaging and deployment guide, and tests that validate the handler.

Non-goals

- Not implementing an LLM or OpenAI API; Eliza behavior is rule-based and already present in the submodule.
- Not building a fully-featured production-grade API gateway with throttling and WAF (but will recommend them).

Constraints

- Lambda size limits: packaged function must fit within Lambda deployment limits (uncompressed < 50 MB for direct upload, or use S3 deployment). Keep dependencies minimal.
- Runtime: Prefer Python (3.10+ recommended) matching existing Eliza-GPT code in `src/eliza_gpt`.
- Network: Caller IP availability depends on the fronting service (API Gateway provides IPs in headers; direct LiteLLM integration may run in VPCs). We'll design for API Gateway integration.
- Support for LiteLLM: ensure response shape and behavior match LiteLLM expectations for chat completions. If LiteLLM requires config flag `supports_system_message: False`, document it.

Assumptions

- The Eliza-GPT code under `src/eliza_gpt` is importable and contains a programmatic interface for generating replies.
- LiteLLM will call the Lambda via API Gateway (HTTP) using a REST or HTTP API; caller IP will be captured from request context or headers (e.g., `X-Forwarded-For`).
- Environment variables and CloudFormation parameters can be used to configure allow-list CIDRs.
- IAM roles and least privilege will be applied for Lambda execution (CloudWatch Logs full access for writing logs).

High-level architecture

- API Gateway (HTTP API) receives incoming requests from LiteLLM.
- API Gateway triggers Lambda function (Python 3.10+).
- Lambda loads Eliza module, processes the incoming LiteLLM-style request into Eliza's input form, runs the response, and returns a LiteLLM-compatible chat completion JSON.
- Lambda logs request metadata (timestamp, request-id, caller IP, request size) to CloudWatch Logs.
- Allow-listing: a middleware step in the Lambda handler checks the caller IP against configured CIDRs (from env var or CloudFormation parameter). If not allowed, return 403.

Data contract / API

- Input: LiteLLM-style JSON with fields like `model`, `messages` (array of role/content objects), `max_tokens` (ignored/optional), `request_id` (optional).
- Output: JSON mimicking OpenAI chat completions, e.g., top-level `id`, `object: "chat.completion"`, `choices` array with `message` containing `role` and `content`, and `usage` (tokens counts may be synthetic or omitted).
- Error responses: standard HTTP error codes and a JSON body with `error: { message, type }`.

Security and Networking

- Allow-listing CIDRs controlled by a CloudFormation parameter `AllowedCallerCIDR` (string, default empty or 0.0.0.0/0 to allow all). Lambda checks incoming IP; API Gateway stage could also enforce IP restrictions.
- Use IAM role with minimal privileges: CloudWatch Logs write only. If S3 or other services used for deployment, ensure separate roles for deployment.
- Recommend adding AWS WAF in front of API Gateway for production control.

Logging and Observability

- Structured JSON logs written to CloudWatch via Python `logging` with a JSON formatter.
- Log fields: timestamp, request_id, caller_ip, path, duration_ms, status_code, size_in/out, and eliza_response_preview.
- Expose a CloudWatch Log Group name via CloudFormation parameter.

Testing

- Unit tests for handler logic using local invocation of the handler function and test events (simulate API Gateway v2 HTTP API events and include `X-Forwarded-For`).
- Integration test: deploy into a temporary test stack and run an HTTP request (optional for CI).
- Test cases: normal chat flow, missing messages, disallowed IP, malformed JSON, and large payload.

Deployment

- Provide CloudFormation template(s): `template.yaml` with Lambda resource, IAM role, API Gateway HTTP API, Log Group, and optional parameter for allowed CIDR(s).
- Packaging: Use Python packaging (zip) and a simple script to upload to S3 and deploy CloudFormation, or use `sam build`/`sam deploy` if preferred.
- Provide a `Makefile` or simple `deploy.sh` with commands.

LiteLLM config.yaml example

- Include a sample block suitable for LiteLLM to call this Lambda via HTTP API or via a supported Lambda invocation method. Document `supports_system_message: False` if LiteLLM cannot provide system messages for this model.

Milestones and timeline

- Week 0: Planning and spec (this file + spec doc).
- Week 1: Implementation: CloudFormation template, Lambda handler, minimal packaging, and unit tests.
- Week 2: Integration tests, documentation, and sample LiteLLM `config.yaml`.

Deliverables

- `project_reference_documentation/01_planning.md` (this file)
- `project_reference_documentation/02_spec.md` (next)
- CloudFormation template(s) and Lambda source in repository
- Unit tests and a basic integration test plan
- README with deploy/run instructions and LiteLLM config example

Open questions / Risks

- How will LiteLLM call the Lambda in the intended environment (HTTP API Gateway vs direct Lambda invoke)? This affects how caller IP is recorded.
- If Eliza-GPT submodule has unexpected heavy dependencies, Lambda package size might exceed limits; may need to slim or use layers.
- Caller IP capture: when behind private networks or proxies, headers may not contain the true client IP.

Next steps

- Create a detailed spec document (`02_spec.md`) that translates this plan into concrete CloudFormation resources, environment variables, input/output schemas, and sample events for tests.
- Start implementation after spec approval.


