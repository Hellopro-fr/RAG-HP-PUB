# Build context = repo root. Preserves libs/auth/node at ../../ relative to the service.
FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm

# Shared lib (the file: dependency target) + the service, keeping their relative tree.
COPY libs/auth/node ./libs/auth/node
COPY apps-microservices/redis-client-frontend ./apps-microservices/redis-client-frontend

WORKDIR /app/apps-microservices/redis-client-frontend
RUN pnpm install
RUN pnpm build

# Production runner
FROM node:20-alpine AS runner
WORKDIR /app
RUN addgroup --system --gid 1001 nextjs && \
    adduser --system --uid 1001 nextjs

ENV SVC=/app/apps-microservices/redis-client-frontend
COPY --from=builder --chown=nextjs:nextjs $SVC/public ./public
COPY --from=builder --chown=nextjs:nextjs $SVC/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs $SVC/.next/static ./.next/static

USER nextjs
EXPOSE 3000
ENV PORT 3000
ENV NODE_ENV production
CMD ["node", "server.js"]
