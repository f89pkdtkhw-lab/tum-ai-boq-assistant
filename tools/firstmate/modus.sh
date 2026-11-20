#!/usr/bin/env bash
# Schaltet die Modellwahl des First Mates um.
#   bash tools/firstmate/modus.sh abo      # eigene Abos: Kontingent-gesteuert, Opus für Oberfläche
#   bash tools/firstmate/modus.sh budget   # gestellter API-Key: ein Budget, günstigere Modelle
set -eo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FM="${FIRSTMATE_DIR:-$HOME/firstmate}"
case "${1:-}" in
  abo) SOURCE="$HERE/crew-dispatch.json" ;;
  budget) SOURCE="$HERE/crew-dispatch.budget.json" ;;
  *) echo "Aufruf: bash tools/firstmate/modus.sh abo|budget"; exit 1 ;;
esac
[ -d "$FM/config" ] || { echo "✗ $FM/config fehlt, erst bash tools/firstmate/setup.sh ausführen"; exit 1; }
cp "$SOURCE" "$FM/config/crew-dispatch.json"
echo "✓ Modellwahl auf '$1' gestellt. Gilt für jeden neu gestarteten Worker."
