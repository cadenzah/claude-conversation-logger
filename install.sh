#!/bin/bash
# Deprecated: conversation-logger is now distributed as a Claude Code plugin.
# This script only explains how to switch; it no longer installs anything.

OLD_DIR="$HOME/.claude/plugins/conversation-logger"

cat <<'EOF'
conversation-logger is now installed through the Claude Code plugin system.

Inside a Claude Code session, run:

  /plugin marketplace add cadenzah/claude-conversation-logger
  /plugin install conversation-logger@cadenzah-plugins

EOF

if [ -d "$OLD_DIR" ] || grep -qs 'conversation-logger/hooks/save-conversation-log.py' "$HOME/.claude/settings.json"; then
  cat <<EOF
An older manual install was detected. Remove it first to avoid duplicate logging:

  1. Delete the Stop hook entry running
     python3 ~/.claude/plugins/conversation-logger/hooks/save-conversation-log.py
     from ~/.claude/settings.json
  2. rm -rf "$OLD_DIR"

EOF
fi

echo "See https://github.com/cadenzah/claude-conversation-logger#installation for details."
