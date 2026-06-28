#!/usr/bin/env python3
"""Compute inter-labeler agreement (Cohen's κ) from the git-llm database.

Compares labels assigned by different labelers on the same turns.
Optionally compares against human gold labels from a YAML file.

Usage:
    # Stub vs LLM (no human gold needed)
    python scripts/eval_kappa.py --db eval-run/latest/db.sqlite --chat-id 2

    # All three pairings (with human gold)
    python scripts/eval_kappa.py --db eval-run/latest/db.sqlite --chat-id 2 \
        --gold docs/evaluation/gold/label-gold.yaml
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import yaml


def _load_labels_by_labeler(
    conn: sqlite3.Connection, chat_id: int
) -> dict[str, dict[int, set[str]]]:
    """Return {labeler_name: {turn_idx: {label_names}}}."""
    rows = conn.execute(
        """
        SELECT t.idx, l.name, l.labeler
        FROM labels l
        JOIN turns t ON t.id = l.turn_id
        WHERE t.chat_id = ?
        ORDER BY t.idx
        """,
        (chat_id,),
    ).fetchall()

    out: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for r in rows:
        out[r["labeler"]][r["idx"]].add(r["name"])
    return dict(out)


def _load_gold(path: Path) -> dict[int, set[str]]:
    """Load human gold labels from YAML. Returns {turn_idx: {labels}}."""
    data = yaml.safe_load(path.read_text())
    gold: dict[int, set[str]] = {}
    for entry in data.get("turns", []):
        gold[entry["idx"]] = set(entry.get("gold_labels", []))
    return gold


def _all_label_names() -> list[str]:
    from git_llm.taxonomy import LABELS
    return [s.name for s in LABELS]


def _to_multiclass_vector(
    turn_indices: list[int],
    label_map: dict[int, set[str]],
    all_labels: list[str],
) -> list[int]:
    """Convert per-turn label sets to a flat multiclass vector.

    For Cohen's κ we need one class per turn. Use the FIRST label
    (highest confidence) as the primary class.  Turns with no labels
    get a special '__none__' class.
    """
    classes = all_labels + ["__none__"]
    class_to_idx = {c: i for i, c in enumerate(classes)}
    vector = []
    for idx in turn_indices:
        labels = label_map.get(idx, set())
        if labels:
            # Pick the first label (deterministic, not random)
            primary = sorted(labels)[0]
            vector.append(class_to_idx.get(primary, len(classes) - 1))
        else:
            vector.append(class_to_idx["__none__"])
    return vector


def _to_multilabel_matrix(
    turn_indices: list[int],
    label_map: dict[int, set[str]],
    all_labels: list[str],
) -> list[list[int]]:
    """Convert per-turn label sets to a binary multilabel matrix.

    Each row is a binary vector: 1 if the label is present, 0 otherwise.
    Used for computing exact-match agreement and label-level κ.
    """
    label_to_idx = {l: i for i, l in enumerate(all_labels)}
    matrix = []
    for idx in turn_indices:
        row = [0] * len(all_labels)
        for l in label_map.get(idx, set()):
            if l in label_to_idx:
                row[label_to_idx[l]] = 1
        matrix.append(row)
    return matrix


def _cohens_kappa(v1: list[int], v2: list[int]) -> float:
    """Compute Cohen's κ for two categorical vectors."""
    assert len(v1) == len(v2), "Vectors must be same length"
    n = len(v1)
    if n == 0:
        return 0.0

    # Observed agreement
    agree = sum(1 for a, b in zip(v1, v2) if a == b)
    p_o = agree / n

    # Expected agreement
    from collections import Counter
    c1 = Counter(v1)
    c2 = Counter(v2)
    all_classes = set(c1.keys()) | set(c2.keys())
    p_e = sum((c1.get(k, 0) / n) * (c2.get(k, 0) / n) for k in all_classes)

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1 - p_e)


def _exact_match_rate(
    turn_indices: list[int],
    map_a: dict[int, set[str]],
    map_b: dict[int, set[str]],
) -> float:
    """Fraction of turns where both labelers assigned the exact same set."""
    if not turn_indices:
        return 0.0
    matches = sum(
        1 for idx in turn_indices
        if map_a.get(idx, set()) == map_b.get(idx, set())
    )
    return matches / len(turn_indices)


def _label_bias(label_map: dict[int, set[str]], all_labels: list[str]) -> dict[str, float]:
    """Compute label frequency distribution."""
    total = 0
    counts: dict[str, int] = defaultdict(int)
    for labels in label_map.values():
        for l in labels:
            counts[l] += 1
            total += 1
    if total == 0:
        return {}
    return {l: counts.get(l, 0) / total for l in all_labels}


