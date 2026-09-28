# claude-conversation-logger

**English** | [한국어](README.ko.md)

A Claude Code plugin that automatically saves every session as a human-readable Markdown file.

Every time Claude finishes responding, the current session is written to disk as Markdown you can read, grep, or drop into a notes app like Obsidian.

Claude Code already keeps raw JSONL transcripts under `~/.claude/projects/`, but they are hard to read and are deleted after `cleanupPeriodDays` (30 days by default). This plugin keeps a readable, permanent copy — automatically, with no `/export` needed.

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

Inside a Claude Code session, run:

```
/plugin marketplace add cadenzah/claude-conversation-logger
/plugin install conversation-logger@cadenzah-plugins
```

Or from your shell:

```bash
claude plugin marketplace add cadenzah/claude-conversation-logger
claude plugin install conversation-logger@cadenzah-plugins
```

The hook is registered automatically (no `settings.json` editing) and runs in the background, so it never delays Claude's responses. The plugin activates on the next session, or immediately after `/reload-plugins`.

## Updating

```
/plugin marketplace update cadenzah-plugins
```

To receive updates automatically, open `/plugin` → **Marketplaces** → `cadenzah-plugins` → **Enable auto-update**.

## Migrating from the old install script

Earlier versions were installed by cloning into `~/.claude/plugins/conversation-logger` and adding a `Stop` hook to `~/.claude/settings.json` by hand. If you installed that way, remove the old setup **before** installing the plugin, otherwise every session will be logged twice:

1. Delete the `Stop` hook entry whose command is `python3 ~/.claude/plugins/conversation-logger/hooks/save-conversation-log.py` from `~/.claude/settings.json`.
2. Remove the old clone:
   ```bash
   rm -rf ~/.claude/plugins/conversation-logger
   ```
3. Install via `/plugin` as shown above.

Existing logs in `~/.claude/conversation-logs/` are kept and keep being updated.

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

## Privacy and configuration

> **Logs are plain-text copies of everything in the session**, including file contents Claude read and command output. Unlike Claude Code's own transcripts, they are never cleaned up automatically. Don't sync `~/.claude/conversation-logs/` to shared or public locations.

To reduce the risk:

- **Secret redaction (on by default)**: values that look like API keys, tokens (GitHub, Anthropic, OpenAI, AWS, Slack, Google, JWTs), private keys, `Authorization` headers, passwords in URLs, and `.env`-style `*_TOKEN=` / `*_PASSWORD=` / `*_API_KEY=` assignments are replaced with `[REDACTED]`. This is pattern-based and best-effort — it will not catch everything.
- **Tool output control**: tool results (file reads, command output) are usually the largest and most sensitive part of a log.
- Log files are created with owner-only permissions (`600`).

Set these in the `env` section of `~/.claude/settings.json`:

| Variable | Values | Default |
| --- | --- | --- |
| `CONVERSATION_LOGGER_TOOL_OUTPUT` | `full` — keep everything<br>`truncate` — first 2,000 characters of each result<br>`none` — omit tool results entirely | `full` |
| `CONVERSATION_LOGGER_REDACT` | `1` — mask secret-looking values<br>`0` — disable redaction | `1` |

```json
{
  "env": {
    "CONVERSATION_LOGGER_TOOL_OUTPUT": "truncate"
  }
}
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
