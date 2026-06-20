# The Canary — web UI image (Next.js).
FROM node:20-slim

WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .

# NEXT_PUBLIC_* vars are inlined at build time, so the API URL must be set here.
ARG NEXT_PUBLIC_CANARY_API=http://localhost:8000
ENV NEXT_PUBLIC_CANARY_API=$NEXT_PUBLIC_CANARY_API

RUN pnpm build

EXPOSE 3000
CMD ["pnpm", "start"]
