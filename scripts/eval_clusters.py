#!/usr/bin/env python3
"""Evaluate cross-chat clustering of zettels.

Groups zettels from multiple chats by label overlap (Jaccard similarity),
then measures cluster coherence, cross-chat coverage, and connectivity.

Usage:
    python scripts/eval_clusters.py \
        --dbs eval-run/latest/db.sqlite /tmp/meta-test-kuchnie.sqlite \
        --chat-ids 2 1 \
        --threshold 0.3
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def _load_zettels_from_db(db_path: str, chat_id: int) -> list[dict]:
    """Load zettel metadata from the artifacts table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT zk_id, kind, title, labels, turn_start, turn_end FROM artifacts WHERE chat_id = ?",
        (chat_id,),
    ).fetchall()
    conn.close()
    zettels = []
    for r in rows:
        zettels.append({
            "id": r["zk_id"],
            "kind": r["kind"],
            "title": r["title"],
            "labels": set(r["labels"].split(",")) if r["labels"] else set(),
            "turn_start": r["turn_start"],
            "turn_end": r["turn_end"],
            "source_db": db_path,
            "source_chat_id": chat_id,
        })
    return zettels


def _jaccard(a: set, b: set) -> float:
    if not a | b:
        return 0.0
    return len(a & b) / len(a | b)


def _cluster_zettels(zettels: list[dict], threshold: float) -> list[list[int]]:
    """Agglomerative clustering by label Jaccard similarity.

    Returns list of clusters, where each cluster is a list of zettel indices.
    """
    n = len(zettels)
    # Start with each zettel in its own cluster
    clusters = [[i] for i in range(n)]

    def _cluster_labels(cluster: list[int]) -> set:
        labels = set()
        for i in cluster:
            labels |= zettels[i]["labels"]
        return labels

    changed = True
    while changed:
        changed = False
        best_sim = 0.0
        best_merge = (-1, -1)

        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                li = _cluster_labels(clusters[i])
                lj = _cluster_labels(clusters[j])
                sim = _jaccard(li, lj)
                if sim >= threshold and sim > best_sim:
                    best_sim = sim
                    best_merge = (i, j)

        if best_merge[0] >= 0:
            i, j = best_merge
            clusters[i] = clusters[i] + clusters[j]
            clusters.pop(j)
            changed = True

    return clusters


def evaluate(
    dbs: list[str],
    chat_ids: list[int],
    threshold: float = 0.3,
) -> dict:
    """Run cross-chat clustering evaluation."""
    # Load zettels from all DBs
    all_zettels = []
    chat_labels = {}  # zk_id → "db_name#chat_id"

    for db_path, chat_id in zip(dbs, chat_ids):
        zettels = _load_zettels_from_db(db_path, chat_id)
        db_short = Path(db_path).stem.replace("db", "").strip("-_") or "db"
        for z in zettels:
            chat_labels[z["id"]] = f"{db_short}#{chat_id}"
        all_zettels.extend(zettels)

    n = len(all_zettels)
    if n < 2:
        print("Not enough zettels to cluster (< 2)")
        return {"n_zettels": n}

    print(f"Cross-Chat Clustering (threshold={threshold}):")
    print(f"  Total zettels: {n}")
    for db_path, chat_id in zip(dbs, chat_ids):
        count = sum(1 for z in all_zettels if z["source_db"] == db_path and z["source_chat_id"] == chat_id)
        print(f"    {Path(db_path).name} chat {chat_id}: {count} zettels")

    # Cluster
    clusters = _cluster_zettels(all_zettels, threshold)
    n_clusters = len(clusters)

    # Analyze clusters
    cluster_details = []
    cross_chat_count = 0
    singleton_count = 0
    coherence_scores = []

    for ci, cluster in enumerate(clusters):
        # Cluster labels (union of all zettel labels)
        cluster_labels = set()
        chat_sources = set()
        zettel_titles = []

        for idx in cluster:
            z = all_zettels[idx]
            cluster_labels |= z["labels"]
            chat_source = chat_labels.get(z["id"], "?")
            chat_sources.add(chat_source)
            zettel_titles.append(f"  - {chat_source}: {z['title'][:50]}")

        is_cross_chat = len(chat_sources) >= 2
        if is_cross_chat:
            cross_chat_count += 1
        if len(cluster) == 1:
            singleton_count += 1

        # Intra-cluster coherence: avg pairwise label overlap
        if len(cluster) >= 2:
            pairs = 0
            total_sim = 0.0
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    total_sim += _jaccard(all_zettels[cluster[i]]["labels"], all_zettels[cluster[j]]["labels"])
                    pairs += 1
            coherence = total_sim / pairs if pairs else 0.0
        else:
            coherence = 0.0

        coherence_scores.append(coherence)

        cluster_details.append({
            "id": ci,
            "size": len(cluster),
            "chat_sources": sorted(chat_sources),
            "is_cross_chat": is_cross_chat,
            "coherence": round(coherence, 3),
            "labels": sorted(cluster_labels)[:5],
            "zettels": zettel_titles,
        })

    mean_coherence = sum(coherence_scores) / len(coherence_scores) if coherence_scores else 0.0

    results = {
        "n_zettels": n,
        "n_clusters": n_clusters,
        "cross_chat_clusters": cross_chat_count,
        "singleton_clusters": singleton_count,
        "mean_coherence": round(mean_coherence, 3),
        "threshold": threshold,
        "clusters": cluster_details,
    }

    print(f"\n  Clusters found: {n_clusters}")
    print(f"  Cross-chat clusters: {cross_chat_count}/{n_clusters} ({cross_chat_count/max(n_clusters,1):.0%})")
    print(f"  Mean coherence: {mean_coherence:.3f}")
    print(f"  Singleton clusters: {singleton_count}/{n_clusters} ({singleton_count/max(n_clusters,1):.0%})")

    print(f"\n  Cluster details:")
    for c in cluster_details:
        cross_flag = " 🌐" if c["is_cross_chat"] else ""
        print(f"    Cluster {c['id']} ({c['size']} zettels, coherence={c['coherence']:.2f}){cross_flag}")
        for z in c["zettels"][:5]:
            print(f"      {z}")
        if len(c["zettels"]) > 5:
            print(f"      ... +{len(c['zettels']) - 5} more")

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate cross-chat clustering")
    parser.add_argument("--dbs", nargs="+", required=True, help="Paths to SQLite databases")
    parser.add_argument("--chat-ids", nargs="+", type=int, required=True, help="Chat IDs (one per DB)")
    parser.add_argument("--threshold", type=float, default=0.3, help="Jaccard similarity threshold")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if len(args.dbs) != len(args.chat_ids):
        parser.error("Must provide same number of --dbs and --chat-ids")

    results = evaluate(args.dbs, args.chat_ids, args.threshold)
    if args.json:
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
