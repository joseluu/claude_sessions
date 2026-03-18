#!/usr/bin/env python3
"""
claude_sessions.py — Manage Claude Code session associations.

Usage:
  python3 claude_sessions.py list [--project PATH] [--verbose]
  python3 claude_sessions.py move <SESSION_ID> <TARGET_DIR> [--copy]
  python3 claude_sessions.py link <TARGET_DIR>   # link current dir's sessions to TARGET_DIR
  python3 claude_sessions.py remove <HANDLE> [--project PATH] [--force]
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
CYAN   = "\033[36m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
BLUE   = "\033[34m"


# ---------------------------------------------------------------------------
# Path encoding / decoding
# ---------------------------------------------------------------------------

def path_to_key(path: str) -> str:
    """Encode a filesystem path to a Claude projects directory name.
    /home/jluu/hobby_l/robot/pepper  ->  -home-jluu-hobby-l-robot-pepper
    Slashes and underscores both become hyphens.
    """
    return path.replace("/", "-").replace("_", "-")


def key_to_path(key: str) -> str:
    """Decode a project directory name back to a best-guess filesystem path.
    -home-jluu-hobby-l-robot-pepper  ->  /home/jluu/hobby-l/robot/pepper
    Note: underscores are lost in encoding; we return the hyphen form.
    """
    return key.replace("-", "/", 1)  # first leading '-' becomes the leading '/'


def find_project_key(real_path: str) -> "str | None":
    """Find the project directory key that best matches real_path."""
    encoded = path_to_key(real_path)
    candidate = CLAUDE_PROJECTS / encoded
    if candidate.exists():
        return encoded
    return None


def resolve_project_key(path_or_key: str) -> str:
    """Accept either a real filesystem path or an already-encoded key."""
    # If it starts with -, it's already a key
    if path_or_key.startswith("-"):
        return path_or_key
    # Otherwise encode it
    return path_to_key(os.path.abspath(path_or_key))


# ---------------------------------------------------------------------------
# Session metadata extraction
# ---------------------------------------------------------------------------

def parse_session(jsonl_path: Path) -> dict:
    """Read a session JSONL and extract useful metadata."""
    meta = {
        "id": jsonl_path.stem,
        "path": jsonl_path,
        "name": None,
        "summary": None,
        "slug": None,
        "cwd": None,
        "timestamp": None,
        "first_user_msg": None,
        "size_kb": jsonl_path.stat().st_size // 1024,
    }

    try:
        with jsonl_path.open(encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return meta

    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        t = entry.get("type")

        if t == "custom-title":
            meta["name"] = entry.get("customTitle")

        if t == "summary" and meta["summary"] is None:
            meta["summary"] = entry.get("summary")

        if meta["slug"] is None and "slug" in entry:
            meta["slug"] = entry["slug"]
            meta["cwd"] = entry.get("cwd")
            ts = entry.get("timestamp")
            if ts:
                meta["timestamp"] = datetime.fromisoformat(
                    ts.replace("Z", "+00:00")
                )

        if meta["first_user_msg"] is None and t == "user":
            msg = entry.get("message", {})
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    for block in content:
                        if block.get("type") == "text":
                            meta["first_user_msg"] = block["text"][:120]
                            break
                elif isinstance(content, str):
                    meta["first_user_msg"] = content[:120]

        # Stop early if we have everything (don't stop for name — it may
        # appear anywhere in the file since /rename can happen at any time)
        if all([meta["summary"], meta["slug"], meta["first_user_msg"], meta["name"]]):
            break

    return meta


def list_project(project_dir: Path, verbose: bool = False) -> "list[dict]":
    """Return session metadata for all JSONL files in a project dir."""
    sessions = []
    for jsonl in sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        sessions.append(parse_session(jsonl))
    return sessions


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def fmt_time(dt) -> str:
    if dt is None:
        return DIM + "unknown" + RESET
    local = dt.astimezone()
    return local.strftime("%Y-%m-%d %H:%M")


def print_session(meta: dict, verbose: bool = False):
    sid   = meta["id"]
    short = sid[:8]
    ts    = fmt_time(meta["timestamp"])
    summary = meta["summary"] or DIM + "(no summary)" + RESET
    slug  = meta["slug"] or ""
    cwd   = meta["cwd"] or ""
    size  = meta["size_kb"]
    first = meta["first_user_msg"] or ""

    name  = meta["name"]
    # Title shown by claude --resume: name > summary > first user message
    if meta["summary"]:
        title = meta["summary"]
    elif first:
        title = first.replace("\n", " ")
    else:
        title = DIM + "(no title)" + RESET

    title_parts = [f"{CYAN}{BOLD}{short}…{RESET}"]
    if name:
        title_parts.append(f"{YELLOW}{BOLD}{name}{RESET}")
    title_parts.append(f"{GREEN}{title}{RESET}")
    print("  " + "  ".join(title_parts))
    print(f"  {DIM}id   :{RESET} {sid}")
    print(f"  {DIM}slug :{RESET} {slug}   {DIM}date:{RESET} {ts}   {DIM}size:{RESET} {size} KB")
    if verbose and cwd:
        print(f"  {DIM}cwd  :{RESET} {cwd}")
    if verbose and first:
        snippet = first.replace("\n", " ")
        print(f"  {DIM}first:{RESET} {snippet}")


def cmd_list(args):
    if not CLAUDE_PROJECTS.exists():
        print(RED + f"Claude projects dir not found: {CLAUDE_PROJECTS}" + RESET)
        sys.exit(1)

    if args.project:
        key = resolve_project_key(args.project)
        project_dirs = [CLAUDE_PROJECTS / key]
    else:
        project_dirs = sorted(CLAUDE_PROJECTS.iterdir())

    found_any = False
    for proj_dir in project_dirs:
        if not proj_dir.is_dir():
            continue
        sessions = list_project(proj_dir, verbose=args.verbose)
        if not sessions:
            continue
        found_any = True

        real_path = key_to_path(proj_dir.name)
        print(f"\n{BOLD}{BLUE}{real_path}{RESET}  {DIM}({proj_dir.name}){RESET}")
        print(f"  {len(sessions)} session(s)")
        print()
        for s in sessions:
            print_session(s, verbose=args.verbose)
            print()

    if not found_any:
        print(YELLOW + "No sessions found." + RESET)


# ---------------------------------------------------------------------------
# Move / copy helpers
# ---------------------------------------------------------------------------

def find_session_globally(session_id: str) -> "list[tuple[Path, Path]]":
    """Return list of (project_dir, jsonl_path) for all matches of session_id."""
    hits = []
    prefix = session_id.lower()
    for proj_dir in CLAUDE_PROJECTS.iterdir():
        if not proj_dir.is_dir():
            continue
        for jsonl in proj_dir.glob("*.jsonl"):
            if jsonl.stem.lower().startswith(prefix):
                hits.append((proj_dir, jsonl))
    return hits


def session_extra_dirs(project_dir: Path, session_id: str) -> "list[Path]":
    """Return any subdirectories that belong to this session (e.g. subagents)."""
    d = project_dir / session_id
    return [d] if d.is_dir() else []


def cmd_move(args):
    session_id = args.session_id
    target_path = args.target_dir
    do_copy = args.copy

    hits = find_session_globally(session_id)
    if not hits:
        print(RED + f"Session not found: {session_id}" + RESET)
        sys.exit(1)

    if len(hits) > 1:
        print(YELLOW + f"Ambiguous session ID prefix '{session_id}' matches:" + RESET)
        for proj_dir, jsonl in hits:
            print(f"  {proj_dir.name} / {jsonl.stem}")
        print("Please provide more characters.")
        sys.exit(1)

    src_proj_dir, src_jsonl = hits[0]
    full_session_id = src_jsonl.stem

    target_key = resolve_project_key(target_path)
    target_proj_dir = CLAUDE_PROJECTS / target_key

    if src_proj_dir == target_proj_dir:
        print(YELLOW + "Source and target are the same directory — nothing to do." + RESET)
        sys.exit(0)

    target_proj_dir.mkdir(parents=True, exist_ok=True)
    dst_jsonl = target_proj_dir / src_jsonl.name

    action = "Copying" if do_copy else "Moving"
    print(f"{BOLD}{action} session {CYAN}{full_session_id[:8]}…{RESET}")
    print(f"  from  {BLUE}{src_proj_dir.name}{RESET}")
    print(f"  to    {BLUE}{target_key}{RESET}")

    # Copy / move the JSONL
    shutil.copy2(src_jsonl, dst_jsonl)
    print(f"  {GREEN}✓{RESET} session file")

    # Copy / move any extra subdirectory (subagents, etc.)
    for extra in session_extra_dirs(src_proj_dir, full_session_id):
        dst_extra = target_proj_dir / extra.name
        shutil.copytree(extra, dst_extra, dirs_exist_ok=True)
        print(f"  {GREEN}✓{RESET} extra dir  {extra.name}/")

    if not do_copy:
        src_jsonl.unlink()
        for extra in session_extra_dirs(src_proj_dir, full_session_id):
            shutil.rmtree(extra)
        print(f"  {GREEN}✓{RESET} removed source")

    print(GREEN + "Done." + RESET)


# ---------------------------------------------------------------------------
# Remove command
# ---------------------------------------------------------------------------

def find_subagent_globally(handle: str) -> "list[tuple[Path, Path, Path]]":
    """Search for subagent/tool-result files matching handle prefix.

    Returns list of (project_dir, session_dir, file_path).
    Matches files under <session_uuid>/subagents/agent-<handle>*.jsonl
    and <session_uuid>/tool-results/<handle>*.
    """
    hits = []
    prefix = handle.lower()
    for proj_dir in CLAUDE_PROJECTS.iterdir():
        if not proj_dir.is_dir():
            continue
        for session_dir in proj_dir.iterdir():
            if not session_dir.is_dir() or session_dir.name == "memory":
                continue
            for sub_file in session_dir.rglob("*"):
                if not sub_file.is_file():
                    continue
                # Strip the "agent-" prefix for matching
                name = sub_file.stem.lower()
                name_no_prefix = name.removeprefix("agent-")
                if name_no_prefix.startswith(prefix) or name.startswith(prefix):
                    hits.append((proj_dir, session_dir, sub_file))
    return hits


def count_session_copies(session_stem: str) -> int:
    """Count how many project dirs contain this session JSONL."""
    count = 0
    for proj_dir in CLAUDE_PROJECTS.iterdir():
        if not proj_dir.is_dir():
            continue
        if (proj_dir / f"{session_stem}.jsonl").exists():
            count += 1
    return count


def cmd_remove(args):
    handle = args.handle
    force  = args.force
    project_filter = args.project

    # ── Try to match a top-level session first ──────────────────────────────
    session_hits = find_session_globally(handle)

    # Filter by project if requested
    if project_filter:
        pkey = resolve_project_key(project_filter)
        session_hits = [(pd, jl) for pd, jl in session_hits
                        if pd.name == pkey]

    if session_hits:
        if len(session_hits) > 1:
            print(YELLOW + f"Ambiguous handle '{handle}' matches sessions:" + RESET)
            for proj_dir, jsonl in session_hits:
                print(f"  {proj_dir.name} / {jsonl.stem}")
            print("Use --project PATH to narrow it down.")
            sys.exit(1)

        proj_dir, jsonl = session_hits[0]
        full_id = jsonl.stem
        copies  = count_session_copies(full_id)
        extra   = session_extra_dirs(proj_dir, full_id)

        print(f"{BOLD}Session:{RESET} {CYAN}{full_id[:8]}…{RESET}")
        print(f"  project : {BLUE}{proj_dir.name}{RESET}")
        if extra:
            sub_files = list(extra[0].rglob("*") if extra else [])
            n_files   = sum(1 for f in sub_files if f.is_file())
            print(f"  extras  : {extra[0].name}/ ({n_files} file(s))")
        print(f"  copies  : {copies} project association(s)")

        if copies == 1 and not force:
            print()
            print(RED + "WARNING: this is the only copy of this session." + RESET)
            print("Deleting it will permanently destroy the conversation.")
            print("Re-run with --force to confirm.")
            sys.exit(1)

        # Proceed
        jsonl.unlink()
        print(f"  {GREEN}✓{RESET} removed {jsonl.name}")
        for d in extra:
            shutil.rmtree(d)
            print(f"  {GREEN}✓{RESET} removed {d.name}/")

        if copies == 1:
            print(RED + "Session permanently deleted." + RESET)
        else:
            print(GREEN + f"Association removed ({copies - 1} copy/copies remain)." + RESET)
        return

    # ── Try to match a subagent / tool-result file ───────────────────────────
    sub_hits = find_subagent_globally(handle)

    if project_filter:
        pkey = resolve_project_key(project_filter)
        sub_hits = [(pd, sd, f) for pd, sd, f in sub_hits if pd.name == pkey]

    if not sub_hits:
        print(RED + f"No session or subagent found matching '{handle}'." + RESET)
        sys.exit(1)

    if len(sub_hits) > 1:
        print(YELLOW + f"Ambiguous handle '{handle}' matches subagent files:" + RESET)
        for pd, sd, f in sub_hits:
            print(f"  {pd.name}/{sd.name}/{f.relative_to(sd)}")
        print("Use --project PATH or provide more characters.")
        sys.exit(1)

    proj_dir, session_dir, sub_file = sub_hits[0]
    rel = sub_file.relative_to(proj_dir)
    kind = "tool-result" if "tool-results" in sub_file.parts else "subagent"

    print(f"{BOLD}Subfile ({kind}):{RESET} {CYAN}{sub_file.name}{RESET}")
    print(f"  session : {session_dir.name[:8]}…")
    print(f"  project : {BLUE}{proj_dir.name}{RESET}")
    print(f"  size    : {sub_file.stat().st_size // 1024} KB")
    print(f"  {DIM}Removing a {kind} file is safe — the main session is unaffected.{RESET}")

    sub_file.unlink()
    print(f"  {GREEN}✓{RESET} removed {rel}")
    print(GREEN + "Done." + RESET)


# ---------------------------------------------------------------------------
# Link: copy all sessions from cwd project to another project
# ---------------------------------------------------------------------------

def cmd_link(args):
    """Copy all sessions from the current directory's project to TARGET_DIR."""
    cwd_key = path_to_key(os.getcwd())
    src_proj_dir = CLAUDE_PROJECTS / cwd_key
    if not src_proj_dir.exists():
        print(RED + f"No Claude sessions found for current directory ({cwd_key})" + RESET)
        sys.exit(1)

    target_key = resolve_project_key(args.target_dir)
    target_proj_dir = CLAUDE_PROJECTS / target_key
    target_proj_dir.mkdir(parents=True, exist_ok=True)

    sessions = list(src_proj_dir.glob("*.jsonl"))
    if not sessions:
        print(YELLOW + "No sessions to copy." + RESET)
        sys.exit(0)

    print(f"{BOLD}Linking {len(sessions)} session(s){RESET}")
    print(f"  from  {BLUE}{cwd_key}{RESET}")
    print(f"  to    {BLUE}{target_key}{RESET}\n")

    for jsonl in sessions:
        dst = target_proj_dir / jsonl.name
        shutil.copy2(jsonl, dst)
        meta = parse_session(jsonl)
        summary = meta["summary"] or "(no summary)"
        print(f"  {GREEN}✓{RESET} {jsonl.stem[:8]}…  {summary}")

        for extra in session_extra_dirs(src_proj_dir, jsonl.stem):
            shutil.copytree(extra, target_proj_dir / extra.name, dirs_exist_ok=True)
            print(f"       extra dir {extra.name}/")

    print(GREEN + "\nDone." + RESET)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Manage Claude Code session associations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s list --project ~/hobby_l/robot/pepper
  %(prog)s list --verbose
  %(prog)s move e7b01dc8 ~/hobby_l/robot/pepper
  %(prog)s move e7b01dc8 ~/hobby_l/robot/pepper --copy
  %(prog)s link ~/hobby_l/robot/pepper
  %(prog)s remove 0242fe79                        # remove session (warns if last copy)
  %(prog)s remove 0242fe79 --force                # remove without confirmation
  %(prog)s remove 0242fe79 --project ~/some/dir   # remove only that project's association
  %(prog)s remove a969122a                        # remove a subagent file (always safe)
        """,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List sessions")
    p_list.add_argument("--project", metavar="PATH",
                        help="Filter to a specific project directory")
    p_list.add_argument("--verbose", "-v", action="store_true",
                        help="Show cwd and first user message")

    # move
    p_move = sub.add_parser("move", help="Move (or copy) a session to another project")
    p_move.add_argument("session_id", help="Session UUID or unique prefix")
    p_move.add_argument("target_dir", help="Target filesystem path or encoded key")
    p_move.add_argument("--copy", action="store_true",
                        help="Copy instead of move (keeps original)")

    # link
    p_link = sub.add_parser("link",
                             help="Copy all sessions from cwd's project to TARGET_DIR")
    p_link.add_argument("target_dir", help="Target filesystem path or encoded key")

    # remove
    p_remove = sub.add_parser(
        "remove",
        help="Remove a session (by UUID prefix) or a subagent/tool-result file (by its handle)",
    )
    p_remove.add_argument(
        "handle",
        help="UUID prefix of a session, or handle of a subagent/tool-result file",
    )
    p_remove.add_argument(
        "--project", metavar="PATH",
        help="Restrict removal to sessions associated with this project directory",
    )
    p_remove.add_argument(
        "--force", action="store_true",
        help="Skip confirmation when removing the last copy of a session",
    )

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "move":
        cmd_move(args)
    elif args.command == "link":
        cmd_link(args)
    elif args.command == "remove":
        cmd_remove(args)


if __name__ == "__main__":
    main()
