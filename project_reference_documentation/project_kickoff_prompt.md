This is an AWS CloudFormation project to deploy a lambda function.

Requirements:

* The core purpose of the lambda function is to do OpenAI-style chat completions of the classic Eliza chatbot, as encoded in the Eliza-GPT git submodule.
* This lambda function will be called by LiteLLM, so it must be compatible with LiteLLM calls. As such, this project should document a LiteLLM config.yaml block for configuring LiteLLM for this lambda-based Eliza model. (If required, the configuration should include `supports_system_message: False`, but only if this is required.)
* The lambda function must support configurable allow-list IP(s); optional, or be able to add by subnet (so that it could be “turned off” with 0.0.0.0/0 if desired).
* This lambda function should output logs to CloudWatch, ideally recording source caller IP address.
* Use documents in `project_reference_documentation/` to inform specs for this implementation.

We are going to follow these phases of project development:

1. Planning mode: The model first writes a plan.
2. Spec mode: The model converts the plan into a spec.
3. Implementation mode: The model implements the spec.
4. Critic mode: This mode's sole function is to find flaws in what the implementation mode just created.
5. Revise mode: This final mode is used to revise the work.
