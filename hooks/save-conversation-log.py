#!/usr/bin/env python3
"""
Claude Code Stop hook: saves each session as a human-readable Markdown file.

Triggered automatically after every Claude response.
Logs are written to: ~/.claude/conversation-logs/{project-name}/{YYYY-MM-DD_HH-MM-SS}_{session}_{title}.md
Each session maps to one file; the file is overwritten on every trigger to keep it up to date.
The title is derived from the first meaningful user message in the conversation.

Environment variables:
    CONVERSATION_LOGGER_TOOL_OUTPUT  full (default) | truncate | none
    CONVERSATION_LOGGER_REDACT       1 (default) masks secret-looking values; 0 disables
"""

import difflib
import json
import re
import sys
import os
import time
from datetime import datetime


TOOL_OUTPUT_MODE = os.environ.get('CONVERSATION_LOGGER_TOOL_OUTPUT', 'full').strip().lower()
REDACT_ENABLED = os.environ.get('CONVERSATION_LOGGER_REDACT', '1').strip() != '0'
TOOL_OUTPUT_TRUNCATE_CHARS = 2000

REDACTED = '[REDACTED]'

# (pattern, replacement). Replacements keep any non-secret prefix (key names,
# "Bearer ") so the log stays readable.
_SECRET_PATTERNS = [
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----', re.DOTALL),
     '-----BEGIN PRIVATE KEY-----\n' + REDACTED + '\n-----END PRIVATE KEY-----'),
    (re.compile(r'\bsk-ant-[A-Za-z0-9_\-]{20,}'), REDACTED),
    (re.compile(r'\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}'), REDACTED),
    (re.compile(r'\bgh[pousr]_[A-Za-z0-9]{36,}'), REDACTED),
    (re.compile(r'\bgithub_pat_[A-Za-z0-9_]{40,}'), REDACTED),
    (re.compile(r'\bglpat-[A-Za-z0-9_\-]{20,}'), REDACTED),
    (re.compile(r'\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'), REDACTED),
    (re.compile(r'\bxox[abprs]-[A-Za-z0-9\-]{10,}'), REDACTED),
    (re.compile(r'\bAIza[0-9A-Za-z_\-]{35}\b'), REDACTED),
    (re.compile(r'\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'), REDACTED),
    (re.compile(r'(?i)(\bauthorization["\']?\s*[:=]\s*["\']?(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=\-]{8,}'),
     r'\1' + REDACTED),
    # dotenv-style assignments at line start: API_KEY=..., export DB_PASSWORD="..."
    (re.compile(r'(?m)^(\s*(?:export\s+)?[A-Z0-9_]*(?:SECRET|SECRET_KEY|TOKEN|PASSWORD|PASSWD|API_?KEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIALS?)=)(["\']?)[^\s"\']{4,}\2'),
     r'\1\2' + REDACTED + r'\2'),
    # URLs with inline credentials: scheme://user:password@host
    (re.compile(r'([a-z][a-z0-9+.\-]*://[^\s:/@]+:)[^\s@/]{3,}(@)'), r'\1' + REDACTED + r'\2'),
]


def redact_secrets(text):
    """Mask values that look like credentials."""
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def format_tool_output(text):
    """Apply CONVERSATION_LOGGER_TOOL_OUTPUT to a tool result."""
    if TOOL_OUTPUT_MODE == 'none':
        return ''
    if TOOL_OUTPUT_MODE == 'truncate' and len(text) > TOOL_OUTPUT_TRUNCATE_CHARS:
        omitted = len(text) - TOOL_OUTPUT_TRUNCATE_CHARS
        return f'{text[:TOOL_OUTPUT_TRUNCATE_CHARS]}\n… ({omitted} more characters truncated)'
    return text


