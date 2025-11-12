# Stage 1: Install dependencies
FROM node:20-alpine AS deps
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy dependency manifests
COPY package.json pnpm-lock.yaml ./

# Fetch all dependencies into a shared cache
# This layer is cached and will only be re-run if manifests change
RUN pnpm fetch

# Stage 2: Build the application
FROM node:20-alpine AS builder
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy dependency manifests and the pnpm store cache from the previous stage
COPY package.json pnpm-lock.yaml ./
COPY --from=deps /root/.local/share/pnpm/store /root/.local/share/pnpm/store

# Install dependencies using the cache
RUN pnpm install

# Copy the rest of the application source code
COPY . .

# Set build-time environment variables if needed
# ARG NEXT_PUBLIC_SOME_VAR
# ENV NEXT_PUBLIC_SOME_VAR=$NEXT_PUBLIC_SOME_VAR

# Build the Next.js application
RUN pnpm build

# Stage 3: Production runner
FROM node:20-alpine AS runner
WORKDIR /app

# Create a non-root user for security
RUN addgroup --system --gid 1001 nextjs
RUN adduser --system --uid 1001 nextjs

# Copy production artifacts from the builder stage
# The `standalone` output mode bundles only what's necessary to run
COPY --from=builder --chown=nextjs:nextjs /app/public ./public
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

# Set the user to the non-root user
USER nextjs

# Expose the port the app runs on
EXPOSE 3000

# Set the default port for Next.js
ENV PORT 3000
# Set NODE_ENV to production
ENV NODE_ENV production

# Command to start the application
CMD ["node", "server.js"]