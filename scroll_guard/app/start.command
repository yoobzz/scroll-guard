#!/bin/zsh
# Scroll Guard: camera preview + internet cut-off through the ESP32 relay.
# Python: $SCROLL_GUARD_PYTHON if set, otherwise .venv next to this file (see README).
cd "${0:A:h}"
if [[ -n "$SCROLL_GUARD_PYTHON" ]]; then
  PY="$SCROLL_GUARD_PYTHON"
elif [[ -x .venv/bin/python ]]; then
  PY=.venv/bin/python
else
  echo "No Python environment. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi
( sleep 6 && open "http://127.0.0.1:8911" ) &
exec "$PY" serwer.py "$@"
