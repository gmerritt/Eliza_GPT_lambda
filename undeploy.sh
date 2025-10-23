#!/usr/bin/env bash
# Delete the CloudFormation stack and optionally remove uploaded S3 objects.
set -euo pipefail

S3_BUCKET=""
STACK_NAME="eliza-lambda-stack"

show_usage() {
  cat <<EOF
Usage: $0 <s3-bucket> [options]

Required:
  s3-bucket               S3 bucket used for deployment artifacts

Options:
  --stack-name NAME       CloudFormation stack name (default: eliza-lambda-stack)

Examples:
  $0 my-deploy-bucket
  $0 my-deploy-bucket --stack-name prod-eliza
EOF
}

if [ $# -eq 0 ]; then
  show_usage
  exit 1
fi

S3_BUCKET=$1
shift

# Parse remaining options
while [ $# -gt 0 ]; do
  case "$1" in
    --stack-name)
      STACK_NAME="$2"
      shift 2
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

if [ -z "$S3_BUCKET" ]; then
  echo "ERROR: s3-bucket is required" >&2
  show_usage
  exit 1
fi

# Try to get the list of keys we created (prefix eliza_lambda_package-*) and delete them
echo "Deleting CloudFormation stack $STACK_NAME"
aws cloudformation delete-stack --stack-name $STACK_NAME
aws cloudformation wait stack-delete-complete --stack-name $STACK_NAME

echo "Removing deployment zips from s3://$S3_BUCKET with prefix eliza_lambda_package-"
keys=$(aws s3api list-objects-v2 --bucket $S3_BUCKET --prefix eliza_lambda_package- --query 'Contents[].Key' --output text || true)
if [ -n "$keys" ]; then
  for k in $keys; do
    echo "Deleting s3://$S3_BUCKET/$k"
    aws s3 rm s3://$S3_BUCKET/$k || true
  done
else
  echo "No matching keys found."
fi

echo "Deleting Secrets Manager secrets created by this deployer (prefix eliza/api_key/$STACK_NAME-)"
secret_arns=$(aws secretsmanager list-secrets --query "SecretList[?starts_with(Name, 'eliza/api_key/$STACK_NAME')].ARN" --output text 2>/dev/null || true)
if [ -n "$secret_arns" ]; then
  for arn in $secret_arns; do
    echo "Deleting secret $arn"
    aws secretsmanager delete-secret --secret-id $arn --force-delete-without-recovery || true
  done
else
  echo "No matching secrets found."
fi

echo "Undeploy complete."
