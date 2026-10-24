#!/usr/bin/env python3
"""Collect the inputs the triage agent needs, before the agent starts.

Runs as a deterministic `steps:` entry of .github/workflows/issue-triage.md, outside the
agent's sandbox, with a read-only GITHUB_TOKEN. The agent itself has no GitHub API access;
everything it reads comes from the files written here:

  issue.json      the triggering issue as submitted (from $GITHUB_EVENT_PATH)
  corpus.json     earlier issues for the duplicate check
  resources.txt   resource and data source names that exist in the provider
  plan.json       an empty plan the agent fills in (it may edit files under /tmp only)

Corpus source, in order:
  1. a frozen snapshot directory ($TRIAGE_SNAPSHOT_DIR, default .github/triage-agent/snapshot)
     with corpus.json, resources.txt and meta.json {"as_of": ...}. Used by sandbox replays so
     the agent only sees what existed when the replayed issue was opened.
  2. otherwise the live repository: all open issues plus issues closed in the last 180 days,
     via `gh issue list`, and resource names from website/docs/{r,d}.

Usage: prepare_context.py --out /tmp/gh-aw/agent
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

FIELDS = "number,url,title,body,state,stateReason,createdAt,closedAt"
EMPTY_PLAN = {"decision": None, "labels": [], "comment": None, "duplicate_of": [], "reason": None}


def gh_issues(*args):
    out = subprocess.run(["gh", "issue", "list", "--json", FIELDS, *args],
                         check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def live_corpus(number):
    since = (datetime.now(timezone.utc) - timedelta(days=180)).strftime("%Y-%m-%d")
    seen, issues = set(), []
    for batch in (gh_issues("--state", "open", "--limit", "5000"),
                  gh_issues("--state", "closed", "--search", f"closed:>={since}", "--limit", "3000")):
        for i in batch:
            if i["number"] in seen or i["number"] == number:
                continue
            seen.add(i["number"])
            issues.append({"number": i["number"], "url": i["url"], "title": i["title"],
                           "body": (i.get("body") or "")[:1000], "state": i["state"].lower(),
                           "state_reason": (i.get("stateReason") or "").lower() or None,
                           "created_at": i["createdAt"], "closed_at": i.get("closedAt")})
    return issues


def live_resources():
    names = set()
    for kind in ("r", "d"):
        for path in glob.glob(f"website/docs/{kind}/*.html.markdown"):
            names.add("aws_" + os.path.basename(path).split(".")[0])
    return sorted(names)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    raw = event["issue"]
    issue = {"number": raw["number"], "title": raw.get("title") or "", "body": raw.get("body") or "",
             "author": (raw.get("user") or {}).get("login"),
             "author_association": raw.get("author_association"),
             "labels": [l["name"] for l in raw.get("labels") or []],
             "created_at": raw.get("created_at")}

    snap = os.environ.get("TRIAGE_SNAPSHOT_DIR", ".github/triage-agent/snapshot")
    if os.path.isdir(snap):
        with open(os.path.join(snap, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
        with open(os.path.join(snap, "corpus.json"), encoding="utf-8") as f:
            corpus = json.load(f)["issues"]
        with open(os.path.join(snap, "resources.txt"), encoding="utf-8") as f:
            resources = [l.strip() for l in f if l.strip()]
        issue["as_of"] = meta["as_of"]
        source = f"snapshot {snap} as of {meta['as_of']}"
    else:
        corpus, resources = live_corpus(issue["number"]), live_resources()
        issue["as_of"] = issue["created_at"]
        source = "live repository"

    # The issue text is untrusted. It is stored verbatim for the scripts; the prompt tells the
    # agent to treat it as data. Strip only NUL bytes, which break some JSON consumers.
    issue["title"] = re.sub("\x00", "", issue["title"])
    issue["body"] = re.sub("\x00", "", issue["body"])

    def write(name, obj):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            if isinstance(obj, str):
                f.write(obj)
            else:
                json.dump(obj, f, indent=2)

    write("issue.json", issue)
    write("corpus.json", {"source": source, "issues": corpus})
    write("resources.txt", "\n".join(resources) + "\n")
    write("plan.json", EMPTY_PLAN)
    print(f"prepared issue #{issue['number']}: corpus={len(corpus)} ({source}), resources={len(resources)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
