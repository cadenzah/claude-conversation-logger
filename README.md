# claude-conversation-logger

A Claude Code plugin that automatically saves every session as a human-readable Markdown file.

Every time Claude finishes responding, the current session is written to disk — so nothing is lost to context compression, and you can review past conversations any time.

## What it does

- Saves each session as a `.md` file after every Claude response
- Organizes logs by project name in subdirectories
- Filenames include the session start time for easy browsing
- Extended thinking (`<details>` blocks) is preserved as collapsible sections
- Internal system tags are stripped; only the real conversation is kept

**Log location:**
```
~/.claude/conversation-logs/
  my-project/
    2026-03-24_13-04-37_0024fc91.md
    2026-03-23_09-11-02_fe5d4af5.md
  another-project/
    2026-03-20_17-30-00_308b6c72.md
```

## Installation

```bash
claude plugin install https://github.com/cadenzah/claude-conversation-logger
```

That's it. The plugin activates on the next Claude Code session.

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

## Requirements

- Python 3 (available on the system `PATH`)
- Claude Code 2.x or later

## How it works

The plugin registers a `Stop` hook that fires whenever Claude finishes a response. The hook receives the path to the current session's JSONL transcript, parses it, and writes a Markdown file. Because the file is overwritten on each trigger, you always have an up-to-date snapshot — even mid-session.

## License

MIT
