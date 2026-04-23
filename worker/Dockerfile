# ── DWSIM Worker — Linux/amd64 ──────────────────────────────────────────────
#
# DWSIM 8.x supports Linux via .NET 6.  This image:
#   1. Installs .NET 6 runtime + pythonnet
#   2. Downloads and installs the DWSIM Linux release
#   3. Installs xvfb for the headless-screenshot strategy
#   4. Copies the CPD-Pilot backend and runs the FastAPI API server
#
# Build:
#   docker build -t cpd-pilot-worker -f worker/Dockerfile .
#
# Run standalone:
#   docker run -p 8000:8000 -e ANTHROPIC_API_KEY=sk-... cpd-pilot-worker
#
# DWSIM version — update DWSIM_VERSION to pick a newer release.
# Check https://github.com/DanWBR/dwsim/releases for available tags.

ARG DWSIM_VERSION=8.8.7

FROM mcr.microsoft.com/dotnet/runtime:6.0-jammy AS base

# ── System dependencies ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3-pip python3-venv \
        xvfb \
        libglib2.0-0 libgl1-mesa-glx libfontconfig1 \
        wget ca-certificates unzip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Ensure `python` resolves to 3.11
RUN ln -sf /usr/bin/python3.11 /usr/local/bin/python \
 && ln -sf /usr/bin/pip3 /usr/local/bin/pip

# ── DWSIM installation ─────────────────────────────────────────────────────────
ARG DWSIM_VERSION
ENV DWSIM_PATH=/opt/dwsim

# Download the Linux release from GitHub and unpack to /opt/dwsim
# The release is a .tar.gz containing the DWSIM binary + DLLs.
RUN set -eux; \
    DWSIM_TAR="DWSIM_${DWSIM_VERSION}_linux-x64.tar.gz"; \
    wget -q "https://github.com/DanWBR/dwsim/releases/download/v${DWSIM_VERSION}/${DWSIM_TAR}" \
        -O /tmp/dwsim.tar.gz; \
    mkdir -p "${DWSIM_PATH}"; \
    tar -xzf /tmp/dwsim.tar.gz -C "${DWSIM_PATH}" --strip-components=1; \
    rm /tmp/dwsim.tar.gz

# ── Python dependencies ────────────────────────────────────────────────────────
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
        pythonnet>=3.0.0 \
        fastapi>=0.115.0 \
        "uvicorn[standard]>=0.30.0" \
        anthropic>=0.40.0 \
        mcp[cli]>=1.0.0 \
        pydantic>=2.0.0 \
        openpyxl>=3.1.0 \
        cairosvg>=2.7.0

# ── Copy application source ────────────────────────────────────────────────────
COPY . .

# ── Runtime environment ────────────────────────────────────────────────────────
ENV PYTHONPATH=/app
ENV DWSIM_PATH=/opt/dwsim
# ANTHROPIC_API_KEY must be supplied at runtime (do not bake into image)

# Output directory for generated files
RUN mkdir -p /app/outputs && chmod 777 /app/outputs

EXPOSE 8000

# ── Entrypoint ────────────────────────────────────────────────────────────────
# xvfb-run provides a virtual display so DWSIM's FlowsheetSurface can render.
# Display size 1920x1080 is enough for any flowsheet the API will generate.
CMD ["xvfb-run", "-a", "-s", "-screen 0 1920x1080x24", \
     "uvicorn", "api.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1"]
