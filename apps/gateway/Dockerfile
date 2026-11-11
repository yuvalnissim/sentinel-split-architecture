FROM ghcr.io/nginx/nginx-unprivileged:1.28-alpine

ENV BACKEND_URL=http://backend.invalid:80 \
    DNS_RESOLVER=10.30.0.2 \
    NGINX_ENVSUBST_FILTER="^(BACKEND_URL|DNS_RESOLVER)$"

COPY default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 8080