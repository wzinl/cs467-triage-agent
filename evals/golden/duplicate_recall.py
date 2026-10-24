#!/usr/bin/env python3
"""Offline check of the skill's duplicate search against real maintainer decisions.

For every issue in the study window that maintainers closed as a duplicate and whose first
maintainer comment names the canonical issue ("duplicate of #N"), run the same TF-IDF search
the skill uses, over only the issues that existed when the duplicate was opened, and record
the canonical's rank and score. Also records the top-1 score for issues that were never
marked duplicate, to estimate how often a threshold would raise a false alarm.

Usage: python3 evals/golden/duplicate_recall.py   (writes evals/golden/duplicate_recall.md)
"""
import gzip
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/issue-triage/scripts"))
import triage_checks as tc  # noqa: E402

window = json.load(gzip.open(ROOT / "evals/data/window_issues.json.gz"))
corpus = json.load(gzip.open(ROOT / "evals/data/corpus.json.gz"))
BOTS = {"github-actions", "dosubot", "terraform-aws-provider"}


def canonical(issue):
    for c in issue["comments"]["nodes"]:
        login = (c.get("author") or {}).get("login")
        if login in BOTS or login == (issue.get("author") or {}).get("login"):
            continue
        m = re.search(r"(?i)duplicates?(?: issue)?(?: of)?(?: your other issue,)? #(\d+)", c["body"])
        if m:
            return int(m.group(1))
    return None


def search(issue):
    t = issue["createdAt"]
    earlier = [c for c in corpus if c["created_at"] < t]
    return tc.similar_issues({"number": issue["number"], "title": issue["title"], "body": issue["body"]}, earlier)


tc.TOP_K = 10
rows, negatives = [], []
for i in window:
    if i.get("stateReason") == "DUPLICATE":
        can = canonical(i)
        if not can:
            continue
        hits = search(i)
        rank = next((k + 1 for k, h in enumerate(hits) if h["number"] == can), None)
        score = next((h["score"] for h in hits if h["number"] == can), None)
        rows.append((i["number"], can, rank, score, hits[0]["score"] if hits else 0))
for i in window[::6]:   # every 6th non-duplicate issue, about 120 negatives, to keep runtime short
    if i.get("stateReason") != "DUPLICATE" and not canonical(i):
        hits = search(i)
        negatives.append(hits[0]["score"] if hits else 0)

found5 = sum(1 for r in rows if r[2] and r[2] <= 5)
found1 = sum(1 for r in rows if r[2] == 1)
lines = ["# Duplicate search: offline recall against maintainer decisions", "",
         f"Duplicates with a named canonical: {len(rows)}. Canonical ranked first: {found1}; "
         f"in top 5: {found5}; in top 10: {sum(1 for r in rows if r[2])}.", "",
         "| duplicate | canonical | rank | canonical score | top-1 score |", "|---|---|---|---|---|"]
lines += [f"| #{a} | #{b} | {c or '>10'} | {d if d is not None else '-'} | {e} |" for a, b, c, d, e in rows]
for th in (tc.DUP_POSSIBLE, tc.DUP_LIKELY):
    tp = sum(1 for r in rows if r[3] is not None and r[3] >= th and r[2] and r[2] <= 5)
    fp = sum(1 for s in negatives if s >= th)
    lines.append(f"\nThreshold {th}: {tp}/{len(rows)} canonicals in the top 5 at or above it; "
                 f"{fp}/{len(negatives)} sampled non-duplicates have a top-1 score at or above it.")
lines.append(f"\nNon-duplicate top-1 score median {statistics.median(negatives):.3f}, "
             f"max {max(negatives):.3f} (n={len(negatives)}).")
(Path(__file__).parent / "duplicate_recall.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
