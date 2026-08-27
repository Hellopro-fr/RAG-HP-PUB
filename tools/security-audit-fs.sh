#!/usr/bin/env bash
#
# security-audit-fs.sh
#
# Audit sécurité filesystem (SANS build) de tous les services + libs du repo :
#   - CVE dépendances (Trivy fs --scanners vuln)   <- ce que audit-dockerfiles-global.sh RATAIT
#   - Secrets embarqués (Trivy fs --scanners secret)
#   - Misconfig Dockerfile / IaC (Trivy fs --scanners misconfig)
#
# Track A passe 1 de l'Audit Sécurité Pré-Cutover (ASPC), ticket 001-INFRA-GCP-ARCHI.
# Conçu pour tourner EN CI (runner ubuntu, Trivy CLI) ET en local. Aucun build d'image.
#
# Usage :
#   bash tools/security-audit-fs.sh
#
# Variables d'environnement :
#   TRIVY_BIN      chemin du binaire trivy (défaut : trivy dans le PATH)
#   OUTPUT_DIR     dossier de sortie (défaut : <repo>/docs/audit/pre-cutover)
#   SEVERITY       sévérités scannées (défaut : HIGH,CRITICAL)
#   TIMEOUT        timeout par scan en secondes (défaut : 180)
#   PROD_LIST      fichier optionnel : 1 nom de service par ligne = destiné à prod (priorisation)
#
# Pré-requis : trivy CLI, jq

set -euo pipefail

# --- Config ----------------------------------------------------------------
readonly REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
readonly APPS_DIR="${REPO_ROOT}/apps-microservices"
readonly LIBS_DIR="${REPO_ROOT}/libs"
readonly TRIVY_BIN="${TRIVY_BIN:-trivy}"
readonly OUTPUT_DIR="${OUTPUT_DIR:-${REPO_ROOT}/docs/audit/pre-cutover}"
readonly RAW_DIR="${OUTPUT_DIR}/raw"
readonly SYNTHESE_MD="${OUTPUT_DIR}/synthese.md"
readonly SYNTHESE_CSV="${OUTPUT_DIR}/synthese.csv"
readonly SEVERITY="${SEVERITY:-HIGH,CRITICAL}"
readonly TIMEOUT="${TIMEOUT:-180}"
readonly PROD_LIST="${PROD_LIST:-}"

