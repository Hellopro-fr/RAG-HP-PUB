# Use the official Node.js 20 image.
FROM node:20

WORKDIR /usr/src/app

# Install pnpm globally
RUN npm install -g pnpm

COPY package.json pnpm-lock.yaml ./

# Install dependencies and update pnpm-lock.yaml if necessary
RUN pnpm install

# Copy local code to the container image.
COPY . .

# Build the application.
RUN pnpm run build

# Expose the port the app runs on.
EXPOSE 3000

# Run the web service on container startup.
CMD ["pnpm", "start"]