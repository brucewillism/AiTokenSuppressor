#!/bin/sh
set -e

echo "Validando configuracao..."
python -c "from app.core.config import get_settings; get_settings()" || {
  echo ""
  echo "ERRO: .env invalido. Verifique SECRET_KEY (min. 32 chars) e DATABASE_URL."
  exit 1
}

python - <<'PY'
import os
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL", "")
user = urlparse(url).username or "(vazio)"
print(f"DATABASE_URL usuario: {user}")
if user == "postgres" and os.environ.get("POSTGRES_USER", "") not in ("", "postgres"):
    print("AVISO: DATABASE_URL usa 'postgres' mas POSTGRES_USER difere — confira o .env")
PY

echo "Iniciando uvicorn..."
python -c "from app.main import app; print('Import app.main: OK')" || {
  echo ""
  echo "ERRO: falha ao importar app.main (dependencia ou codigo)."
  exit 1
}

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
