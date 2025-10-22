#!/usr/bin/env bash
# Simple deploy helper: package code into S3 and deploy CloudFormation
set -euo pipefail

S3_BUCKET=${1:-}
STACK_NAME=${2:-eliza-lambda-stack}
TEMPLATE_FILE=template.yaml
ZIP_NAME=eliza_lambda_package.zip
LAMBDA_DIR=lambda

if [ -z "$S3_BUCKET" ]; then
  echo "Usage: $0 <s3-bucket> [stack-name]"
  exit 1
fi

echo "Creating package zip..."
rm -f $ZIP_NAME
(cd $LAMBDA_DIR && zip -r ../$ZIP_NAME .)

echo "Uploading to s3://$S3_BUCKET/$ZIP_NAME"
aws s3 cp $ZIP_NAME s3://$S3_BUCKET/$ZIP_NAME

echo "Packaging and deploying CloudFormation stack ($STACK_NAME)"
aws cloudformation package --template-file $TEMPLATE_FILE --s3-bucket $S3_BUCKET --output-template-file packaged-template.yaml
aws cloudformation deploy --template-file packaged-template.yaml --stack-name $STACK_NAME --capabilities CAPABILITY_NAMED_IAM --parameter-overrides LambdaS3Bucket=$S3_BUCKET

echo "Deployment complete."
