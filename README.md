# claude-conversation-logger

**English** | [한국어](README.ko.md)

A Claude Code plugin that automatically saves every session as a human-readable Markdown file.

Every time Claude finishes responding, the current session is written to disk — so nothing is lost to context compression, and you can review past conversations any time.

## What it does

- Saves each session as a `.md` file after every Claude response
- Organizes logs by project name in subdirectories
- Filenames include the session start time and a human-readable title for easy browsing
- Extended thinking (`<details>` blocks) is preserved as collapsible sections
- Internal system tags are stripped; only the real conversation is kept

The title in the filename is taken from Claude Code's AI-generated session title when available, and falls back to the first meaningful user message otherwise.

**Log location:**
```
~/.claude/conversation-logs/
  my-project/
    2026-03-24_13-04-37_0024fc91_how-to-set-up-a-stop-hook.md
    2026-03-23_09-11-02_fe5d4af5_refactor-auth-middleware.md
  another-project/
    2026-03-20_17-30-00_308b6c72_initial-project-setup.md
```

## Requirements

- Python 3 (available on the system `PATH`)
- Claude Code 2.x or later

## Installation

**1. Run the install script:**

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/cadenzah/claude-conversation-logger/main/install.sh)
```

This clones the repository to `~/.claude/plugins/conversation-logger`. Running the same command again will update the plugin to the latest version.

**2. Add the Stop hook** to your `~/.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/plugins/conversation-logger/hooks/save-conversation-log.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

If you already have other hooks under `Stop`, add this entry to the existing array.

The plugin activates on the next Claude Code session.

## Updating

Run the same install script to pull the latest changes:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/cadenzah/claude-conversation-logger/main/install.sh)
```

## Log format

Each file starts with session metadata followed by the conversation:

```markdown
# Conversation Log

- **Session ID**: `0024fc91-...`
- **Project**: `my-project` (`/Users/you/my-project`)
- **Started**: 2026-03-24 13:04:37
- **Last updated**: 2026-03-24 14:22:10
- **Messages**: 42

---

## User `2026-03-24 13:04:37`

How do I set up a Stop hook in Claude Code?

## Claude `2026-03-24 13:05:14`

<details>
<summary>Thinking</summary>

The user is asking about Stop hooks...

</details>

Stop hooks are configured in `~/.claude/settings.json` under the `"hooks"` key...
```

## Quick access to logs from your project

You can create a symlink inside your project directory to jump directly to that project's conversation logs:

```bash
ln -s ~/.claude/conversation-logs/$(basename "$PWD") ./.claude/conversation-logs
```

After this, `.claude/conversation-logs/` in your project will point to all saved sessions for that project. Feel free to change the symlink path to wherever you prefer — only the link location matters, not the name.

> **Note:** Add the symlink to `.gitignore` to avoid committing it. The target path (`~/.claude/conversation-logs/`) is local to each machine, so the link will be broken on other people's environments.
>
> ```bash
> echo ".claude/conversation-logs" >> .gitignore
> ```
>
> To remove the symlink, simply delete it — the actual log files will not be affected:
>
> ```bash
> rm ./.claude/conversation-logs
> ```

## How it works

The plugin registers a `Stop` hook that fires whenever Claude finishes a response. The hook receives the path to the current session's JSONL transcript, parses it, and writes a Markdown file. Because the file is overwritten on each trigger, you always have an up-to-date snapshot — even mid-session.

## Contributing

Contributions are welcome! Feel free to open issues for bug reports or feature requests, and pull requests are always appreciated.

If you have ideas for improvements — new output formats, filtering options, better metadata, or anything else — don't hesitate to jump in.

## License

MIT
