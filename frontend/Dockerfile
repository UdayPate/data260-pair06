# p06-frontend  (Pair 06, port 9061): builds the React app, then serves the static files with nginx.
# Build from the frontend/ folder:
#   docker build -t p06-frontend:1.0.0 --build-arg VITE_API_URL=http://localhost:9060 .
# VITE_API_URL is baked into the JavaScript at build time: it must be the address the BROWSER
# uses to reach the gateway (http://localhost:9060 locally, the LoadBalancer address on AWS).

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src/ src/
ARG VITE_API_URL=http://localhost:9060
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# "unprivileged" nginx runs as a normal user, so it can use any port above 1024.
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 9061
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:9061/ || exit 1
