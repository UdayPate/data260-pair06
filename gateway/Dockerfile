# p06-gateway  (Pair 06, port 9060): the one address the website calls. It forwards each request
# to the service that owns that path (see nginx.conf).
# Build from the gateway/ folder:  docker build -t p06-gateway:1.0.0 .
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 9060
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:9060/health || exit 1
