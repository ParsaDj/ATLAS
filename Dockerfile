FROM node:22-slim AS dashboard
WORKDIR /build
RUN npm install --global pnpm@11.25.0
COPY apps/dashboard/package.json apps/dashboard/pnpm-lock.yaml apps/dashboard/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/dashboard/ ./
RUN pnpm build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY apps/api apps/api
COPY apps/ai_agent apps/ai_agent
COPY apps/__init__.py apps/__init__.py
COPY alembic.ini alembic.ini
COPY migrations migrations
COPY --from=dashboard /build/dist apps/dashboard/dist
COPY simulator simulator
COPY scripts scripts
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"]
