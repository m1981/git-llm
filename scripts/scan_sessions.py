#!/usr/bin/env python3
"""Scan all pi.dev sessions and rank by meta-test suitability.

Reads every .jsonl under ~/.pi/agent/sessions/*/ and computes per-session
metrics relevant to the git-llm evaluation: user prompt count, label
diversity, pivot/challenge frequency, decision-worthy sequences, and
knowledge extraction potential.

Usage:
    python scripts/scan_sessions.py                   # all sessions
    python scripts/scan_sessions.py --repo kuchnie     # filter by repo substring
    python scripts/scan_sessions.py --top 10           # show top 10
    python scripts/scan_sessions.py --min-prompts 5    # only sessions with ≥5 prompts
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".pi" / "agent" / "sessions"

# ── Lightweight keyword heuristics (no LLM, no taxonomy import) ─────────────

_PIVOT_KW = re.compile(
    r"\b(actually|instead|let'?s switch|pivot|change to|alternatively|"
    r"how about|what if we used|switch to|replace .* with)\b", re.I
)
_CHALLENGE_KW = re.compile(
    r"\b(but |however|disagree|wrong|are you sure|why not|"
    r"that doesn'?t make sense|overkill|too complex)\b", re.I
)
_DECISION_KW = re.compile(
    r"\b(let'?s go with|decided|decision|we'?ll use|agreed|"
    r"final answer|in conclusion|the answer is|"
    r"ADR|architecture decision)\b", re.I
)
_EDUCATIONAL_KW = re.compile(
    r"\b(concept|theory|principle|in essence|fundamentally|"
    r"here'?s how .* works|the key insight|"
    r"the difference between|think of it as)\b", re.I
)
_QUESTION_RE = re.compile(r"\?\s*$", re.MULTILINE)
_DIRECTIVE_RE = re.compile(
    r"\b(please|make|build|generate|write|give me|show me|create|implement|fix|add)\b", re.I
)
_CODE_RE = re.compile(r"```|^\s{4}\S", re.MULTILINE)


@dataclass
class SessionMetrics:
    path: Path
    repo: str
    session_id: str
    timestamp: str
    total_lines: int = 0
    user_prompts: int = 0
    assistant_turns: int = 0
    user_text: list[str] = field(default_factory=list)

    # Derived scores
    pivot_hits: int = 0
    challenge_hits: int = 0
    decision_hits: int = 0
    educational_hits: int = 0
    question_count: int = 0
    directive_count: int = 0
    has_code: bool = False

    @property
    def meta_score(self) -> float:
        """Composite score for meta-test suitability (0–100)."""
        if self.user_prompts < 3:
            return 0.0
        s = 0.0
        s += min(self.user_prompts / 10, 1.0) * 20      # up to 20 pts for prompt count
        s += min(self.pivot_hits, 5) * 4                  # up to 20 pts for pivots
        s += min(self.challenge_hits, 3) * 5              # up to 15 pts for challenges
        s += min(self.decision_hits, 3) * 5               # up to 15 pts for decisions
        s += min(self.educational_hits, 3) * 3            # up to  9 pts for educational
        s += min(self.question_count / 3, 1.0) * 7        # up to  7 pts for questions
        s += (10 if self.has_code else 0)                  # 10 pts for code sharing
        s += min(self.total_lines / 200, 1.0) * 4         # up to  4 pts for length
        return round(s, 1)

    @property
    def label_diversity(self) -> int:
        """How many different 'label types' are present."""
        types = 0
        if self.question_count > 0: types += 1
        if self.directive_count > 0: types += 1
        if self.pivot_hits > 0: types += 1
        if self.challenge_hits > 0: types += 1
        if self.educational_hits > 0: types += 1
        if self.decision_hits > 0: types += 1
        if self.has_code: types += 1
        return types


def _extract_repo(path: Path) -> str:
    """Extract repo name from session dir name like '--Users-michal-PycharmProjects-kuchnie--'."""
    dirname = path.parent.name
    # Strip leading/trailing dashes, then take last meaningful segment
    parts = dirname.strip("-").split("-")
    # Find 'PycharmProjects' and take the next segment
    for i, p in enumerate(parts):
        if p == "PycharmProjects" and i + 1 < len(parts):
            return parts[i + 1]
    return dirname.strip("-")[:30]


def _scan_file(path: Path) -> SessionMetrics | None:
    """Scan a single session JSONL file."""
    repo = _extract_repo(path)
    session_id = ""
    timestamp = ""
    metrics = SessionMetrics(
        path=path, repo=repo, session_id="", timestamp="",
    )

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue

                dtype = d.get("type", "")

                if dtype == "session":
                    session_id = d.get("id", "")
                    timestamp = d.get("timestamp", "")
                    continue

                if dtype != "message":
                    continue

                msg = d.get("message", {})
                role = msg.get("role", "")
                content = msg.get("content", "")

                # Normalize content to string
                if isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "thinking":
                                text_parts.append(block.get("thinking", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    content = "\n".join(text_parts)

                if not isinstance(content, str):
                    continue

                metrics.total_lines += 1

                if role == "user":
                    # Skip tool results (they start with <tool_result> or contain only XML)
                    if content.strip().startswith("<tool_result>") or content.strip().startswith("<function_results>"):
                        continue
                    metrics.user_prompts += 1
                    metrics.user_text.append(content[:500])

                    # Score user content
                    if _QUESTION_RE.search(content):
                        metrics.question_count += 1
                    if _DIRECTIVE_RE.search(content):
                        metrics.directive_count += 1
                    if _PIVOT_KW.search(content):
                        metrics.pivot_hits += 1
                    if _CHALLENGE_KW.search(content):
                        metrics.challenge_hits += 1
                    if _CODE_RE.search(content):
                        metrics.has_code = True

                elif role == "assistant":
                    metrics.assistant_turns += 1
                    if _DECISION_KW.search(content):
                        metrics.decision_hits += 1
                    if _EDUCATIONAL_KW.search(content):
                        metrics.educational_hits += 1

    except Exception as e:
        print(f"  WARN: {path}: {e}", file=sys.stderr)
        return None

    metrics.session_id = session_id
    metrics.timestamp = timestamp
    return metrics


def scan_all_sessions(
    sessions_root: Path,
    repo_filter: str | None = None,
) -> list[SessionMetrics]:
    """Scan all session files, optionally filtering by repo substring."""
    results: list[SessionMetrics] = []
    files = sorted(sessions_root.rglob("*.jsonl"))
    print(f"Scanning {len(files)} session files...", file=sys.stderr)

    for f in files:
        if repo_filter and repo_filter not in f.parent.name:
            continue
        m = _scan_file(f)
        if m and m.user_prompts >= 1:
            results.append(m)

    results.sort(key=lambda m: m.meta_score, reverse=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan pi.dev sessions for meta-test suitability.")
    parser.add_argument("--repo", help="Filter by repo name substring (e.g. 'kuchnie')")
    parser.add_argument("--top", type=int, default=20, help="Show top N sessions (default: 20)")
    parser.add_argument("--min-prompts", type=int, default=1, help="Minimum user prompts to include")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--sessions-dir", type=Path, default=SESSIONS_ROOT)
    args = parser.parse_args()

    sessions = scan_all_sessions(args.sessions_dir, args.repo)
    sessions = [s for s in sessions if s.user_prompts >= args.min_prompts]
    top = sessions[: args.top]

    if args.json:
        out = []
        for s in top:
            out.append({
                "path": str(s.path),
                "repo": s.repo,
                "session_id": s.session_id,
                "timestamp": s.timestamp,
                "meta_score": s.meta_score,
                "user_prompts": s.user_prompts,
                "assistant_turns": s.assistant_turns,
                "total_lines": s.total_lines,
                "label_diversity": s.label_diversity,
                "pivot_hits": s.pivot_hits,
                "challenge_hits": s.challenge_hits,
                "decision_hits": s.decision_hits,
                "educational_hits": s.educational_hits,
                "question_count": s.question_count,
                "directive_count": s.directive_count,
                "has_code": s.has_code,
            })
        json.dump(out, sys.stdout, indent=2)
        return

    # ── Pretty table ────────────────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  TOP {len(top)} SESSIONS BY META-TEST SUITABILITY  "
          f"(scanned {len(sessions)} sessions, filtered: {args.repo or 'all'})")
    print(f"{'='*100}\n")

    print(f"  {'#':>3}  {'Score':>5}  {'Pmts':>4}  {'Piv':>3}  {'Chal':>3}  "
          f"{'Dec':>3}  {'Edu':>3}  {'Q':>3}  {'Code':>4}  "
          f"{'Repo':<25} {'Session ID':<38} {'First prompt (50 chars)'}")
    print(f"  {'─'*3}  {'─'*5}  {'─'*4}  {'─'*3}  {'─'*3}  "
          f"{'─'*3}  {'─'*3}  {'─'*3}  {'─'*4}  "
          f"{'─'*25} {'─'*38} {'─'*50}")

    for i, s in enumerate(top, 1):
        first_prompt = ""
        for t in s.user_text[:1]:
            first_prompt = t.strip().replace("\n", " ")[:50]
        code_flag = "  ✓" if s.has_code else ""
        print(
            f"  {i:>3}  {s.meta_score:>5.1f}  {s.user_prompts:>4}  "
            f"{s.pivot_hits:>3}  {s.challenge_hits:>3}  "
            f"{s.decision_hits:>3}  {s.educational_hits:>3}  "
            f"{s.question_count:>3}  {code_flag:>4}  "
            f"{s.repo:<25} {s.session_id:<38} {first_prompt}"
        )

    print(f"\n  Score legend: pivots(20) + challenges(15) + decisions(15) + "
          f"prompts(20) + educational(9) + questions(7) + code(10) + length(4) = 100 max")
    print(f"  Pmts=user prompts, Piv=pivots, Chal=challenges, Dec=decisions, "
          f"Edu=educational, Q=questions, Code=has code blocks\n")


if __name__ == "__main__":
    main()
