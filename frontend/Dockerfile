# syntax=docker/dockerfile:1

# Adjust this if your Angular project name (in angular.json) is different
ARG APP_NAME=team-invincible

##############################
# 1. Build stage
##############################
FROM node:20-alpine AS builder

# Create app directory
WORKDIR /app

# Install dependencies (uses package.json / package-lock.json)
COPY package*.json ./
RUN npm ci

# Copy the rest of the source code
COPY . .

# Build Angular app in production mode
RUN npm run build -- --configuration=production

##############################
# 2. Runtime stage
##############################
# 2. Runtime stage
FROM nginx:stable-alpine AS runner

RUN rm -rf /usr/share/nginx/html/*

# pick the first dist/*/browser (Angular 17+ default)
COPY --from=builder /app/dist/*/browser/ /usr/share/nginx/html/

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

