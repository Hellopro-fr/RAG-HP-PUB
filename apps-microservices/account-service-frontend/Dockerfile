# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
RUN rm -rf /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /src/dist /usr/share/nginx/html
RUN printf 'proxy_http_version 1.1;\nproxy_set_header Host $host;\nproxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\nproxy_set_header X-Forwarded-Proto $scheme;\nproxy_set_header X-Real-IP $remote_addr;\nproxy_read_timeout 30s;\n' > /etc/nginx/proxy.inc
EXPOSE 8601
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://localhost:8601/ >/dev/null || exit 1
