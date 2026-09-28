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
import hashlib
import html
import json
import re
import subprocess
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


# Context Claude Code injects into user messages. Only these are removed, so any
# HTML/XML the user actually typed or pasted is preserved.
_INJECTED_TAG_RE = re.compile(
    r'<(system-reminder|ide_[a-z_]+|local-command-caveat)\b[^>]*>.*?</\1>\s*', re.DOTALL
)
_COMMAND_TAGS_RE = re.compile(
    r'(?:<command-message>.*?</command-message>\s*)?'
    r'<command-name>(.*?)</command-name>'
    r'(?:\s*<command-args>(.*?)</command-args>)?',
    re.DOTALL,
)


def _format_slash_command(match):
    name = match.group(1).strip()
    if not name.startswith('/'):
        name = '/' + name
    args = (match.group(2) or '').strip()
    if not args:
        return f'`{name}`'
    if '\n' in args:
        return f'`{name}`\n\n{args}'
    return f'`{name} {args}`'


def clean_user_text(text):
    """Remove injected context tags and render slash-command tags readably."""
    text = _INJECTED_TAG_RE.sub('', text)
    text = _COMMAND_TAGS_RE.sub(_format_slash_command, text)
    return text.strip()


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


def entries_to_markdown(entries, session_id, cwd, project_root=None, last_assistant_message=None):
    """Render transcript entries as a Markdown string.

    ``last_assistant_message`` comes from the Stop hook input. The transcript is
    written asynchronously and may not contain the final reply yet; if so, the
    reply is appended so the log is never missing the last turn.

    Returns:
        (markdown: str | None, error: str | None)
    """
    # Sidechain entries belong to subagents, not the main conversation
    messages = [
        e for e in entries
        if e.get('type') in ('user', 'assistant') and not e.get('isSidechain')
    ]
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
    project_root = project_root or cwd
    project_name = os.path.basename(project_root) if project_root else 'unknown'

    md = []
    md.append('# Conversation Log')
    md.append('')
    md.append(f'- **Session ID**: `{session_id}`')
    md.append(f'- **Project**: `{project_name}` (`{project_root}`)')
    if cwd and cwd != project_root:
        md.append(f'- **Working directory**: `{cwd}`')
    md.append(f'- **Started**: {format_timestamp(first_ts)}')
    md.append(f'- **Last updated**: {format_timestamp(last_ts)}')
    md.append(f'- **Messages**: {message_count}')
    md.append('')
    md.append('---')
    md.append('')

    abandoned = _find_rewound_uuids(entries)
    branch = []  # rendered lines of the current run of rewound messages
    branch_count = 0

    def flush_branch():
        nonlocal branch, branch_count
        if branch:
            md.extend(_details(
                f'Rewound branch ({branch_count} messages, not part of the final conversation)',
                branch,
            ))
            branch, branch_count = [], 0

    for msg in messages:
        lines = _render_message(msg)
        if not lines:
            continue
        if msg.get('uuid') in abandoned:
            branch.extend(lines)
            branch_count += 1
        else:
            flush_branch()
            md.extend(lines)
    flush_branch()

    if pending_reply:
        md.append(f'## Claude `{format_timestamp(last_ts)}`')
        md.append('')
        md.append(pending_reply)
        md.append('')

    markdown = '\n'.join(md)
    if REDACT_ENABLED:
        markdown = redact_secrets(markdown)
    return markdown, None


def _details(summary, body_lines):
    """Wrap Markdown lines in a collapsible <details> block."""
    return ['<details>', f'<summary>{html.escape(summary)}</summary>', ''] + body_lines + ['</details>', '']


def _first_line(text, limit=80):
    skill = re.match(r'Base directory for this skill:\s*(\S+)', text)
    if skill:
        return 'Skill: ' + os.path.basename(skill.group(1).rstrip('/'))
    for line in text.splitlines():
        line = line.strip().lstrip('#').strip()
        if line:
            return line if len(line) <= limit else line[:limit].rstrip() + '…'
    return ''


def _render_message(msg):
    """Return the Markdown lines for one transcript message (empty to skip)."""
    role = msg.get('type', '')
    timestamp = format_timestamp(msg.get('timestamp', ''))
    content = msg.get('message', {}).get('content', '')
    thinking, text = extract_content(content)

    if role == 'user':
        if _is_tool_result_only(content):
            if not text.strip():
                return []
            return [f'## Tool Output `{timestamp}`', '', text.strip(), '']

        text = clean_user_text(text)
        if not text:
            return []
        if msg.get('isCompactSummary'):
            # Summary Claude Code wrote when the context was compacted
            return [f'## Context Compacted `{timestamp}`', ''] + _details(
                'Summary of the earlier conversation given to Claude', [text, '']
            )
        if msg.get('isMeta'):
            # Injected by Claude Code (skill instructions, resume prompts,
            # image metadata, messages from other sessions), not typed by the user
            return _details(f'Context `{timestamp}`: {_first_line(text)}', [text, ''])
        return [f'## User `{timestamp}`', '', text, '']

    if role == 'assistant':
        if not text.strip() and not thinking:
            return []
        lines = [f'## Claude `{timestamp}`', '']
        if thinking:
            lines += _details('Thinking', [thinking.strip(), ''])
        if text.strip():
            lines.append(text.strip())
        lines.append('')
        return lines

    return []


