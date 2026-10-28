# Build context: repository root (docker build -f backend/Dockerfile .)

# ---------- build: resolve the locked pixi environment ----------
FROM ghcr.io/prefix-dev/pixi:0.63.2 AS build
WORKDIR /app
# Copy only the manifest and lock first so this layer is cached until dependencies change
COPY pixi.toml pixi.lock ./
RUN pixi install --locked -e backend-prod
# Activation script (PATH, CONDA_PREFIX, package activation) for the runtime image
RUN pixi shell-hook -e backend-prod -s bash > /shell-hook.sh

# ---------- test: backend environment incl. pytest, used by the backend-test service ----------
FROM build AS test
RUN pixi install --locked -e backend
COPY backend/ /app/backend/
WORKDIR /app/backend
CMD ["pixi", "run", "-e", "backend", "test"]

# ---------- runtime: only the environment and the code, no pixi or compilers ----------
FROM debian:trixie-slim AS runtime
RUN useradd --create-home --uid 1000 app
# The environment must keep the same absolute path: conda environments embed their prefix
COPY --from=build /app/.pixi/envs/backend-prod /app/.pixi/envs/backend-prod
COPY --from=build /shell-hook.sh /shell-hook.sh
COPY backend/ /app/backend/
# For commands that bypass the entrypoint, e.g. the Compose healthcheck
ENV PATH=/app/.pixi/envs/backend-prod/bin:$PATH
WORKDIR /app/backend
USER app
EXPOSE 8000
ENTRYPOINT ["/app/backend/entrypoint.sh"]
