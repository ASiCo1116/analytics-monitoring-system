# Build context: repository root (docker build -f frontend/Dockerfile .)

# ---------- build: resolve the locked pixi environment ----------
FROM ghcr.io/prefix-dev/pixi:0.83.0 AS build
WORKDIR /app
# Copy only the manifest and lock first so this layer is cached until dependencies change
COPY pixi.toml pixi.lock ./
RUN pixi install --locked -e frontend
# Activation script (PATH, CONDA_PREFIX, package activation) for the runtime image
RUN pixi shell-hook -e frontend -s bash > /shell-hook.sh

# ---------- runtime: only the environment and the code, no pixi or compilers ----------
FROM debian:trixie-slim AS runtime
RUN useradd --create-home --uid 1000 app
# The environment must keep the same absolute path: conda environments embed their prefix
COPY --from=build /app/.pixi/envs/frontend /app/.pixi/envs/frontend
COPY --from=build /shell-hook.sh /shell-hook.sh
COPY frontend/ /app/frontend/
# For commands that bypass the entrypoint, e.g. the Compose healthcheck
ENV PATH=/app/.pixi/envs/frontend/bin:$PATH
WORKDIR /app/frontend
USER app
EXPOSE 8501
ENTRYPOINT ["/app/frontend/entrypoint.sh"]