def _is_real_prompt(entry):
    """True for a prompt the user typed (not tool results or injected context)."""
    if entry.get('type') != 'user' or entry.get('isMeta') or entry.get('isCompactSummary'):
        return False
    content = entry.get('message', {}).get('content', '')
    if isinstance(content, str):
        return bool(content.strip())
    return isinstance(content, list) and any(
        isinstance(i, dict) and i.get('type') == 'text' for i in content
    )


def _find_rewound_uuids(entries):
    """Return uuids of messages on branches abandoned by a rewind.

    Rewinding and re-prompting attaches the new prompt to the same parent as
    the prompt it replaces, so a parent with several user-prompt children marks
    a rewind; every earlier sibling's subtree was abandoned. Other forks in the
    tree (e.g. parallel tool calls) are left alone.
    """
    children = {}
    for entry in entries:
        if entry.get('uuid') and entry.get('parentUuid'):
            children.setdefault(entry['parentUuid'], []).append(entry)

    abandoned = set()
    for siblings in children.values():
        prompts = [e for e in siblings if _is_real_prompt(e)]
        for root in prompts[:-1]:
            stack = [root]
            while stack:
                node = stack.pop()
                if node['uuid'] in abandoned:
                    continue
                abandoned.add(node['uuid'])
                stack.extend(children.get(node['uuid'], []))
    return abandoned


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
        if entry.get('isMeta') or entry.get('isCompactSummary') or entry.get('isSidechain'):
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


def get_session_cwd(entries, fallback):
    """Return the directory the session started in.

    Using the first recorded cwd (not the hook's current cwd) keeps a session
    in one log folder even if the working directory changes mid-session.
    """
    for entry in entries:
        if entry.get('type') in ('user', 'assistant') and entry.get('cwd'):
            return entry['cwd']
    return fallback


def resolve_project_root(path):
    """Map a directory to its project root.

    Subdirectories and git worktrees resolve to the main repository root, so
    all sessions of one repo share a folder. Non-git directories map to
    themselves.
    """
    if not path:
        return path
    try:
        out = subprocess.run(
            ['git', '-C', path, 'rev-parse', '--git-common-dir', '--show-toplevel'],
            capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return path
    lines = out.stdout.strip().splitlines()
    if out.returncode != 0 or len(lines) < 2:
        return path
    # realpath so symlinked routes (e.g. /tmp vs /private/tmp) agree
    common_dir = os.path.realpath(os.path.join(path, lines[0]))
    if os.path.basename(common_dir) == '.git':
        # Main checkout or a linked worktree: the repo root owns .git
        return os.path.dirname(common_dir)
    return os.path.realpath(lines[1])


PROJECT_MARKER = '.project-path'


def _claim_logs_dir(logs_dir, project_root):
    """Return True if ``logs_dir`` belongs to ``project_root`` (claiming it if unowned)."""
    marker = os.path.join(logs_dir, PROJECT_MARKER)
    try:
        with open(marker, 'r', encoding='utf-8') as f:
            return f.read().strip() == project_root
    except FileNotFoundError:
        pass
    except Exception:
        return True
    # Unowned: a new folder, or one created before markers existed.
    os.makedirs(logs_dir, mode=0o700, exist_ok=True)
    try:
        with open(marker, 'w', encoding='utf-8') as f:
            f.write(project_root + '\n')
    except Exception:
        pass
    return True


def resolve_logs_dir(base_dir, project_root):
    """Pick the log folder for a project, avoiding basename collisions.

    The first project to use ``<name>/`` owns it; a different project with the
    same basename gets ``<name>-<hash>/``.
    """
    if not project_root:
        return os.path.join(base_dir, 'unknown')
    name = os.path.basename(project_root.rstrip(os.sep)) or 'root'
    logs_dir = os.path.join(base_dir, name)
    if _claim_logs_dir(logs_dir, project_root):
        return logs_dir
    suffix = hashlib.sha1(project_root.encode('utf-8')).hexdigest()[:6]
    logs_dir = os.path.join(base_dir, f'{name}-{suffix}')
    _claim_logs_dir(logs_dir, project_root)
    return logs_dir


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

    session_cwd = get_session_cwd(entries, cwd)
    project_root = resolve_project_root(session_cwd)

    markdown, error = entries_to_markdown(
        entries, session_id, session_cwd,
        project_root=project_root,
        last_assistant_message=hook_data.get('last_assistant_message'),
    )
    if error or not markdown:
        sys.exit(0)

    logs_dir = resolve_logs_dir(
        os.path.expanduser('~/.claude/conversation-logs'), project_root
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
