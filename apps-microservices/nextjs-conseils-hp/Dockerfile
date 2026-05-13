# Étape 1: Base Node 22 LTS
FROM node:22-alpine AS base

# Étape 2: Installation des dépendances
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY apps-microservices/nextjs-conseils-hp/package.json ./
COPY apps-microservices/nextjs-conseils-hp/package-lock.json ./
RUN npm ci

# Étape 3: Build
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps-microservices/nextjs-conseils-hp/ .
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Étape 4: Runner production
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Output standalone
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
