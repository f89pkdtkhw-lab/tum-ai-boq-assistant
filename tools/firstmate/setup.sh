#!/usr/bin/env bash
# Richtet FirstMate für unser Team ein. Läuft auf macOS und unter Linux/WSL, nicht in Windows selbst.
#
#   bash tools/firstmate/setup.sh "Raban"
#
# Prüft die Werkzeuge, klont FirstMate nach ~/firstmate (oder $FIRSTMATE_DIR) und schreibt
# die lokalen, nicht eingecheckten Einstellungen: Herdr als Fensterverwaltung, unsere
# Modellwahl pro Aufgabe und die Vorlieben des Captains mit Team-Board und Repo-Regeln.
# Installiert selbst nichts; was fehlt, steht am Ende mit Befehl da.
set -eo pipefail

NAME="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
FM="${FIRSTMATE_DIR:-$HOME/firstmate}"

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  *) echo "✗ FirstMate läuft nur auf macOS oder Linux/WSL. Unter Windows: siehe docs/firstmate.md, Abschnitt WSL."; exit 1 ;;
esac

hint() {
  case "$1" in
    git) [ "$OS" = mac ] && echo "xcode-select --install" || echo "sudo apt install -y git" ;;
    gh) [ "$OS" = mac ] && echo "brew install gh" || echo "siehe https://github.com/cli/cli/blob/trunk/docs/install_linux.md" ;;
    jq) [ "$OS" = mac ] && echo "brew install jq" || echo "sudo apt install -y jq" ;;
    tmux) [ "$OS" = mac ] && echo "brew install tmux" || echo "sudo apt install -y tmux" ;;
    node|npm) [ "$OS" = mac ] && echo "brew install node" || echo "sudo apt install -y nodejs npm (oder nvm)" ;;
    python3) [ "$OS" = mac ] && echo "brew install python" || echo "sudo apt install -y python3" ;;
    claude) echo "curl -fsSL https://claude.ai/install.sh | bash, danach claude starten und anmelden" ;;
    codex) echo "npm install -g @openai/codex, danach codex starten und mit ChatGPT anmelden" ;;
    herdr) [ "$OS" = mac ] && echo "brew install herdr" || echo "curl -fsSL https://herdr.dev/install.sh | sh" ;;
    quota-axi) echo "npm install -g quota-axi" ;;
    gemini) echo "npm install -g @google/gemini-cli, danach gemini starten und mit Google anmelden" ;;
  esac
}

missing=()
optional=()
for tool in git gh jq tmux node npm python3 claude codex herdr quota-axi; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done

if [ "${#missing[@]}" -gt 0 ]; then
  echo "✗ Es fehlen noch Werkzeuge:"
  for tool in "${missing[@]}"; do echo "    $tool: $(hint "$tool")"; done
  echo "Installiere sie und starte das Skript erneut."
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "✗ GitHub CLI ist nicht angemeldet: gh auth login"
  exit 1
fi

LOGIN="$(gh api user --jq .login)"
NAME="${NAME:-$LOGIN}"
BOARD="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['issue'])" "$REPO_ROOT/tools/board.json")"

if [ -d "$FM/.git" ]; then
  echo "✓ FirstMate liegt schon in $FM"
else
  git clone https://github.com/kunchenguid/firstmate "$FM"
fi
mkdir -p "$FM/config" "$FM/data"

echo herdr > "$FM/config/backend"
cp "$HERE/crew-dispatch.json" "$FM/config/crew-dispatch.json"
if [ -f "$FM/data/captain.md" ]; then
  echo "! $FM/data/captain.md existiert schon und bleibt unverändert. Vorlage: tools/firstmate/captain.md"
else
  sed -e "s/<LOGIN>/$LOGIN/g" -e "s/<NAME>/$NAME/g" -e "s/<BOARD>/$BOARD/g" "$HERE/captain.md" > "$FM/data/captain.md"
fi

echo "✓ Herdr als Fensterverwaltung, Modellwahl und Captain-Vorlieben für @$LOGIN eingerichtet."
for tool in "${optional[@]}"; do echo "! Optional für Recherche-Aufgaben: $tool ($(hint "$tool"))"; done
cat <<EOF

Nächste Schritte:
  1. herdr starten, in einem Fenster: cd "$FM" && claude
  2. Beim ersten Start prüft FirstMate fehlende Werkzeuge und fragt vor jeder Installation.
  3. Schreib dem First Mate:
     "Füge https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant als Projekt im Modus direct-PR +yolo hinzu."
  4. Fürs Handy: im First-Mate-Fenster /remote-control eingeben und in der Claude-App unter Code verbinden.
EOF
