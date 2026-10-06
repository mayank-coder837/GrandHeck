# Optional container build. The primary way to run the demo is `python run.py`.
# Stage 1: build the React dashboard.
FROM node:22-alpine AS dashboard
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: the site gateway (FastAPI) serving the built dashboard. No internet needed at runtime.
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=dashboard /app/frontend/dist frontend/dist
WORKDIR /app/backend
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "grandheck.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