def extract_content(content):
    """Extract (thinking, text) from a message content field.

    Returns:
        thinking (str | None): Extended thinking text, or None if absent.
        text (str): Visible response text and tool-use annotations.
    """
    if isinstance(content, str):
        return None, content
    if not isinstance(content, list):
        return None, ''

    thinking_parts = []
    text_parts = []

    for item in content:
        if not isinstance(item, dict):
            continue
        t = item.get('type')
        if t == 'text':
            text_parts.append(item.get('text', ''))
        elif t == 'thinking':
            thinking_parts.append(item.get('thinking', ''))
        elif t == 'tool_use':
            name = item.get('name', 'tool')
            input_data = item.get('input', {})
            if name == 'Edit':
                file_path = input_data.get('file_path', '')
                old_str = input_data.get('old_string', '')
                new_str = input_data.get('new_string', '')
                old_lines = (old_str + '\n').splitlines(keepends=True)
                new_lines = (new_str + '\n').splitlines(keepends=True)
                diff = difflib.unified_diff(
                    old_lines, new_lines,
                    fromfile=file_path, tofile=file_path,
                    lineterm=''
                )
                diff_content = '\n'.join(diff)
                text_parts.append(f"**[Tool: {name}]** `{file_path}`\n```diff\n{diff_content}\n```")
            else:
                input_str = json.dumps(input_data, ensure_ascii=False, indent=2)
                text_parts.append(f"**[Tool: {name}]**\n```json\n{input_str}\n```")
        elif t == 'tool_result':
            result_content = item.get('content', '')
            if isinstance(result_content, list):
                result_text = '\n'.join(
                    c.get('text', '') for c in result_content
                    if isinstance(c, dict) and c.get('type') == 'text'
                )
            else:
                result_text = str(result_content) if result_content else ''
            result_text = format_tool_output(result_text)
            if result_text.strip():
                text_parts.append(result_text)

    thinking = '\n\n'.join(p for p in thinking_parts if p.strip()) or None
    text = '\n\n'.join(p for p in text_parts if p.strip())
    return thinking, text


def format_timestamp(ts_str):
    """Convert an ISO timestamp to local time string."""
    try:
        dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
        return dt.astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ts_str


