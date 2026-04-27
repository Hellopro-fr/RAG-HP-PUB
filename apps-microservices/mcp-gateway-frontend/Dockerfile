# Stage 1: Build
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve
FROM nginx:1.27-alpine
RUN addgroup -g 1001 -S appgroup && adduser -u 1001 -S appuser -G appgroup
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx-limits.conf /etc/nginx/conf.d/00-limits.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN chown -R appuser:appgroup /var/cache/nginx /var/log/nginx /usr/share/nginx/html \
    && touch /var/run/nginx.pid && chown appuser:appgroup /var/run/nginx.pid
USER appuser
EXPOSE 8581
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8581/ || exit 1
CMD ["nginx", "-g", "daemon off;"]
