# Stage 1: build the React client into static files.
FROM node:20-alpine AS client
WORKDIR /app
COPY client/package.json client/package-lock.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# Stage 2: NGINX serves the built client, the music files and proxies the cluster.
# 1.27.3+ is needed for the `resolve` option on upstream servers.
FROM nginx:1.28-alpine
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=client /app/dist /usr/share/nginx/html
