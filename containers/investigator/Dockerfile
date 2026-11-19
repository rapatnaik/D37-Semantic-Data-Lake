# Isolated worker for model-generated analysis code (d37-agent).
# Build from the repository root:
#   docker build -f containers/investigator/Dockerfile -t d37-investigator-worker:latest .
# The runtime adds the isolation (see agents/investigator/execution.py):
#   --network none, --read-only, --cap-drop ALL, no-new-privileges, user 65534,
#   memory/CPU/PID limits, read-only input mounts, one writable outputs/ mount.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

# Analysis libraries pinned by uv.lock (dependency group "worker").
COPY pyproject.toml uv.lock /tmp/build/
RUN cd /tmp/build \
 && uv export --frozen --only-group worker --no-emit-project -o requirements.txt \
 && uv pip install --system --no-cache --require-hashes -r requirements.txt \
 && rm -rf /tmp/build /usr/local/bin/uv

# The runtime mounts the current worker.py read-only over this copy, so the
# image does not need rebuilding when the worker changes.
COPY agents/investigator/worker.py /opt/d37/worker.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=0 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/mpl \
    HOME=/tmp

USER 65534:65534
WORKDIR /work
CMD ["python", "-I", "/opt/d37/worker.py", "/work"]
