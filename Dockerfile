FROM python:3.13-slim

# pyskylight is the sibling client library. Until it is on PyPI, install from git.
ARG PYSKYLIGHT_REF=main
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1

WORKDIR /app
RUN pip install --no-cache-dir "pyskylight @ git+https://github.com/joshuaswarren/pyskylight@${PYSKYLIGHT_REF}"

COPY . /app
RUN pip install --no-cache-dir .

# State lives on a mounted volume so the reconcile mapping survives restarts.
ENV SYNC_STATE_PATH=/data/state.json
VOLUME ["/data"]

ENTRYPOINT ["/app/run-loop.sh"]
