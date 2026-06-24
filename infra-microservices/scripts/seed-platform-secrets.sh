#!/usr/bin/env bash
set -euo pipefail
# set -e : exit on error | set -u : undefined vars = error | pipefail : catch piped errors

# Description : Alimente les secrets platform-* de GCP Secret Manager depuis un fichier .env.
#               Lit les valeurs localement, pousse une nouvelle version par secret.
#               NE contient AUCUNE valeur en dur. NE touche PAS la VM.
# Usage       : ./seed-platform-secrets.sh /chemin/vers/.env [--dry-run]
# Pre-requis  : gcloud authentifie (impersonation devops-infra-sa, role secretmanager.admin)

readonly PROJECT="hellopro-rag-project"
readonly ENV_FILE="${1:?Usage: $0 <chemin .env> [--dry-run]}"
readonly DRY_RUN="${2:-}"

# Mapping : ENV_VAR -> platform-secret-id (secrets partages par >=2 services)
declare -A MAP=(
  [JWT_SECRET]=platform-jwt-secret
  [ACCOUNT_INTERNAL_TOKEN]=platform-account-internal-token
  [CATALOG_ADMIN_KEY]=platform-catalog-admin-key
  [GATEWAY_ADMIN_KEY]=platform-gateway-admin-key
  [MCP_ENCRYPTION_KEY]=platform-mcp-encryption-key
  [MCP_FALLBACK_PASS]=platform-mcp-fallback-pass
  # NB platform-gateway-mysql-pass : alimente HORS .env par copie depuis
  #    account-service-backend-mysql-pass (GATEWAY_MYSQL_PASS absent du .env,
  #    valeur reelle = defaut docker-compose 'gateway_pass'). Cf. seed manuel.
  [MYSQL_ROOT_PASSWORD]=platform-gateway-mysql-root-pass
  [REDIS_SECRET]=platform-redis-secret
  [RABBITMQ_URL]=platform-rabbitmq-url
  [NEO4J_PASSWORD]=platform-neo4j-password
  # Zilliz : auth user+password (ZILLIZ_API_KEY=none, non utilise)
  [ZILLIZ_USER]=platform-zilliz-user
  [ZILLIZ_PASSWORD]=platform-zilliz-password
  [OPENAI_API_KEY]=platform-openai-api-key
  [GEMINI_API_KEY]=platform-gemini-api-key
  [DEEPSEEK_API_KEY]=platform-deepseek-api-key
  [OPENROUTER_API_KEY]=platform-openrouter-api-key
  [EMBEDDING_API_KEY]=platform-embedding-api-key
  [HP_TOKEN]=platform-hp-token
  [HELLOPRO_API_BEARER_TOKEN]=platform-hellopro-api-bearer-token
  [SLACK_WEBHOOK_URL]=platform-slack-webhook-url
  [MCP_RINGOVER_ADMIN_TOKEN]=platform-mcp-ringover-admin-token
  [MCP_LEEXI_ADMIN_TOKEN]=platform-mcp-leexi-admin-token
  [GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN]=platform-mcp-templates-runner-admin-token
  [ZOHO_GATEWAY_TOKEN]=platform-zoho-gateway-token
)

log_info()  { echo "[INFO]  $*"; }
log_ok()    { echo "[OK]    $*"; }
log_skip()  { echo "[SKIP]  $*"; }
log_fail()  { echo "[FAIL]  $*" >&2; }

command -v gcloud >/dev/null 2>&1 || { log_fail "gcloud introuvable"; exit 1; }
[ -f "${ENV_FILE}" ] || { log_fail "Fichier .env introuvable: ${ENV_FILE}"; exit 1; }

# Extrait la valeur d'une cle dans le .env :
#  - derniere occurrence non commentee (le .env a des doublons commentes)
#  - split sur le PREMIER '=' (valeurs peuvent contenir '=' : URLs, base64)
#  - retire les guillemets entourants eventuels
get_env_value() {
  local key="$1"
  grep -E "^[[:space:]]*${key}=" "${ENV_FILE}" 2>/dev/null \
    | grep -vE "^[[:space:]]*#" \
    | tail -1 \
    | sed -E "s/^[[:space:]]*${key}=//" \
    | sed -E 's/^"(.*)"$/\1/' \
    | sed -E "s/^'(.*)'\$/\1/"
}

log_info "Projet      : ${PROJECT}"
log_info "Fichier .env: ${ENV_FILE}"
log_info "Mode        : ${DRY_RUN:-APPLY}"
log_info "Secrets     : ${#MAP[@]}"
echo "---"

ok=0; skip=0; fail=0
for env_var in "${!MAP[@]}"; do
  secret="${MAP[$env_var]}"
  value="$(get_env_value "${env_var}")"

  if [ -z "${value}" ]; then
    log_skip "${env_var} vide/absent dans .env  ->  ${secret}"
    skip=$((skip+1))
    continue
  fi

  if [ "${DRY_RUN}" = "--dry-run" ]; then
    # N'affiche PAS la valeur (juste sa longueur) pour ne pas exposer le secret
    log_info "DRY-RUN ${env_var} (len=${#value})  ->  ${secret}"
    ok=$((ok+1))
    continue
  fi

  # --data-file=- via printf : pas de valeur en argument CLI (invisible dans 'ps'),
  # pas de fichier temporaire (rien a nettoyer).
  if printf '%s' "${value}" | gcloud secrets versions add "${secret}" \
        --data-file=- --project="${PROJECT}" >/dev/null 2>&1; then
    log_ok "${env_var}  ->  ${secret}"
    ok=$((ok+1))
  else
    log_fail "${env_var}  ->  ${secret} (echec gcloud)"
    fail=$((fail+1))
  fi
done

echo "---"
log_info "Resume : ${ok} OK / ${skip} SKIP / ${fail} FAIL (sur ${#MAP[@]})"
[ "${fail}" -eq 0 ] || exit 1
