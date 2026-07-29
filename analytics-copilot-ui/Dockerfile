# =============================================================================
# Analytics Copilot UI — Next.js 14 production image
# Build context: analytics-copilot-ui/ (this directory)
# Requires next.config.mjs: output: "standalone"
# NEXT_PUBLIC_API_URL is baked in at build time (Next.js public env rules)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: install dependencies (cached unless lockfile changes)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS deps

RUN apk add --no-cache libc6-compat

WORKDIR /app

COPY package.json package-lock.json ./

# Deterministic install from lockfile (npm is the project package manager)
RUN npm ci

# -----------------------------------------------------------------------------
# Stage 2: build Next.js (standalone output)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Client-side env vars are inlined during `next build`.
# Pass at build time: --build-arg NEXT_PUBLIC_API_URL=https://api.example.com
# Do NOT hardcode localhost in this image.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

RUN npm run build

# -----------------------------------------------------------------------------
# Stage 3: minimal runtime (standalone server only)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Standalone server bundle (includes minimal node_modules)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./

# Static assets must sit next to the standalone server
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Optional public assets (directory may be empty; created if project has no public/)
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

# standalone output entrypoint (not "npm run start")
CMD ["node", "server.js"]
