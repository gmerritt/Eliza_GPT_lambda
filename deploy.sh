#!/usr/bin/env bash
# Simple deploy helper: package code into S3 and deploy CloudFormation
set -euo pipefail

# Parse arguments
S3_BUCKET=""
STACK_NAME="eliza-lambda-stack"
API_KEY_PLAIN=""
API_KEY_SSM=""
API_KEY_SECRET=""
LOG_REQUESTS="false"
TEMPLATE_FILE=template.yaml
ZIP_NAME=eliza_lambda_package.zip
ZIP_PATH="$(pwd)/$ZIP_NAME"
LAMBDA_DIR=lambda
ALLOWED_CALLER_CIDR="0.0.0.0/0"

show_usage() {
  cat <<EOF
Usage: $0 [s3-bucket] [options]

Optional:
  s3-bucket               S3 bucket name for deployment artifacts
                          (default: eliza-lambda-<account-id>)

Options:
  --stack-name NAME       CloudFormation stack name (default: eliza-lambda-stack)
  --api-key KEY           API key for authentication (stored in Secrets Manager)
  --api-key-ssm PARAM     SSM Parameter name containing API key
  --api-key-secret ARN    Secrets Manager secret ARN/ID containing API key
  --log-requests          Enable verbose logging of incoming requests (default: false)
  --allowed-cidr CIDR     Comma-separated CIDR(s) allowed to call the Lambda (default: 34.214.132.110/32)

Examples:
  $0
  $0 --api-key my-secret-key
  $0 my-deploy-bucket
  $0 my-deploy-bucket --stack-name prod-eliza
  $0 my-deploy-bucket --stack-name dev-eliza --api-key my-secret-key
  $0 my-deploy-bucket --log-requests
EOF
}

# Parse arguments - first positional arg (if not a flag) is bucket
if [ $# -gt 0 ] && [[ "$1" != --* ]]; then
  S3_BUCKET=$1
  shift
fi

# Parse remaining options
while [ $# -gt 0 ]; do
  case "$1" in
    --stack-name)
      STACK_NAME="$2"
      shift 2
      ;;
    --api-key)
      API_KEY_PLAIN="$2"
      shift 2
      ;;
    --api-key-ssm)
      API_KEY_SSM="$2"
      shift 2
      ;;
    --api-key-secret)
      API_KEY_SECRET="$2"
      shift 2
      ;;
    --allowed-cidr)
      ALLOWED_CALLER_CIDR="$2"
      shift 2
      ;;
    --log-requests)
      LOG_REQUESTS="true"
      shift
      ;;
    -h|--help)
      show_usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      show_usage
      exit 1
      ;;
  esac
done

# If bucket not specified, use a safe project-specific default (timestamp + random suffix)
if [ -z "$S3_BUCKET" ]; then
  suffix_ts=$(date +%s)
  suffix_rand=$(openssl rand -hex 3 2>/dev/null || echo "$(date +%N | sha1sum | cut -c1-6)")
  # Use a stable, project-specific default bucket name so repeated deploys reuse the same bucket.
  S3_BUCKET="eliza-gpt-deploy"
  echo "No S3 bucket provided. Using default bucket: $S3_BUCKET"
  echo "Note: this bucket name is global. If it already exists in another account/region you may need to provide a unique bucket name using the first positional argument."
fi

# Ensure AWS CLI credentials are available and valid
if ! STS_ID=$(aws sts get-caller-identity --query Arn --output text 2>/dev/null); then
  echo "ERROR: AWS credentials not found or invalid. Please configure AWS CLI credentials before running this script." >&2
  exit 2
fi
echo "Deploying as: $STS_ID"

# If bucket doesn't exist, create it (so this script can run from a fresh account)
echo "Checking S3 bucket: $S3_BUCKET"
if ! aws s3api head-bucket --bucket "$S3_BUCKET" 2>/dev/null; then
  echo "S3 bucket $S3_BUCKET does not exist. Creating..."
  # Try to infer region
  REGION=$(aws configure get region || true)
  if [ -z "$REGION" ]; then
    REGION=us-east-1
  fi
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$S3_BUCKET" || { echo "Failed to create bucket in us-east-1" >&2; exit 3; }
  else
    aws s3api create-bucket --bucket "$S3_BUCKET" --create-bucket-configuration LocationConstraint=$REGION || { echo "Failed to create bucket in $REGION" >&2; exit 3; }
  fi
  # Enable versioning to support deterministic deploys
  echo "Enabling versioning on bucket $S3_BUCKET"
  aws s3api put-bucket-versioning --bucket "$S3_BUCKET" --versioning-configuration Status=Enabled || true
