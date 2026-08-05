FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY apps/web/package.json apps/web/pnpm-lock.yaml apps/web/pnpm-workspace.yaml ./
RUN corepack enable && corepack prepare pnpm@10.28.2 --activate \
    && pnpm install --frozen-lockfile
COPY apps/web ./
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_INITIAL_LAUNCH_MODE=true
ARG NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL
ENV NEXT_PUBLIC_INITIAL_LAUNCH_MODE=$NEXT_PUBLIC_INITIAL_LAUNCH_MODE
ENV NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=$NEXT_PUBLIC_ALLOW_MOCK_FALLBACK
RUN npm run build

FROM node:20-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next-build/standalone ./
COPY --from=build --chown=node:node /app/.next-build/static ./.next-build/static
USER node
EXPOSE 3000
HEALTHCHECK --interval=15s --timeout=15s --retries=10 CMD node -e "fetch('http://127.0.0.1:3000/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"
CMD ["node", "server.js"]
