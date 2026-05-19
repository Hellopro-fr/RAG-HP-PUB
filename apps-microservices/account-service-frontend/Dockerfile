# Stage 1: Build
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:1.27-alpine
RUN addgroup -g 1001 -S appgroup && adduser -u 1001 -S appuser -G appgroup
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx-limits.conf /etc/nginx/conf.d/00-limits.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN printf 'proxy_http_version 1.1;\nproxy_set_header Host $host;\nproxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\nproxy_set_header X-Forwarded-Proto $scheme;\nproxy_set_header X-Real-IP $remote_addr;\nproxy_read_timeout 30s;\n' > /etc/nginx/proxy.inc \
    && chown -R appuser:appgroup /var/cache/nginx /var/log/nginx /usr/share/nginx/html /etc/nginx/proxy.inc \
    && touch /var/run/nginx.pid && chown appuser:appgroup /var/run/nginx.pid
USER appuser
EXPOSE 8601
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8601/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
