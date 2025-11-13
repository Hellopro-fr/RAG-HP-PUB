# Dockerfile for Next.js development environment
FROM node:20-slim

WORKDIR /app

# Copy package.json and lock file
COPY apps-microservices/extractor-testing-service/frontend/package.json ./

# Install pnpm and dependencies
RUN npm install -g pnpm
RUN pnpm install

# Copy the rest of the application code
COPY apps-microservices/extractor-testing-service/frontend/ .

# Expose port 3000
EXPOSE 3030

# Start the development server
CMD ["pnpm", "dev"]