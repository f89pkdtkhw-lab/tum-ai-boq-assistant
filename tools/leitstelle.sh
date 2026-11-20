#!/usr/bin/env bash
# Leitstelle: ein Fenster mit drei Bereichen, auf macOS und Linux/WSL gleich.
#   links:        Herdr mit First Mate und allen Worker-Fenstern
#   rechts oben:  quota-axi, Restkontingent jedes Abos live
#   rechts unten: die letzten Posts vom Team-Board, alle 30 Sekunden neu
#
#   bash tools/leitstelle.sh
#
# Läuft die Leitstelle schon, verbindet das Skript nur wieder mit ihr.
# Bereich wechseln: Strg+B, dann Pfeiltaste. Schließen ohne Beenden: Strg+B, dann D.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FM="${FIRSTMATE_DIR:-$HOME/firstmate}"
SESSION=leitstelle

for tool in tmux herdr quota-axi; do
  command -v "$tool" >/dev/null 2>&1 || { echo "✗ $tool fehlt, siehe docs/firstmate.md"; exit 1; }
done
[ -d "$FM" ] || { echo "✗ FirstMate fehlt in $FM, erst bash tools/firstmate/setup.sh ausführen"; exit 1; }

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" -x "$(tput cols 2>/dev/null || echo 200)" -y "$(tput lines 2>/dev/null || echo 50)" \
    -c "$FM" "echo 'First Mate starten: claude   (fürs Handy danach /remote-control)'; herdr; exec bash"
  tmux split-window -h -t "$SESSION" -l 38% "quota-axi --tui || { echo 'quota-axi beendet'; exec bash; }"
  tmux split-window -v -t "$SESSION" -c "$REPO" \
    "while true; do clear; echo 'Team-Board (alle 30 s)'; tools/board read -n 8; sleep 30; done"
  tmux set-option -t "$SESSION" mouse on >/dev/null
  # Browser-Dashboard läuft unsichtbar in einem zweiten tmux-Fenster: http://localhost:8770
  tmux new-window -d -t "$SESSION" -n dashboard -c "$REPO" "python3 tools/dashboard.py; exec bash"
  tmux select-pane -t "$SESSION:0.0"
fi
exec tmux attach -t "$SESSION"
