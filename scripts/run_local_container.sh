#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
IMAGE_NAME="${IMAGE_NAME:-traq-server:local}"
PORT="${PORT:-8000}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}" >&2
  exit 1
fi

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line//[[:space:]]/}" ]] && continue
  [[ "${line}" =~ ^[[:space:]]*# ]] && continue
  if [[ "${line}" != *=* ]]; then
    continue
  fi
  key="${line%%=*}"
  value="${line#*=}"
  key="${key#"${key%%[![:space:]]*}"}"
  key="${key%"${key##*[![:space:]]}"}"
  export "${key}=${value}"
done < "${ENV_FILE}"

if [[ -z "${TRAQ_DATABASE_URL:-}" ]]; then
  echo "TRAQ_DATABASE_URL is required in .env" >&2
  exit 1
fi

if [[ -z "${TRAQ_API_KEY:-}" ]]; then
  echo "TRAQ_API_KEY is required in .env" >&2
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" || "${OPENAI_API_KEY}" == "replace-me" ]]; then
  echo "OPENAI_API_KEY must be set to a real key in .env" >&2
  exit 1
fi

TRAE_BACKEND="${TRAQ_ARTIFACT_BACKEND:-local}"
TRAE_STORAGE_ROOT="${TRAQ_STORAGE_ROOT:-${ROOT_DIR}/local_data}"

exec sudo docker run --rm --network host \
  -e TRAQ_DATABASE_URL="${TRAQ_DATABASE_URL}" \
  -e TRAQ_API_KEY="${TRAQ_API_KEY}" \
  -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
  -e TRAQ_ARTIFACT_BACKEND="${TRAE_BACKEND}" \
  -e TRAQ_STORAGE_ROOT="${TRAE_STORAGE_ROOT}" \
  -e PORT="${PORT}" \
  "${IMAGE_NAME}"
