# Build stage
FROM node:22-alpine AS build
WORKDIR /app
COPY apps-microservices/account-service-frontend/package.json ./
RUN npm install --no-audit --no-fund
COPY apps-microservices/account-service-frontend .
RUN npm run build

# Runtime stage
FROM nginx:1.27-alpine AS runtime
RUN apk add --no-cache wget
COPY --from=build /app/dist /usr/share/nginx/html
COPY apps-microservices/account-service-frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost:80/healthz || exit 1
USER nginx
