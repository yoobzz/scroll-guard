#!/usr/bin/env sh
# Scroll Guard add-on entry point. Options come from /data/options.json (the add-on UI).
set -e

OPTIONS=/data/options.json
MODEL_SIZE=$(jq -r '.model_size // "light"' "$OPTIONS" 2>/dev/null || echo light)
if [ "$MODEL_SIZE" = "full" ]; then
  export SCROLL_GUARD_MODELE=pelne
else
  export SCROLL_GUARD_MODELE=lekkie
fi
mkdir -p "$SCROLL_GUARD_MODELS"

echo "[scroll guard] models: $MODEL_SIZE (downloaded to $SCROLL_GUARD_MODELS on first start)"
exec python /app/serwer.py --ingress --port 8911 --opcje "$OPTIONS"
