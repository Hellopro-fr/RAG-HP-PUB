FROM node:22-slim AS base
WORKDIR /app

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm install

# Copy source
COPY . .

# Build
RUN npm run build

# Production stage
FROM nginx:1.27-alpine AS production
COPY --from=base /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

# Development stage (default)
FROM base AS development
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
