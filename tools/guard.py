#!/usr/bin/env python3
"""
Claude Code PreToolUse hook for Bash: the allow-list only ever approves a plain call to one
of the tutor's own scripts.

Claude Code already refuses to let `Bash(python tools/tutor.py *)` approve
`python tools/tutor.py ... && other`, but it auto-approves chained parts it considers
read-only (`ls`, `cat` inside the repo), and its docs don't spell out how `$( )` inside
an allowed command is treated. This hook closes both gaps: if a command mentions a tutor
script and is anything other than one plain call, it answers "ask", which makes Claude Code
prompt even when an allow rule matches. Everything else gets no decision (normal flow).

Reads the hook event JSON on stdin, prints a decision JSON or nothing. Standard library only.
"""
import json
import re
import sys

SCRIPTS = ("tutor", "learner", "log_session", "validate")
MENTION = re.compile(r"tools[/\\](?:%s)\.py" % "|".join(SCRIPTS))
PLAIN_START = re.compile(r"^(?:python3?) tools/(?:%s)\.py(?: |$)" % "|".join(SCRIPTS))


def unsafe_syntax(command):
    """Return a description of the first shell feature that makes `command` more than one
    plain call, or None. Single quotes are literal; double quotes still expand $ and `."""
    quote = None
    i = 0
    while i < len(command):
        c = command[i]
        nxt = command[i + 1] if i + 1 < len(command) else ""
        if quote == "'":
            if c == "'":
                quote = None
        elif quote == '"':
            if c == "\\":
                i += 1
            elif c == '"':
                quote = None
            elif c == "`":
                return "command substitution (`)"
            elif c == "$":
                return "expansion ($) inside double quotes"
        else:
            if c == "\\":
                if nxt in ("\n", ""):
                    return "line continuation"
                i += 1
            elif c in "'\"":
                quote = c
            elif c == "$":
                return "substitution or expansion ($)"
            elif c == "`":
                return "command substitution (`)"
            elif c in ";&|":
                return f"command separator ({c})"
            elif c in "<>":
                return f"redirection ({c})"
            elif c in "()":
                return "subshell"
            elif c in "\n\r":
                return "newline"
        i += 1
    if quote:
        return "unclosed quote"
    return None


def decide(command):
    """None (no opinion) or the reason this command must prompt."""
    if not isinstance(command, str) or not MENTION.search(command):
        return None
    stripped = command.strip()
    if not PLAIN_START.match(stripped):
        return "a tutor script called in an unusual form"
    problem = unsafe_syntax(stripped)
    if problem:
        return f"a tutor script combined with {problem}"
    return None


def main():
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except (OSError, json.JSONDecodeError):
        return 0
    if event.get("tool_name") != "Bash":
        return 0
    reason = decide((event.get("tool_input") or {}).get("command"))
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"Needs your approval: {reason}.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
