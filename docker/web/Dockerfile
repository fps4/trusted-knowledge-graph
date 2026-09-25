# The demo screen: one image, one container per person (web-mara, web-sanne, …).
# Built from web/:  docker build -f docker/web/Dockerfile web/
#
# Next.js standalone output (web/next.config.mjs): a self-contained server bundle,
# so the runtime stage carries no full node_modules. The person is chosen at run
# time (TKG_PERSONA) and the key is mounted, never built in. docs/decisions/0027.

FROM node:20-bookworm-slim AS deps
WORKDIR /web
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

FROM node:20-bookworm-slim AS build
WORKDIR /web
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /web/node_modules ./node_modules
COPY . .
RUN mkdir -p public && npm run build

FROM node:20-bookworm-slim AS runtime
WORKDIR /web
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0
COPY --from=build --chown=10001:10001 /web/.next/standalone ./
COPY --from=build --chown=10001:10001 /web/.next/static ./.next/static
COPY --from=build --chown=10001:10001 /web/public ./public
# Non-root by default. Compose runs it as the host user instead, so it can read the
# persona key that `make init` wrote 0600 — as it does for the resolver.
USER 10001
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000/').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", "server.js"]