# --- Logging ---------------------------------------------------------------
log_info()  { echo "[INFO]  $(date '+%Y-%m-%d %H:%M:%S') $*"; }
log_warn()  { echo "[WARN]  $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }
log_error() { echo "[ERROR] $(date '+%Y-%m-%d %H:%M:%S') $*" >&2; }

# --- Prerequisites ---------------------------------------------------------
check_prerequisites() {
  command -v "${TRIVY_BIN}" >/dev/null 2>&1 || { log_error "trivy not found (TRIVY_BIN=${TRIVY_BIN})"; exit 1; }
  command -v jq >/dev/null 2>&1 || { log_error "jq not found"; exit 1; }
  [ -d "${APPS_DIR}" ] || { log_error "apps-microservices/ introuvable à ${APPS_DIR}"; exit 1; }
}

# --- Est-ce un service destiné à prod ? ------------------------------------
is_prod_service() {
  local name="$1"
  [ -n "${PROD_LIST}" ] && [ -f "${PROD_LIST}" ] || { echo "?"; return; }
  if grep -qxF "${name}" "${PROD_LIST}" 2>/dev/null; then echo "PROD"; else echo "vm"; fi
}

# --- Scan d'une unité (service ou lib) -------------------------------------
scan_unit() {
  local unit_dir="$1"
  local unit_name
  unit_name="$(basename "${unit_dir}")"
  local json_out="${RAW_DIR}/${unit_name}.json"

  # Trivy fs : vuln (CVE deps) + secret + misconfig
  if ! "${TRIVY_BIN}" fs \
        --scanners vuln,secret,misconfig \
        --severity "${SEVERITY}" \
        --format json \
        --timeout "${TIMEOUT}s" \
        --no-progress \
        --output "${json_out}" \
        "${unit_dir}" 2>/dev/null; then
    log_warn "Trivy scan partiel/échec pour ${unit_name}"
    [ -f "${json_out}" ] || echo '{"Results":[]}' > "${json_out}"
  fi

  # Counts
  local crit high secrets misconfig
  crit=$(jq '[.Results[]?.Vulnerabilities[]?      | select(.Severity=="CRITICAL")] as $v
            | [.Results[]?.Secrets[]?             | select(.Severity=="CRITICAL")] as $s
            | [.Results[]?.Misconfigurations[]?   | select(.Severity=="CRITICAL")] as $m
            | ($v|length)+($s|length)+($m|length)' "${json_out}" 2>/dev/null || echo 0)
  high=$(jq '[.Results[]?.Vulnerabilities[]?      | select(.Severity=="HIGH")] as $v
            | [.Results[]?.Secrets[]?             | select(.Severity=="HIGH")] as $s
            | [.Results[]?.Misconfigurations[]?   | select(.Severity=="HIGH")] as $m
            | ($v|length)+($s|length)+($m|length)' "${json_out}" 2>/dev/null || echo 0)
  secrets=$(jq   '[.Results[]?.Secrets[]?]           | length' "${json_out}" 2>/dev/null || echo 0)
  misconfig=$(jq '[.Results[]?.Misconfigurations[]?] | length' "${json_out}" 2>/dev/null || echo 0)

  local scope
  scope="$(is_prod_service "${unit_name}")"

  echo "${unit_name},${scope},${crit},${high},${secrets},${misconfig}" >> "${SYNTHESE_CSV}"

  if [ "${crit}" -gt 0 ] || [ "${secrets}" -gt 0 ]; then
    echo "  ⛔ ${unit_name} [${scope}] : CRITICAL=${crit}, secrets=${secrets}"
  elif [ "${high}" -gt 0 ]; then
    echo "  ⚠️  ${unit_name} [${scope}] : HIGH=${high}"
  else
    echo "  ✅ ${unit_name} [${scope}]"
  fi
}

# --- Synthèse globale ------------------------------------------------------
generate_synthese() {
  log_info "Génération de la synthèse..."
  local total
  total=$(( $(wc -l < "${SYNTHESE_CSV}") - 1 ))

  cat > "${SYNTHESE_MD}" <<EOF
# Synthèse — Audit Sécurité Pré-Cutover (fs) — Track A passe 1

> Généré par \`tools/security-audit-fs.sh\` — Trivy \`fs\` (scanners : vuln, secret, misconfig), sévérités ${SEVERITY}.
> Portée : \`apps-microservices/*\` + \`libs/*\`. Colonne **Scope** : PROD = destiné à Cloud Run/GKE, vm = reste sur VM, ? = liste prod absente.
> Détails bruts : \`raw/<unit>.json\`. Cutover : voir \`audit-securite-pre-cutover.md\`.

## 1. Vue d'ensemble

| Métrique | Valeur |
|---|---|
| Unités scannées | ${total} |
| Avec CRITICAL ou secrets | $(awk -F, 'NR>1 && ($3>0 || $5>0){n++} END{print n+0}' "${SYNTHESE_CSV}") |
| Avec HIGH seul | $(awk -F, 'NR>1 && $3==0 && $5==0 && $4>0{n++} END{print n+0}' "${SYNTHESE_CSV}") |
| Clean (0 finding ${SEVERITY}) | $(awk -F, 'NR>1 && $3==0 && $4==0 && $5==0 && $6==0{n++} END{print n+0}' "${SYNTHESE_CSV}") |

### Findings agrégés

| Type | Total | Dont PROD |
|---|---|---|
| CRITICAL | $(awk -F, 'NR>1{s+=$3} END{print s+0}' "${SYNTHESE_CSV}") | $(awk -F, 'NR>1 && $2=="PROD"{s+=$3} END{print s+0}' "${SYNTHESE_CSV}") |
| HIGH | $(awk -F, 'NR>1{s+=$4} END{print s+0}' "${SYNTHESE_CSV}") | $(awk -F, 'NR>1 && $2=="PROD"{s+=$4} END{print s+0}' "${SYNTHESE_CSV}") |
| Secrets | $(awk -F, 'NR>1{s+=$5} END{print s+0}' "${SYNTHESE_CSV}") | $(awk -F, 'NR>1 && $2=="PROD"{s+=$5} END{print s+0}' "${SYNTHESE_CSV}") |
| Misconfig | $(awk -F, 'NR>1{s+=$6} END{print s+0}' "${SYNTHESE_CSV}") | $(awk -F, 'NR>1 && $2=="PROD"{s+=$6} END{print s+0}' "${SYNTHESE_CSV}") |

## 2. PRIORITÉ — CRITICAL ou secrets (bloquant cutover)

| Unité | Scope | CRIT | HIGH | Secrets | Misconfig |
|---|---|---|---|---|---|
EOF
  # PROD d'abord, puis tri par CRITICAL puis secrets décroissant
  awk -F, 'NR>1 && ($3>0 || $5>0){printf "| %s | %s | %s | %s | %s | %s |\n",$1,$2,$3,$4,$5,$6}' "${SYNTHESE_CSV}" \
    | sort -t'|' -k3,3r -k4,4nr -k6,6nr >> "${SYNTHESE_MD}"

  cat >> "${SYNTHESE_MD}" <<EOF

## 3. HIGH uniquement (plan sous 7-30 j)

| Unité | Scope | HIGH | Misconfig |
|---|---|---|---|
EOF
  awk -F, 'NR>1 && $3==0 && $5==0 && $4>0{printf "| %s | %s | %s | %s |\n",$1,$2,$4,$6}' "${SYNTHESE_CSV}" \
    | sort -t'|' -k4,4nr >> "${SYNTHESE_MD}"

  cat >> "${SYNTHESE_MD}" <<EOF

## 4. Clean (0 finding ${SEVERITY})

EOF
  awk -F, 'NR>1 && $3==0 && $4==0 && $5==0 && $6==0{print "- "$1" ["$2"]"}' "${SYNTHESE_CSV}" >> "${SYNTHESE_MD}"

  cat >> "${SYNTHESE_MD}" <<'EOF'

## 5. Plan d'action

1. **P1 (immédiat, bloquant)** — secrets embarqués → rotation creds + purge git + `.dockerignore` + Secret Manager.
2. **P2 (avant cutover)** — CRITICAL sur services PROD → bump base image / bump dépendance.
3. **P3 (7-30 j)** — HIGH → bump au prochain build.
4. **P4 (continu)** — appliquer `.claude/rules/docker-security.md` à tout nouveau service.

> Rappel findings déjà ouverts : F-HP-SEC-011 (grpc), F-HP-SEC-012 (next), F-HP-SEC-013 (clé GCP SA en clair).
EOF
  log_info "Synthèse : ${SYNTHESE_MD}"
}

# --- Main ------------------------------------------------------------------
main() {
  check_prerequisites
  mkdir -p "${RAW_DIR}"
  echo "unit,scope,critical,high,secrets,misconfig" > "${SYNTHESE_CSV}"

  local units=()
  while IFS= read -r dockerfile; do
    units+=("$(dirname "${dockerfile}")")
  done < <(find "${APPS_DIR}" -mindepth 2 -maxdepth 2 -name Dockerfile -type f 2>/dev/null | sort)
  # libs (deps partagées) scannées comme unités à part
  if [ -d "${LIBS_DIR}" ]; then
    while IFS= read -r libdir; do units+=("${libdir}"); done \
      < <(find "${LIBS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort)
  fi

  local total="${#units[@]}"
  log_info "Unités à scanner : ${total} (Trivy=${TRIVY_BIN}, sévérités=${SEVERITY})"
  [ "${total}" -gt 0 ] || { log_error "Aucune unité trouvée"; exit 1; }

  local i=0
  for u in "${units[@]}"; do
    i=$((i+1))
    echo "===== [${i}/${total}] $(basename "${u}") ====="
    scan_unit "${u}" || log_warn "scan_unit KO pour ${u}"
  done

  echo ""
  generate_synthese
  log_info "Audit fs terminé → ${OUTPUT_DIR}"
}

main "$@"
