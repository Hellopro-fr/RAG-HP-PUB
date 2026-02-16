FROM nginx:1.27-alpine

# Copier la configuration Nginx
COPY apps-microservices/image-cdn-service/nginx.conf /etc/nginx/nginx.conf

# Le volume /data sera monté depuis docker-compose (image_download_data)
# Structure attendue: /data/images/{domain}/produit-2|3/{shard}/{shard}/{shard}/

EXPOSE 8580

# Healthcheck intégré
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost:8580/health || exit 1
