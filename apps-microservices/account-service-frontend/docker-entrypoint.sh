#!/bin/sh
# docker-entrypoint.sh — sélection conditionnelle de la conf Nginx selon l'environnement runtime.
#
# Mode VM Docker Compose (par défaut, IS_CLOUD_RUN unset/false) :
#   - default.conf statique copié pendant le build (le nginx.conf historique) reste actif
#   - aucun template rendu, comportement strictement inchangé vs avant cette modification
#
# Mode Cloud Run (IS_CLOUD_RUN=true) :
#   - regenère default.conf depuis nginx.conf.cloudrun.template via envsubst
#   - injection de BACKEND_HOST (hostname Cloud Run du backend, sans https://)
#
# Ticket : 001-INFRA-GCP-ARCHI Sprint S003 T001-S003-000 (F-HP-NGINX-001)

set -eu

if [ "${IS_CLOUD_RUN:-false}" = "true" ]; then
    : "${BACKEND_HOST:?BACKEND_HOST required when IS_CLOUD_RUN=true}"
    echo "[entrypoint] Cloud Run mode: rendering /etc/nginx/conf.d/default.conf from template (BACKEND_HOST=${BACKEND_HOST})"
    export BACKEND_HOST
    envsubst '${BACKEND_HOST}' < /etc/nginx/nginx.conf.cloudrun.template > /etc/nginx/conf.d/default.conf
    echo "[entrypoint] --- generated /etc/nginx/conf.d/default.conf (extrait location /api/) ---"
    grep -A 2 "location /api/" /etc/nginx/conf.d/default.conf | head -5 || true
    echo "[entrypoint] --- end extrait ---"
else
    echo "[entrypoint] VM/Docker Compose mode: using static default.conf (unchanged)"
fi

# Chain le CMD passé (par défaut : nginx -g 'daemon off;')
exec "$@"
