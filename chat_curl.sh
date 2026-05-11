#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE="${LITELLM_CONFIG_FILE:-litellm_config.yaml}"
MODEL=""
RAW_OUTPUT="false"

usage() {
  cat <<'EOF'
Usage:
  ./chat_curl.sh [options] "your message"
  echo "your message" | ./chat_curl.sh [options]

Options:
  -c, --config FILE   Path to LiteLLM config file (default: litellm_config.yaml)
  -m, --model MODEL   Model name override (default: from config, then openai/eliza-lambda)
  --raw               Print raw JSON response instead of assistant text
  -h, --help          Show this help message

Environment overrides:
  API_BASE            Override api_base from config
  API_KEY             Override api_key from config
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--config)
      CONFIG_FILE="$2"
      shift 2
      ;;
    -m|--model)
      MODEL="$2"
      shift 2
      ;;
    --raw)
      RAW_OUTPUT="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "Config file not found: $CONFIG_FILE" >&2
  exit 1
fi

extract_yaml_value() {
  local key="$1"
  local value
  value="$(sed -n "s/^[[:space:]]*${key}:[[:space:]]*//p" "$CONFIG_FILE" | head -n 1 | sed 's/^"//; s/"$//')"
  printf '%s' "$value"
}

API_BASE="${API_BASE:-$(extract_yaml_value api_base)}"
API_KEY="${API_KEY:-$(extract_yaml_value api_key)}"

if [[ -z "$MODEL" ]]; then
  MODEL="$(extract_yaml_value model)"
fi
if [[ -z "$MODEL" ]]; then
  MODEL="openai/eliza-lambda"
fi

if [[ -z "$API_BASE" || -z "$API_KEY" ]]; then
  echo "Missing API_BASE or API_KEY. Set env vars or provide them in $CONFIG_FILE." >&2
  exit 1
fi

if [[ $# -gt 0 ]]; then
  USER_MESSAGE="$*"
else
  if [[ -t 0 ]]; then
    echo "Enter a message (or pass one as an argument):" >&2
    read -r USER_MESSAGE
  else
    USER_MESSAGE="$(cat)"
  fi
fi

if [[ -z "$USER_MESSAGE" ]]; then
  echo "No message provided." >&2
  exit 1
fi

PAYLOAD="$(python3 - "$MODEL" "$USER_MESSAGE" <<'PY'
import json
import sys

model = sys.argv[1]
message = sys.argv[2]
print(json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": message}],
}))
PY
)"

RESPONSE="$(curl -sS "${API_BASE%/}/chat/completions" \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")"

if [[ "$RAW_OUTPUT" == "true" ]]; then
  printf '%s\n' "$RESPONSE"
  exit 0
fi

python3 - <<'PY' "$RESPONSE"
import json
import sys

raw = sys.argv[1]
try:
    data = json.loads(raw)
    content = data["choices"][0]["message"]["content"]
    print(content)
except Exception:
    print(raw)
PY
