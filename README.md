# claude_sessions

A command-line tool to manage [Claude Code](https://claude.ai/claude-code) session associations.

Claude Code stores conversation sessions in `~/.claude/projects/` organised by the filesystem path where the session was started. This tool lets you list, move, copy, link and remove sessions across project directories — useful when you want a session to be proposed when resuming Claude in a different directory.

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## Usage

```
python3 claude_sessions.py <command> [options]
```

### `list` — Browse all sessions

```bash
# All projects, all sessions
python3 claude_sessions.py list

# Filter to one project directory
python3 claude_sessions.py list --project ~/hobby_l/robot/pepper

# Include cwd and first user message
python3 claude_sessions.py list --verbose
```

Output shows, for each session: short UUID, summary title, slug, date, size on disk.

---

### `move` — Move or copy a session to another project

```bash
# Move (removes from source)
python3 claude_sessions.py move e7b01dc8 ~/hobby_l/robot/pepper

# Copy (keeps original in place)
python3 claude_sessions.py move e7b01dc8 ~/hobby_l/robot/pepper --copy
```

The session UUID can be abbreviated to any unique prefix.
The target directory will be created if it does not exist.
Subagent subdirectories (`subagents/`, `tool-results/`) are moved/copied together with the main JSONL.

---

### `link` — Copy all sessions from the current directory to another project

```bash
# Run from the directory whose sessions you want to share
cd ~/some/project
python3 claude_sessions.py link ~/hobby_l/robot/pepper
```

---

### `remove` — Delete a session association or a subagent file

```bash
# Remove one project's association with a session (other copies are kept)
python3 claude_sessions.py remove e7b01dc8 --project ~/hobby_l/robot/pepper

# Remove the last copy of a session (requires --force)
python3 claude_sessions.py remove 0242fe79
# → WARNING: this is the only copy. Re-run with --force to confirm.
python3 claude_sessions.py remove 0242fe79 --force

# Remove a subagent file (safe — main session is unaffected)
python3 claude_sessions.py remove a969122a

# Remove a tool-result cache file
python3 claude_sessions.py remove toolu_01Fj
```

**Safety rules:**

| Target | Behaviour |
|---|---|
| Session with multiple project associations | Removes only the specified association |
| Session with a single association | Blocked unless `--force` is passed |
| Subagent / tool-result file | Always safe, removed immediately |
| Ambiguous prefix | Lists matches, asks for more characters |

---

## Path encoding

Claude Code encodes project paths by replacing `/` and `_` with `-`:

```
/home/alice/hobby_l/robot/pepper  →  -home-alice-hobby-l-robot-pepper
```

The tool accepts both real filesystem paths and already-encoded keys interchangeably.

## Examples

```bash
# Make a session started in ~ also appear when resuming in ~/hobby_l/robot/pepper
python3 claude_sessions.py move e7b01dc8 ~/hobby_l/robot/pepper --copy

# Clean up a tiny stub session permanently
python3 claude_sessions.py remove 535c4df6 --force

# Inspect what's stored for a project before moving there
python3 claude_sessions.py list --project ~/work/myproject --verbose
```
