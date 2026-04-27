FROM node:20-alpine AS build
WORKDIR /app

# node:20-alpine ships Yarn 1.22.22 but package.json pins
# "packageManager": "yarn@4.11.0" — Corepack downloads and shims the right
# version. Enabled before copying deps so yarn.lock (Berry v6 format) is read
# by Yarn 4, not Yarn 1.
RUN corepack enable

# Copy dep manifests + Yarn Berry config so corepack + yarn resolve reproducibly.
COPY package.json yarn.lock .yarnrc.yml ./

# --immutable fails the build if yarn.lock would change — catches drift in CI.
RUN yarn install --immutable

COPY . .
RUN yarn build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8099
CMD ["nginx", "-g", "daemon off;"]
