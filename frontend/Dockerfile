# node:23-slim (Debian-based) matches the system Node v23.10.0 this project
# was built against. Not alpine: this app depends on @tailwindcss/postcss
# (Tailwind v4's PostCSS engine), which resolves a platform-specific native
# binary via optionalDependencies -- slim/glibc is the safer, more widely
# supported target for that than musl/alpine.

# ---- build stage --------------------------------------------------------
FROM node:23-slim AS builder
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# `frontend/lib/api-client.ts` reads `process.env.NEXT_PUBLIC_API_URL` and is
# imported only from "use client" components/pages, so Next.js inlines its
# value into the browser bundle at BUILD time (next build), not read again at
# container start. It must therefore be set here, as a build arg threaded
# through docker-compose.yml's `build.args`, and it must be a URL the
# browser -- not the Compose network -- can reach (see docker-compose.yml
# and docs/docker.md for the full reasoning).
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

# ---- runtime stage -------------------------------------------------------
# next.config.ts has no `output: "standalone"`, so `next start` needs the
# full production node_modules (next/react/react-dom), the build output
# (.next), the public/ assets, and the config file itself. A fresh
# `npm ci --omit=dev` here (rather than copying node_modules from the build
# stage) keeps the runtime image free of devDependencies (typescript,
# tailwindcss, eslint, ...) used only to build.
FROM node:23-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./next.config.ts

# `next start` reads the `PORT` env var (commander `.env('PORT')` on the
# `-p/--port` option) when no `-p` flag is given, and binds hostname 0.0.0.0
# by default -- so docker-compose.yml sets PORT=${FRONTEND_PORT} rather than
# this Dockerfile hardcoding a port.
EXPOSE 3000
CMD ["npm", "start"]
