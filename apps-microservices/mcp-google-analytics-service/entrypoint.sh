#!/bin/bash
set -e

# If credential type is P12, convert to JSON for ADC compatibility
if [ "${GOOGLE_CREDENTIALS_TYPE}" = "p12" ]; then
  echo "Converting P12 credentials to ADC-compatible JSON..."

  if [ -z "${GOOGLE_SERVICE_ACCOUNT_EMAIL}" ]; then
    echo "ERROR: GOOGLE_SERVICE_ACCOUNT_EMAIL is required when using P12 credentials"
    exit 1
  fi

  if [ ! -f "${GOOGLE_APPLICATION_CREDENTIALS_P12:-/secrets/gcp-credentials.p12}" ]; then
    echo "ERROR: P12 file not found at ${GOOGLE_APPLICATION_CREDENTIALS_P12:-/secrets/gcp-credentials.p12}"
    exit 1
  fi

  python3 /app/p12_to_json.py
  export GOOGLE_APPLICATION_CREDENTIALS="/tmp/gcp-credentials.json"
  echo "Converted P12 -> JSON at ${GOOGLE_APPLICATION_CREDENTIALS}"
fi

exec "$@"