else
  echo "S3 bucket $S3_BUCKET exists."
fi

echo "Creating package zip (includes lambda/ and Eliza-GPT/src/eliza_gpt)..."
rm -f "$ZIP_PATH"
tmpdir=$(mktemp -d)
trap 'rm -rf "'$tmpdir'"' EXIT

# Copy lambda contents into the package root (so app.py is at ZIP root)
mkdir -p "$tmpdir"
cp -r ${LAMBDA_DIR}/* "$tmpdir/"

# Include Eliza-GPT source if present
if [ -d "Eliza-GPT/src/eliza_gpt" ]; then
  mkdir -p "$tmpdir/eliza_gpt"
  cp -r Eliza-GPT/src/eliza_gpt "$tmpdir/eliza_gpt/"
fi

(
  cd "$tmpdir" && zip -r "$ZIP_PATH" .
)

# Use a unique key per deploy so CFN reliably detects changes
KEY="eliza_lambda_package-$(date +%s).zip"
echo "Uploading to s3://$S3_BUCKET/$KEY"
aws s3 cp "$ZIP_PATH" "s3://$S3_BUCKET/$KEY"

echo "Packaging and deploying CloudFormation stack ($STACK_NAME)"
aws cloudformation package --template-file "$TEMPLATE_FILE" --s3-bucket "$S3_BUCKET" --output-template-file packaged-template.yaml
# Build parameter overrides as an array to avoid word-splitting/quoting issues
PARAM_OVERRIDES=("LambdaS3Bucket=$S3_BUCKET" "LambdaS3Key=$KEY" "RequireApiKey=$( [ -n \"$API_KEY_PLAIN\" -o -n \"$API_KEY_SSM\" -o -n \"$API_KEY_SECRET\" ] && echo true || echo false )" "LogRequests=$LOG_REQUESTS")
# Include AllowedCallerCIDR parameter so deployments set the env var / WAF IPSet
PARAM_OVERRIDES+=("AllowedCallerCIDR=$ALLOWED_CALLER_CIDR")
if [ -n "$API_KEY_PLAIN" ]; then
  # Create a Secrets Manager secret for the plain key to avoid storing plaintext in CFN
  secret_name="eliza/api_key/$STACK_NAME-$(date +%s)"
  echo "Creating Secrets Manager secret $secret_name"
  create_out=$(aws secretsmanager create-secret --name "$secret_name" --secret-string "{\"api_key\": \"$API_KEY_PLAIN\"}" --query ARN --output text)
  PARAM_OVERRIDES+=("ApiKeySecretId=$create_out")
fi
if [ -n "$API_KEY_SSM" ]; then
  PARAM_OVERRIDES+=("ApiKeySSMParameterName=$API_KEY_SSM")
fi
if [ -n "$API_KEY_SECRET" ]; then
  PARAM_OVERRIDES+=("ApiKeySecretId=$API_KEY_SECRET")
fi

aws cloudformation deploy --template-file packaged-template.yaml --stack-name "$STACK_NAME" --capabilities CAPABILITY_NAMED_IAM --parameter-overrides "${PARAM_OVERRIDES[@]}"

echo "Fetching stack outputs to write litellm config..."
API_URL=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text)
if [ -z "$API_URL" ] || [ "$API_URL" = "None" ]; then
  echo "Warning: could not find ApiUrl stack output. Check CloudFormation outputs." >&2
else
  cat > litellm_config.yaml <<EOF
model_list:
  - model_name: eliza-lambda
    litellm_params:
      model: openai/eliza-lambda
      api_base: ${API_URL%/}/v1/
      api_key: "${API_KEY_PLAIN}"
      supports_system_message: False

general_settings:
  pass_through_endpoints:
    - path_prefix: /eliza
      target_url: ${API_URL%/}/v1/
      headers:
        Authorization: "Bearer ${API_KEY_PLAIN}"
EOF
  echo "Wrote litellm_config.yaml"
fi

echo "Deployment complete."
