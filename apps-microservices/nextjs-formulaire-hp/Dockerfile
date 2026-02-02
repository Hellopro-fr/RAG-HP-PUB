# Étape 1: Base avec Node.js
FROM node:18-alpine AS base

# Étape 2: Installation des dépendances
FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app

# Copier package.json
COPY package.json ./

# Installer les dépendances
RUN npm install

# Étape 3: Build de l'application
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# Étape 4: Image de production légère
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Créer un utilisateur non-root pour la sécurité
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copier le dossier public
COPY --from=builder /app/public ./public

# Créer le dossier .next avec les bonnes permissions
RUN mkdir .next
RUN chown nextjs:nodejs .next

# Copier le build standalone (output: 'standalone' dans next.config.js)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
