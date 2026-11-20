#!/usr/bin/env bash
# Control station: one window with three panes, identical on macOS and Linux/WSL.
#   left:         Herdr with First Mate and all worker windows
#   upper right:  quota-axi, live remaining subscription quotas
#   lower right:  latest team board posts, refreshed every 30 seconds
#
#   bash tools/leitstelle.sh
#
# If the control station is already running, this script reattaches.
# Switch pane: Ctrl+B, then arrow. Detach without stopping: Ctrl+B, then D.
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
FM="${FIRSTMATE_DIR:-$HOME/firstmate}"
SESSION=leitstelle

for tool in tmux herdr quota-axi; do
  command -v "$tool" >/dev/null 2>&1 || { echo "✗ $tool missing, see docs/firstmate.md"; exit 1; }
done
[ -d "$FM" ] || { echo "✗ FirstMate missing in $FM; run bash tools/firstmate/setup.sh first"; exit 1; }

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" -x "$(tput cols 2>/dev/null || echo 200)" -y "$(tput lines 2>/dev/null || echo 50)" \
    -c "$FM" "echo 'Start First Mate: claude   (then /remote-control for phone access)'; herdr; exec bash"
  tmux split-window -h -t "$SESSION" -l 38% "quota-axi --tui || { echo 'quota-axi stopped'; exec bash; }"
  tmux split-window -v -t "$SESSION" -c "$REPO" \
    "while true; do clear; echo 'Team board (every 30 s)'; tools/board read -n 8; sleep 30; done"
  tmux set-option -t "$SESSION" mouse on >/dev/null
  # Browser dashboard runs hidden in a second tmux window: http://localhost:8770
  tmux new-window -d -t "$SESSION" -n dashboard -c "$REPO" "python3 tools/dashboard.py; exec bash"
  tmux select-pane -t "$SESSION:0.0"
fi
exec tmux attach -t "$SESSION"
