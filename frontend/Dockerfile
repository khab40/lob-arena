# syntax=docker/dockerfile:1

FROM node:24-slim AS build

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

COPY . .
RUN pnpm run build

FROM nginx:alpine

ENV NGINX_ENVSUBST_TEMPLATE_DIR=/etc/nginx/templates \
    NGINX_ENVSUBST_TEMPLATE_SUFFIX=.template \
    NGINX_ENVSUBST_OUTPUT_DIR=/dist

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY runtime-config.js.template /etc/nginx/templates/runtime-config.js.template
COPY --from=build /app/dist /dist

EXPOSE 5173
