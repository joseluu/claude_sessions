# CLAUDE.md — claude_sessions developer notes

Technical notes gathered by exploring `~/.claude/` during the development of `claude_sessions.py`.

---

## Storage layout

```
~/.claude/
├── projects/
│   ├── -home-alice-myproject/          # one dir per project path
│   │   ├── *.jsonl                     # one file per session
│   │   ├── <session-uuid>/             # optional subdir, same name as the session
│   │   │   ├── subagents/
│   │   │   │   ├── agent-<id>.jsonl   # subagent conversation
│   │   │   │   └── agent-aprompt_suggestion-<id>.jsonl  # tiny suggestion agents
│   │   │   └── tool-results/
│   │   │       └── toolu_<id>.txt     # cached large tool outputs
│   │   ├── memory/                     # optional per-project CLAUDE.md memory
│   │   └── sessions-index.json        # optional index (not always present)
│   └── ...
└── settings.json                       # global user settings
```

---

## Path encoding

Project directory names are derived from the absolute filesystem path:
- Every `/` becomes `-`
- Every `_` also becomes `-`
- The leading `/` becomes a leading `-`

```python
def path_to_key(path: str) -> str:
    return path.replace("/", "-").replace("_", "-")
# /home/alice/hobby_l/robot/pepper  →  -home-alice-hobby-l-robot-pepper
```

**Implication**: underscores are lost in encoding; the reverse mapping is lossy.

---

## Session JSONL format

Each session is a newline-delimited JSON file (`*.jsonl`). Each line is one event.

### Key entry types

| `type` field | Description |
|---|---|
| `file-history-snapshot` | Snapshot of tracked file backups at session start |
| `summary` | Auto-generated session title — field `summary` (string) |
| `user` | User message turn — contains `message.role`, `message.content` |
| `assistant` | Assistant message turn |
| `tool_use` | Tool call |
| `tool_result` | Tool output |

### Entries with session metadata

Any entry that has a `slug` field also carries:

```json
{
  "sessionId": "e7b01dc8-6c4f-4883-8f9d-3a46f83e1b10",
  "slug":      "floating-forging-planet",
  "cwd":       "/home/jluu",
  "timestamp": "2026-02-22T07:23:38.095Z",
  "version":   "2.1.50",
  "gitBranch": "main"
}
```

### Summary entry

```json
{
  "type":     "summary",
  "summary":  "Pepper Robot WiFi Setup & Control",
  "leafUuid": "8c6341bb-5800-45c0-8f34-2e1b923fa078"
}
```

### User message entry

```json
{
  "type": "user",
  "uuid": "...",
  "parentUuid": "...",
  "isSidechain": false,
  "userType": "human",
  "message": {
    "role": "user",
    "content": "..."
    // or content: [ { "type": "text", "text": "..." }, ... ]
  }
}
```

---

## Subagent files

Subagent files live under `<project>/<session-uuid>/subagents/`:

- **Named agents** (`agent-<id>.jsonl`): real Task tool subagents with full conversation history; can be large (tens–hundreds of KB).
- **Prompt suggestion agents** (`agent-aprompt_suggestion-<id>.jsonl`): tiny background agents (~2 KB) used by Claude Code's UI suggestions. Safe to delete freely.
- **Compact agents** (`agent-acompact-<id>.jsonl`): context-compaction subagents.

Removing any subagent file does **not** break session resumption — the parent session JSONL is self-contained.

---

## Tool-result cache files

`<project>/<session-uuid>/tool-results/toolu_<id>.txt`

Large tool outputs (e.g. long Bash stdout) are offloaded here to keep the JSONL manageable. Can be very large (hundreds of KB to MB). Safe to delete; Claude Code will simply not be able to re-display the cached output.

---

## Session association mechanics

- When `claude` starts in a directory, it derives the project key from `cwd` and looks up sessions in `~/.claude/projects/<key>/`.
- A session can be associated with multiple projects by copying the `.jsonl` into multiple project directories. Claude Code will propose it when resuming in any of those directories.
- The `cwd` field *inside* the JSONL reflects where the session was originally started and is not updated when you copy the file — it's informational only.

---

## sessions-index.json (optional)

Some project dirs contain a `sessions-index.json`. Format observed:

```json
[
  {
    "sessionId": "aefc2270-ab16-4496-9fcb-1a4c51deb706",
    "title": "...",
    "timestamp": "...",
    "messageCount": 42
  }
]
```

Not always present; Claude Code regenerates it from the JSONL files if missing. Not updated by this tool — can be safely ignored or deleted.

---

## Parsing strategy used in claude_sessions.py

To avoid loading entire large JSONL files into memory, the parser streams lines and stops early once it has found: `summary`, `slug`/`cwd`/`timestamp`, and the first user message. For very large sessions (>1 MB) this saves significant time.

---

## Known limitations

- `_` and `/` are both encoded as `-` so path decoding is ambiguous (e.g. `hobby_l` and `hobby-l` map to the same key). The tool displays the decoded form with hyphens.
- `sessions-index.json` is not updated by move/remove operations; this is harmless.
- Subagent file handle matching strips the `agent-` prefix to allow matching by the short hex ID shown in Claude Code's UI.