def load_entries(transcript_path):
    """Read a JSONL transcript into a list of entries, skipping malformed lines."""
    entries = []
    with open(transcript_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def entries_to_markdown(entries, session_id, cwd, last_assistant_message=None):
    """Render transcript entries as a Markdown string.

    ``last_assistant_message`` comes from the Stop hook input. The transcript is
    written asynchronously and may not contain the final reply yet; if so, the
    reply is appended so the log is never missing the last turn.

    Returns:
        (markdown: str | None, error: str | None)
    """
    messages = [e for e in entries if e.get('type') in ('user', 'assistant')]
    if not messages:
        return None, 'no messages'

    pending_reply = None
    if last_assistant_message and last_assistant_message.strip():
        if not _reply_in_current_turn(messages, last_assistant_message):
            pending_reply = last_assistant_message.strip()

    first_ts = messages[0].get('timestamp', '')
    last_ts = messages[-1].get('timestamp', '')
    message_count = len(messages)
    if pending_reply:
        last_ts = datetime.now().astimezone().isoformat()
        message_count += 1
    project_name = os.path.basename(cwd) if cwd else 'unknown'

    md = []
    md.append('# Conversation Log')
    md.append('')
    md.append(f'- **Session ID**: `{session_id}`')
    md.append(f'- **Project**: `{project_name}` (`{cwd}`)')
    md.append(f'- **Started**: {format_timestamp(first_ts)}')
    md.append(f'- **Last updated**: {format_timestamp(last_ts)}')
    md.append(f'- **Messages**: {message_count}')
    md.append('')
    md.append('---')
    md.append('')

    for msg in messages:
        role = msg.get('type', '')
        timestamp = format_timestamp(msg.get('timestamp', ''))
        content = msg.get('message', {}).get('content', '')
        thinking, text = extract_content(content)

        if role == 'user':
            if _is_tool_result_only(content):
                if not text.strip():
                    continue
                md.append(f'## Tool Output `{timestamp}`')
                md.append('')
                md.append(text.strip())
                md.append('')
            else:
                # Strip internal system tags injected by Claude Code
                if '<system-reminder>' in text or '<ide_' in text:
                    text = re.sub(r'<[^>]+>.*?</[^>]+>', '', text, flags=re.DOTALL).strip()
                if not text.strip():
                    continue
                md.append(f'## User `{timestamp}`')
                md.append('')
                md.append(text.strip())
                md.append('')

        elif role == 'assistant':
            if not text.strip() and not thinking:
                continue
            md.append(f'## Claude `{timestamp}`')
            md.append('')
            if thinking:
                md.append('<details>')
                md.append('<summary>Thinking</summary>')
                md.append('')
                md.append(thinking.strip())
                md.append('')
                md.append('</details>')
                md.append('')
            if text.strip():
                md.append(text.strip())
            md.append('')

    if pending_reply:
        md.append(f'## Claude `{format_timestamp(last_ts)}`')
        md.append('')
        md.append(pending_reply)
        md.append('')

    markdown = '\n'.join(md)
    if REDACT_ENABLED:
        markdown = redact_secrets(markdown)
    return markdown, None


def _is_tool_result_only(content):
    return (
        isinstance(content, list) and len(content) > 0 and
        all(isinstance(i, dict) and i.get('type') == 'tool_result'
            for i in content if isinstance(i, dict))
    )


def _reply_in_current_turn(messages, reply):
    """Return True if ``reply`` already appears in the transcript's latest turn.

    The latest turn is everything after the last real user prompt (tool results
    don't count). Whitespace is normalized so block-joining differences don't
    cause a duplicate.
    """
    def norm(s):
        return ' '.join(s.split())

    target = norm(reply)
    texts = []
    for msg in reversed(messages):
        content = msg.get('message', {}).get('content', '')
        if msg.get('type') == 'user' and not _is_tool_result_only(content):
            break
        if msg.get('type') == 'assistant' and isinstance(content, list):
            texts.extend(
                item.get('text', '') for item in content
                if isinstance(item, dict) and item.get('type') == 'text'
            )
    return target in norm('\n'.join(reversed(texts)))


def get_date_prefix(entries):
    """Return the first user/assistant timestamp formatted for a filename."""
    for entry in entries:
        if entry.get('type') in ('user', 'assistant') and entry.get('timestamp'):
            try:
                dt = datetime.fromisoformat(
                    entry['timestamp'].replace('Z', '+00:00')
                ).astimezone()
                return dt.strftime('%Y-%m-%d_%H-%M-%S')
            except Exception:
                break
    return datetime.now().strftime('%Y-%m-%d_%H-%M-%S')


def _make_title_slug(text, max_length=80):
    """Convert raw text to a filename-safe slug, preserving Korean characters."""
    # Remove @ file references (e.g. @app/composables/foo.ts)
    text = re.sub(r'@\S+', '', text)
    # Strip leading Markdown heading symbols (e.g. "## Title" → "Title")
    text = re.sub(r'^#+\s*', '', text.lstrip())
    # Remove XML-like tag pairs iteratively to handle nesting
    # (e.g. <task-notification><task-id>...</task-id>...</task-notification>)
    for _ in range(8):
        cleaned = re.sub(r'<[^>]+>.*?</[^>]+>', '', text, flags=re.DOTALL)
        if cleaned == text:
            break
        text = cleaned
    # Remove any remaining unpaired tags
    text = re.sub(r'<[^>]+/?>', '', text)
    # Take first non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            text = line
            break
    else:
        text = text.strip()
    # Remove filesystem-unsafe characters (keep Korean, alphanumeric, common punctuation)
    text = re.sub(r'[\\/:*?"<>|\x00]', '', text)
    # Collapse whitespace to hyphen
    text = re.sub(r'\s+', '-', text.strip())
    text = text.strip('-.')
    # Truncate to max_length characters (not bytes — macOS/Linux handle UTF-8 filenames)
    if len(text) > max_length:
        text = text[:max_length].rstrip('-.')
    return text


# Prefixes (lower-cased) that indicate auto-injected context, not a real user message.
_SKIP_PREFIXES = (
    'this session is being continued from a previous conversation',
    'continue from where you left off',
    'base directory for this skill',
    '[image:',
    '[request interrupted',   # "[Request interrupted by user for tool use]"
    'the user just ran ',     # skill execution notification ("The user just ran insights…")
)


def _extract_user_title_slug(entries):
    """Scan user messages and return the first meaningful one as a slug.

    - Skips messages that are purely tool results.
    - Within each user message, scans ALL text items (not just the first),
      skipping items that start with XML-like system tags.
    - Skips known auto-injected context strings.
    """
    for entry in entries:
        if entry.get('type') != 'user':
            continue

        content = entry.get('message', {}).get('content', '')

        if isinstance(content, str):
            candidates = [content.strip()]
        elif isinstance(content, list):
            if _is_tool_result_only(content):
                continue
            # Gather all text items in order
            candidates = [
                item.get('text', '').strip()
                for item in content
                if isinstance(item, dict) and item.get('type') == 'text'
                and item.get('text', '').strip()
            ]
        else:
            continue

        for text in candidates:
            # Skip XML-block injections (ide_opened_file, task-notification, …)
            if text.startswith('<'):
                continue
            # Skip known auto-injected context strings
            if text.lower().startswith(_SKIP_PREFIXES):
                continue
            slug = _make_title_slug(text, max_length=50)
            if slug:
                return slug
    return None


def get_title_slug(entries):
    """Return a filename-safe slug representing the session topic.

    Strategy (in priority order):
    1. ``ai-title`` entry – Claude Code's own AI-generated session title.
       Present in recent versions; most accurate and concise.
    2. First meaningful user message – fallback for older sessions.
    """
    for entry in entries:
        if entry.get('type') == 'ai-title':
            title = (entry.get('aiTitle') or '').strip()
            if title:
                # ai-title is already a concise phrase generated by Claude Code;
                # use a high ceiling so it is never truncated in practice.
                return _make_title_slug(title, max_length=120)

    return _extract_user_title_slug(entries)


def _wait_for_stable_transcript(transcript_path, interval=0.2, max_wait=3):
    """Wait briefly until the transcript file size stops changing.

    The transcript is flushed asynchronously, so give pending writes a moment
    to land. Returns after two consecutive equal readings or ``max_wait``.
    """
    deadline = time.monotonic() + max_wait
    prev_size = None
    while True:
        try:
            size = os.path.getsize(transcript_path)
        except OSError:
            return
        if size == prev_size or time.monotonic() >= deadline:
            return
        prev_size = size
        time.sleep(interval)


def main():
    try:
        hook_data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    transcript_path = hook_data.get('transcript_path', '')
    session_id = hook_data.get('session_id', 'unknown')
    cwd = hook_data.get('cwd', '')

    if not transcript_path or not os.path.exists(transcript_path):
        sys.exit(0)

    _wait_for_stable_transcript(transcript_path)

    try:
        entries = load_entries(transcript_path)
    except Exception:
        sys.exit(0)

    markdown, error = entries_to_markdown(
        entries, session_id, cwd,
        last_assistant_message=hook_data.get('last_assistant_message'),
    )
    if error or not markdown:
        sys.exit(0)

    project_name = os.path.basename(cwd) if cwd else 'unknown'
    logs_dir = os.path.join(
        os.path.expanduser('~/.claude/conversation-logs'), project_name
    )
    os.makedirs(logs_dir, mode=0o700, exist_ok=True)

    date_prefix = get_date_prefix(entries)
    session_short = session_id[:8] if len(session_id) >= 8 else session_id

    # Derive a human-readable title from the first user message
    title_slug = get_title_slug(entries)
    new_filename = (
        f'{date_prefix}_{session_short}_{title_slug}.md'
        if title_slug
        else f'{date_prefix}_{session_short}.md'
    )
    log_path = os.path.join(logs_dir, new_filename)

    # If a log file for this session already exists under a different name
    # (e.g. created before the title was available), remove the old file so
    # there is always exactly one log file per session.
    for existing in os.listdir(logs_dir):
        if existing.endswith('.md') and session_short in existing and existing != new_filename:
            try:
                os.remove(os.path.join(logs_dir, existing))
            except Exception:
                pass

    try:
        # Logs can contain source code and command output; keep them owner-only.
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(markdown)
    except Exception:
        pass

    sys.exit(0)


if __name__ == '__main__':
    main()
