FROM node:20-slim AS builder

WORKDIR /app

# Baked into the Next.js client bundle at build time (required for production).
# Pass via compose: build.args.NEXT_PUBLIC_API_URL / REQUIRE_API_URL.
ARG NEXT_PUBLIC_API_URL
ARG REQUIRE_API_URL=1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV REQUIRE_API_URL=${REQUIRE_API_URL}
# Do NOT set NODE_ENV=production before npm install — devDependencies
# (@tailwindcss/postcss, typescript) are required for `next build`.

COPY package*.json ./
# Fresh Linux install — never reuse host node_modules (see .dockerignore).
RUN npm ci || npm install

COPY . .
# Fail fast at image build if API URL missing in production/Docker builds.
RUN if [ -z "$NEXT_PUBLIC_API_URL" ] && [ "$REQUIRE_API_URL" = "1" ]; then \
      echo "ERROR: NEXT_PUBLIC_API_URL is required for Docker/production frontend builds" >&2; \
      exit 1; \
    fi
ENV NODE_ENV=production
RUN npm run build

FROM node:20-slim AS runner

WORKDIR /app

ARG NEXT_PUBLIC_API_URL
ARG REQUIRE_API_URL=1
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV REQUIRE_API_URL=${REQUIRE_API_URL}
ENV NODE_ENV=production

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules

EXPOSE 3000

CMD ["npm", "start"]