def evaluate(
    db_path: str,
    chat_id: int,
    gold_path: str | None = None,
) -> dict:
    """Run the full inter-labeler agreement evaluation."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    all_labels = _all_label_names()
    by_labeler = _load_labels_by_labeler(conn, chat_id)

    # Find all labelers
    labeler_names = sorted(by_labeler.keys())
    print(f"Labelers found: {labeler_names}")

    # Find common turn indices (turns labeled by ALL labelers)
    all_indices = set()
    for lm in by_labeler.values():
        all_indices.update(lm.keys())
    common_indices = sorted(all_indices)

    # Focus on user turns for primary comparison
    user_turns = [
        r["idx"] for r in conn.execute(
            "SELECT idx FROM turns WHERE chat_id = ? AND role = 'user' ORDER BY idx",
            (chat_id,),
        ).fetchall()
    ]
    assistant_turns = [
        r["idx"] for r in conn.execute(
            "SELECT idx FROM turns WHERE chat_id = ? AND role = 'assistant' ORDER BY idx",
            (chat_id,),
        ).fetchall()
    ]

    print(f"Total turns with labels: {len(common_indices)}")
    print(f"User turns: {len(user_turns)}")
    print(f"Assistant turns: {len(assistant_turns)}")

    results: dict = {"labelers": labeler_names, "pairings": {}}

    # ── Pairwise comparisons ────────────────────────────────────────────
    pairs_to_compare = []

    # Stub vs LLM
    stub_key = next((k for k in labeler_names if k == "stub"), None)
    llm_key = next((k for k in labeler_names if k.startswith("llm:")), None)

    if stub_key and llm_key:
        pairs_to_compare.append(("stub", "llm", stub_key, llm_key))

    # Load gold if provided
    gold_map = None
    if gold_path:
        gold_map = _load_gold(Path(gold_path))
        if stub_key:
            pairs_to_compare.append(("stub", "human", stub_key, "__gold__"))
        if llm_key:
            pairs_to_compare.append(("llm", "human", llm_key, "__gold__"))

    for name_a, name_b, key_a, key_b in pairs_to_compare:
        map_a = by_labeler.get(key_a, {})
        map_b = gold_map if key_b == "__gold__" else by_labeler.get(key_b, {})

        for role_name, turns in [("user", user_turns), ("assistant", assistant_turns)]:
            if not turns:
                continue
            # Primary: multiclass κ
            primary_a = _to_multiclass_vector(turns, map_a, all_labels)
            primary_b = _to_multiclass_vector(turns, map_b, all_labels)
            kappa_primary = _cohens_kappa(primary_a, primary_b)

            # Master-class κ (coarser)
            from git_llm.taxonomy import BY_NAME
            def to_master(turns, lm):
                mc_map = defaultdict(set)
                for idx, labels in lm.items():
                    mc_map[idx] = {BY_NAME[l].master_class.value for l in labels if l in BY_NAME}
                return mc_map

            mc_a = to_master(turns, map_a)
            mc_b = to_master(turns, map_b)
            mc_classes = sorted({c.value for c in __import__('git_llm.taxonomy', fromlist=['MasterClass']).MasterClass})
            mc_primary_a = _to_multiclass_vector(turns, mc_a, mc_classes)
            mc_primary_b = _to_multiclass_vector(turns, mc_b, mc_classes)
            kappa_mc = _cohens_kappa(mc_primary_a, mc_primary_b)

            # Exact match rate
            exact = _exact_match_rate(turns, map_a, map_b)

            pairing_key = f"{name_a}_vs_{name_b}_{role_name}"
            pairing = {
                "kappa_primary": round(kappa_primary, 3),
                "kappa_master_class": round(kappa_mc, 3),
                "exact_match_rate": round(exact, 3),
                "n_turns": len(turns),
            }
            results["pairings"][pairing_key] = pairing

            print(f"\n  {name_a:>6} vs {name_b:<6} ({role_name}, {len(turns)} turns):")
            print(f"    Primary κ:      {kappa_primary:.3f}")
            print(f"    Master-class κ: {kappa_mc:.3f}")
            print(f"    Exact match:    {exact:.1%}")

    # ── Label bias ──────────────────────────────────────────────────────
    if llm_key:
        bias = _label_bias(by_labeler[llm_key], all_labels)
        top_labels = sorted(bias.items(), key=lambda x: -x[1])[:5]
        print(f"\n  LLM label bias (top 5):")
        for label, freq in top_labels:
            flag = " ⚠️" if freq > 0.40 else ""
            print(f"    {label:<20} {freq:.1%}{flag}")
        results["llm_bias"] = {l: round(f, 3) for l, f in bias.items()}

    conn.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute inter-labeler agreement")
    parser.add_argument("--db", required=True, help="Path to git-llm SQLite database")
    parser.add_argument("--chat-id", type=int, required=True, help="Chat ID")
    parser.add_argument("--gold", help="Path to human gold YAML file (user turns)")
    parser.add_argument("--gold-assistant", help="Path to human gold YAML file (assistant turns)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = evaluate(args.db, args.chat_id, args.gold, args.gold_assistant)

    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
