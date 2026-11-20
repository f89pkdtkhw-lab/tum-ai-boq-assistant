#!/usr/bin/env bash
# Switch the First Mate model selection.
#   bash tools/firstmate/modus.sh abo      # Personal subscriptions: quota-driven, Opus for UI
#   bash tools/firstmate/modus.sh budget   # Provided API key: one budget, cheaper models
set -eo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FM="${FIRSTMATE_DIR:-$HOME/firstmate}"
case "${1:-}" in
  abo) SOURCE="$HERE/crew-dispatch.json" ;;
  budget) SOURCE="$HERE/crew-dispatch.budget.json" ;;
  *) echo "Usage: bash tools/firstmate/modus.sh abo|budget"; exit 1 ;;
esac
[ -d "$FM/config" ] || { echo "✗ $FM/config missing; run bash tools/firstmate/setup.sh first"; exit 1; }
cp "$SOURCE" "$FM/config/crew-dispatch.json"
echo "✓ Model selection set to '$1'. Applies to every newly started worker."
