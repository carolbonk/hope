# Hope web app in offline demo mode, for the Hugging Face Space (see infra/hf-space/README.md).
FROM node:22-slim
RUN corepack enable
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0 NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_HOPE_DEMO=1 NEXT_PUBLIC_HOPE_API_URL= PORT=7860
WORKDIR /app
RUN chown node:node /app
COPY --chown=node:node . .
USER node
RUN pnpm install --frozen-lockfile && pnpm --filter @hope/web build
EXPOSE 7860
CMD ["pnpm", "--filter", "@hope/web", "start"]
