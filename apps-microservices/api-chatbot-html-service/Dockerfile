# Use the official Node.js 20 image.
FROM node:20

# Create and change to the app directory.
WORKDIR /usr/src/app

# Copy application dependency manifests to the container image.
# A wildcard is used to ensure both package.json AND package-lock.json are copied.
# Copying this first prevents re-running npm install on every code change.
COPY package*.json ./

# Install production dependencies.
# If you are building your code for production, instead use: npm ci --omit=dev
RUN npm install --legacy-peer-deps

# Copy local code to the container image.
COPY . .

# Build the application.
RUN npm run build

# Expose the port the app runs on.
EXPOSE 3000

# Run the web service on container startup.
CMD ["npm", "start"]