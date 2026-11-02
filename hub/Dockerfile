# The hub: the React app is built here and served by the stdlib Python backend. Build: hub/test.sh build
FROM oven/bun:1.4.4-alpine AS web
WORKDIR /web
COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile --silent
COPY web/ ./
# only the bundle: types, lint, format and tests already passed in `test.sh check`, which every build runs first
RUN bun --bun vite build --logLevel warn

FROM python:3.15.0-alpine
# Alpine has no zone database: without it TZ (the cluster's timezone) is ignored and every time shows as UTC.
RUN apk add --no-cache tzdata
WORKDIR /app
COPY *.py secrets-map.json ./
COPY notify/ notify/
COPY store/ store/
COPY --from=web /web/dist static/
CMD ["python3", "-I", "/app/hub.py"]
