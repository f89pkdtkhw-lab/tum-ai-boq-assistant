#!/usr/bin/env bash
# Set up FirstMate for our team. Runs on macOS and Linux/WSL, not directly on Windows.
#
#   bash tools/firstmate/setup.sh "Raban"
#
# Check tools, clone FirstMate into ~/firstmate (or $FIRSTMATE_DIR) and write
# local, untracked settings: Herdr window management, our
# per-task model selection and captain preferences with team board and repository rules.
# Installs nothing automatically; missing tools are listed with install commands.
set -eo pipefail

NAME="${1:-}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
FM="${FIRSTMATE_DIR:-$HOME/firstmate}"

case "$(uname -s)" in
  Darwin) OS=mac ;;
  Linux) OS=linux ;;
  *) echo "✗ FirstMate runs only on macOS or Linux/WSL. On Windows: see the WSL section in docs/firstmate.md."; exit 1 ;;
esac

hint() {
  case "$1" in
    git) [ "$OS" = mac ] && echo "xcode-select --install" || echo "sudo apt install -y git" ;;
    gh) [ "$OS" = mac ] && echo "brew install gh" || echo "see https://github.com/cli/cli/blob/trunk/docs/install_linux.md" ;;
    jq) [ "$OS" = mac ] && echo "brew install jq" || echo "sudo apt install -y jq" ;;
    tmux) [ "$OS" = mac ] && echo "brew install tmux" || echo "sudo apt install -y tmux" ;;
    node|npm) [ "$OS" = mac ] && echo "brew install node" || echo "sudo apt install -y nodejs npm (or nvm)" ;;
    python3) [ "$OS" = mac ] && echo "brew install python" || echo "sudo apt install -y python3" ;;
    claude) echo "curl -fsSL https://claude.ai/install.sh | bash, then start claude and sign in" ;;
    codex) echo "npm install -g @openai/codex, then start codex and sign in with ChatGPT" ;;
    herdr) [ "$OS" = mac ] && echo "brew install herdr" || echo "curl -fsSL https://herdr.dev/install.sh | sh" ;;
    quota-axi) echo "npm install -g quota-axi" ;;
    gemini) echo "npm install -g @google/gemini-cli, then start gemini and sign in with Google" ;;
  esac
}

missing=()
optional=()
for tool in git gh jq tmux node npm python3 claude codex herdr quota-axi; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done

if [ "${#missing[@]}" -gt 0 ]; then
  echo "✗ Missing tools:"
  for tool in "${missing[@]}"; do echo "    $tool: $(hint "$tool")"; done
  echo "Install them and rerun this script."
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "✗ GitHub CLI is not signed in: gh auth login"
  exit 1
fi

LOGIN="$(gh api user --jq .login)"
NAME="${NAME:-$LOGIN}"
BOARD="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['issue'])" "$REPO_ROOT/tools/board.json")"

if [ -d "$FM/.git" ]; then
  echo "✓ FirstMate already exists in $FM"
else
  git clone https://github.com/kunchenguid/firstmate "$FM"
fi
mkdir -p "$FM/config" "$FM/data"

echo herdr > "$FM/config/backend"
cp "$HERE/crew-dispatch.json" "$FM/config/crew-dispatch.json"
if [ -f "$FM/data/captain.md" ] && grep -q "tum-ai-boq-assistant" "$FM/data/captain.md"; then
  echo "! $FM/data/captain.md already belongs to this repository and is preserved. Template: tools/firstmate/captain.md"
else
  if [ -f "$FM/data/captain.md" ]; then
    cp "$FM/data/captain.md" "$FM/data/captain.md.bak-$(date +%Y%m%d-%H%M%S)"
    echo "✓ Old captain preferences backed up (captain.md.bak-…)"
  fi
  sed -e "s/<LOGIN>/$LOGIN/g" -e "s/<NAME>/$NAME/g" -e "s/<BOARD>/$BOARD/g" "$HERE/captain.md" > "$FM/data/captain.md"
fi

echo "✓ Herdr window management, model selection and captain preferences configured for @$LOGIN."
for tool in "${optional[@]}"; do echo "! Optional for research tasks: $tool ($(hint "$tool"))"; done
cat <<EOF

Next steps:
  1. Start herdr, then in a window: cd "$FM" && claude
  2. On first start FirstMate checks missing tools and asks before each installation.
  3. Tell the First Mate:
     "Add https://github.com/f89pkdtkhw-lab/tum-ai-boq-assistant as a project in direct-PR +yolo mode.
      Then work autonomously according to captain.md: overview with tools/stand.py, pull available agent-bereit issues."
  4. For your phone: enter /remote-control in the First Mate window and connect in the Claude app under Code.
EOF
