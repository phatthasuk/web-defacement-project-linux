# Stage 1: Build the frontend application
FROM node:20-slim AS builder

WORKDIR /app

COPY package*.json ./
# Vitest's Vite peer range currently resolves to a nested Vite 8, whose optional
# esbuild peer is not recorded by the repository's lockfile. Keep the Docker
# install deterministic while using the exact locked dependency tree.
RUN npm ci --legacy-peer-deps

COPY . .
RUN npm run build

# Stage 2: Serve static files with Nginx
FROM nginxinc/nginx-unprivileged:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 8080 8443

CMD ["nginx", "-g", "daemon off;"]
