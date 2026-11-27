#!/usr/bin/env bash
# Führt Entwicklungsbefehle in der WSL-Umgebung aus.
#
# Die Python-Umgebung liegt bewusst im Linux-Dateisystem (~/.venvs/ha-homewake),
# nicht unter /mnt/c: dort wäre sie sehr langsam.
#
# Aufruf (aus WSL):        scripts/dev.sh <befehl>
# Aufruf (aus Windows):    wsl -e bash <repo-in-wsl>/scripts/dev.sh <befehl>  (oder scripts/dev.ps1)
#
# Befehle:
#   setup   Umgebung anlegen bzw. auf den Stand von uv.lock bringen,
#           Node.js (Version aus frontend/.node-version) und Karten-Pakete dazu
#   test    pytest (weitere Argumente werden durchgereicht)
#   lint    ruff check + ruff format --check
#   format  ruff format + ruff check --fix, Biome für die Karte
#   types   mypy --strict
#   karte   Karte bauen und prüfen (Biome, tsc, Vitest), E73
#   npm     npm im Ordner frontend/, z. B. "npm run build"
#   check   Karte bauen und prüfen, dann lint + types + test (alles, was vor
#           einem Commit grün sein muss)
#   run     beliebigen Befehl in der Umgebung ausführen, z. B. "run python -V"
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/ha-homewake}"
export UV_LINK_MODE=copy

cd "$(dirname "$0")/.."

cmd="${1:-check}"
shift || true

# npm im Kartenordner, mit dem Node.js aus der uv-Umgebung (E67)
karten_npm() { (cd frontend && uv run --no-sync --project .. npm "$@"); }

node_einrichten() {
  local soll ist
  soll="$(cat frontend/.node-version)"
  ist="$(uv run --no-sync node --version 2>/dev/null || true)"
  if [ "$ist" != "v$soll" ]; then
    uv run --no-sync nodeenv --python-virtualenv --prebuilt --force --node="$soll"
  fi
  karten_npm ci
}

case "$cmd" in
  setup)  (uv sync --locked 2>/dev/null || uv sync) && node_einrichten ;;
  test)   uv run --no-sync pytest "$@" ;;
  lint)   uv run --no-sync ruff check . && uv run --no-sync ruff format --check . ;;
  format)
    uv run --no-sync ruff format . && uv run --no-sync ruff check --fix .
    karten_npm run format
    ;;
  types)  uv run --no-sync mypy custom_components tests ;;
  karte)  karten_npm run build && karten_npm run check ;;
  npm)    karten_npm "$@" ;;
  check)
    karten_npm run build
    karten_npm run check
    uv run --no-sync ruff check .
    uv run --no-sync ruff format --check .
    uv run --no-sync mypy custom_components tests
    uv run --no-sync pytest --cov --cov-report=term "$@"
    ;;
  run)    uv run --no-sync "$@" ;;
  *) echo "Unbekannter Befehl: $cmd" >&2; exit 2 ;;
esac
