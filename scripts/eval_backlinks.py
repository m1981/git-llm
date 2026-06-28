#!/usr/bin/env python3
"""Evaluate backlink resolution quality on extracted zettels.

Reads zettel frontmatter from a directory and measures:
- Link count and bidirectionality
- Link precision (shared labels between linked zettels)
- Link recall (how many related pairs are actually linked)
- Graph connectivity (isolated nodes)

Usage:
    python scripts/eval_backlinks.py --zettel-dir eval-run/latest/zettel-clean/notes/
    python scripts/eval_backlinks.py --db eval-run/latest/db.sqlite --chat-id 2
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import yaml


def _load_zettels_from_dir(zettel_dir: Path) -> list[dict]:
    """Load zettel metadata from frontmatter."""
    zettels = []
    for f in sorted(zettel_dir.rglob("*.md")):
        text = f.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        end = text.find("---", 3)
        if end < 0:
            continue
        try:
            fm = yaml.safe_load(text[3:end])
        except Exception:
            continue
        if fm:
            fm["_file"] = str(f)
            zettels.append(fm)
    return zettels


def _load_zettels_from_db(db_path: str, chat_id: int) -> list[dict]:
    """Load zettel metadata from the artifacts table, including backlinks."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT zk_id, kind, title, labels, turn_start, turn_end FROM artifacts WHERE chat_id = ?",
        (chat_id,),
    ).fetchall()

    # Load backlinks from artifact_links table
    related_map: dict[str, set[str]] = defaultdict(set)
    try:
        links = conn.execute("""
            SELECT a.zk_id AS from_id, al.linked_zk_id AS to_id
            FROM artifact_links al
            JOIN artifacts a ON a.id = al.artifact_id
            WHERE a.chat_id = ?
        """, (chat_id,)).fetchall()
        for l in links:
            related_map[l["from_id"]].add(l["to_id"])
            related_map[l["to_id"]].add(l["from_id"])  # bidirectional
    except Exception:
        pass  # artifact_links table may not exist

    conn.close()
    zettels = []
    for r in rows:
        zk_id = r["zk_id"]
        zettels.append({
            "id": zk_id,
            "kind": r["kind"],
            "title": r["title"],
            "labels": r["labels"].split(",") if r["labels"] else [],
            "source_turns": list(range(r["turn_start"], r["turn_end"] + 1)),
            "related": sorted(related_map.get(zk_id, set())),
        })
    return zettels


def evaluate(zettels: list[dict]) -> dict:
    """Evaluate backlink quality."""
    n = len(zettels)
    if n < 2:
        print("Not enough zettels to evaluate (< 2)")
        return {"n_zettels": n}

    # Build lookup: id → related ids
    id_to_related: dict[str, set[str]] = defaultdict(set)
    id_to_labels: dict[str, set[str]] = {}
    id_to_title: dict[str, str] = {}

    for z in zettels:
        zk_id = z.get("id", "")
        labels = set(z.get("labels", []))
        related = set(z.get("related", []))
        id_to_labels[zk_id] = labels
        id_to_title[zk_id] = z.get("title", "")[:50]
        id_to_related[zk_id] = related

    # ── Check 1: Every zettel has ≥1 related ────────────────────────────
    isolated = [zk for zk, rel in id_to_related.items() if not rel]
    has_related = n - len(isolated)

    # ── Check 2: Bidirectionality ───────────────────────────────────────
    total_links = sum(len(r) for r in id_to_related.values())
    directed_links = total_links // 2  # each link counted twice if bidirectional

    bidirectional = 0
    broken = 0
    for zk, related in id_to_related.items():
        for r in related:
            if zk in id_to_related.get(r, set()):
                bidirectional += 1
            else:
                broken += 1

    bidir_rate = bidirectional / max(bidirectional + broken, 1)

    # ── Check 3: Link precision ─────────────────────────────────────────
    # Of generated links, fraction where both zettels share ≥1 label
    good_links = 0
    total_checked = 0
    for zk, related in id_to_related.items():
        for r in related:
            if zk < r:  # count each pair once
                total_checked += 1
                shared = id_to_labels.get(zk, set()) & id_to_labels.get(r, set())
                if shared:
                    good_links += 1

    precision = good_links / max(total_checked, 1)

    # ── Check 4: Link recall ────────────────────────────────────────────
    # Of zettel pairs sharing ≥2 labels, fraction that are linked
    expected_pairs = 0
    found_pairs = 0
    zk_ids = list(id_to_labels.keys())
    for i in range(len(zk_ids)):
        for j in range(i + 1, len(zk_ids)):
            a, b = zk_ids[i], zk_ids[j]
            shared = id_to_labels.get(a, set()) & id_to_labels.get(b, set())
            if len(shared) >= 2:
                expected_pairs += 1
                if b in id_to_related.get(a, set()):
                    found_pairs += 1

    recall = found_pairs / max(expected_pairs, 1)

    # ── Summary ─────────────────────────────────────────────────────────
    results = {
        "n_zettels": n,
        "total_directed_links": directed_links,
        "bidirectional_rate": round(bidir_rate, 3),
        "link_precision": round(precision, 3),
        "link_recall": round(recall, 3),
        "isolated_nodes": len(isolated),
        "graph_connected": len(isolated) == 0,
        "expected_pairs_sharing_2plus_labels": expected_pairs,
        "found_pairs": found_pairs,
    }

    print(f"Backlink Resolution:")
    print(f"  Zettels: {n}")
    print(f"  Links: {directed_links}")
    print(f"  Bidirectional: {bidirectional}/{bidirectional + broken} ({bidir_rate:.0%})")
    print(f"  Link precision: {good_links}/{total_checked} ({precision:.0%})")
    print(f"  Link recall: {found_pairs}/{expected_pairs} ({recall:.0%})")
    print(f"  Isolated nodes: {len(isolated)}")
    print(f"  Graph connected: {'✅' if not isolated else '❌'}")

    if isolated:
        print(f"\n  Isolated zettels:")
        for zk in isolated:
            print(f"    - {zk}: {id_to_title.get(zk, '?')}")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate backlink resolution")
    parser.add_argument("--zettel-dir", help="Path to zettel notes directory")
    parser.add_argument("--db", help="Path to git-llm SQLite database")
    parser.add_argument("--chat-id", type=int, help="Chat ID (with --db)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.zettel_dir:
        zettels = _load_zettels_from_dir(Path(args.zettel_dir))
    elif args.db and args.chat_id is not None:
        zettels = _load_zettels_from_db(args.db, args.chat_id)
    else:
        parser.error("Provide --zettel-dir or --db + --chat-id")
        return

    results = evaluate(zettels)
    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
