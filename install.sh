#!/bin/bash
set -e

INSTALL_DIR="$HOME/.claude/plugins/conversation-logger"
REPO_URL="https://github.com/cadenzah/claude-conversation-logger"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Updating conversation-logger..."
  git -C "$INSTALL_DIR" pull
  echo "Done."
else
  echo "Installing conversation-logger..."
  git clone "$REPO_URL" "$INSTALL_DIR"
  echo ""
  echo "Add the following to ~/.claude/settings.json under \"hooks\" > \"Stop\":"
  echo ""
  echo '  {'
  echo '    "type": "command",'
  echo "    \"command\": \"python3 $INSTALL_DIR/hooks/save-conversation-log.py\","
  echo '    "timeout": 15'
  echo '  }'
  echo ""
  echo "Done. The plugin activates on the next Claude Code session."
fi
