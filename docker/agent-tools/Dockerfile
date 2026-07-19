# syntax=docker/dockerfile:1.7
# The base manifest and Debian snapshot are mirrored in toolchain.lock.json.
FROM python:3.13-slim@sha256:afe189875f1d2f9b45e287834fb9f2c273a5d59d354ae4050ab9affbf0a6ba06

ARG DEBIAN_SNAPSHOT=20260718T000000Z
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SDIT_DATA_DIR=/var/lib/sdit

RUN rm -f /etc/apt/sources.list.d/debian.sources \
    && printf '%s\n' \
      "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/${DEBIAN_SNAPSHOT} trixie main" \
      "deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/${DEBIAN_SNAPSHOT} trixie-security main" \
      > /etc/apt/sources.list \
    && apt-get -o Acquire::Check-Valid-Until=false update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      dnsutils \
      iproute2 \
      jq \
      netcat-openbsd \
      nmap \
      openssh-client \
      tini \
    && find /var/lib/apt/lists -type f -delete

WORKDIR /opt/sdit
COPY src-python/requirements.lock ./requirements.lock
RUN python -m pip install --require-hashes -r requirements.lock

COPY src-python/app ./app
COPY src-python/run.py ./run.py
COPY skills ./skills
COPY knowledge_base ./knowledge_base

RUN mkdir -p "${SDIT_DATA_DIR}" \
    && python - <<'PY'
import importlib.metadata
import json
import shutil
import subprocess
from pathlib import Path

tools = {}
for name in ("curl", "dig", "ip", "jq", "nc", "nmap", "ssh"):
    path = shutil.which(name)
    if path:
        probe = subprocess.run([path, "--version"], text=True, capture_output=True, timeout=5, check=False)
        tools[name] = {"path": path, "version": (probe.stdout or probe.stderr).splitlines()[0][:240]}
packages = {dist.metadata["Name"]: dist.version for dist in importlib.metadata.distributions() if dist.metadata.get("Name")}
Path("/opt/sdit/TOOLCHAIN_SNAPSHOT.json").write_text(
    json.dumps({"schema_version": "toolchain-snapshot.v1", "tools": tools, "python_packages": packages}, sort_keys=True, indent=2),
    encoding="utf-8",
)
PY

EXPOSE 8765
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"]
