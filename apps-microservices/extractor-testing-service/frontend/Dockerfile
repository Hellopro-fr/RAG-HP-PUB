# Stage 1: Build the Next.js application
FROM node:20-slim AS builder
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy package management files
COPY apps-microservices/extractor-testing-service/frontend/package.json ./
COPY apps-microservices/extractor-testing-service/frontend/pnpm-lock.yaml ./

# Install all dependencies (including devDependencies needed for the build)
RUN pnpm install

# Copy the rest of the application source code
COPY apps-microservices/extractor-testing-service/frontend/ .

# Build the application
RUN pnpm build

# Stage 2: Create the final production image
FROM node:20-slim
WORKDIR /app

# Install pnpm
RUN npm install -g pnpm

# Copy only necessary files for production
COPY apps-microservices/extractor-testing-service/frontend/package.json ./
COPY apps-microservices/extractor-testing-service/frontend/pnpm-lock.yaml ./

# Install only production dependencies
RUN pnpm install --prod

# Copy the built application from the builder stage
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./

# Expose the port the app will run on
EXPOSE 3030

# The command to start the production server
CMD ["pnpm", "start"]