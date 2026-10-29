# Scroll Guard — Home Assistant add-on image (aarch64 / amd64, CPU only).
# Debian base, because PyTorch has no wheels for the Alpine images HA uses by default.
FROM python:3.12-slim-bookworm

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    SCROLL_GUARD_DATA=/data \
    SCROLL_GUARD_MODELS=/data/models

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 jq \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app/requirements.txt /app/requirements.txt
# CPU-only PyTorch first, so ultralytics does not pull the multi-GB CUDA build
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision \
    && pip install -r /app/requirements.txt

COPY app/ /app/
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
