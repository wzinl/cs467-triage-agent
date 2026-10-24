#!/usr/bin/env python3
"""Dry-run replay of the golden cases through the same agent configuration the workflow compiles to.

For each case this script:
  1. freezes the world at the case's `as_of`. Only issues opened earlier are kept, with their
     open/closed state at that moment and no labels; only resources documented by then are kept;
  2. builds a clean workspace with only the paths the workflow's sparse checkout fetches, so the
     agent cannot read evals/ (expected outcomes) or anything else outside them;
  3. runs the real prepare step (prepare_context.py) against a synthetic `issues.opened` event;
  4. applies the pre-activation rule the workflow compiles (`skip-roles`), using the reporter's
     author association as the stand-in for their repository role;
  5. runs Claude Code with the model, prompt, --allowed-tools, --disallowed-tools, --max-turns
     and --permission-mode parsed from .github/workflows/issue-triage.lock.yml, with gh-aw's own
     safe-outputs MCP server (v0.93.x source) recording what the agent asks to post;
  6. passes the recorded outputs through gh-aw's label validator and text sanitizer
     (apply_safe_outputs.cjs) to get what would have reached GitHub.

Writes actual/<run>/<case>.json and logs/<run>/<case>.stream.jsonl (run name from $REPLAY_RUN,
default run1). Never calls GitHub.

Usage: python3 evals/golden/replay.py run [case-id ...]      (all cases when none are given)
       python3 evals/golden/replay.py prepare <case-id>     (steps 1-3 plus triage_checks.py; no model call)
Needs: claude (Claude Code CLI) logged in, node, and GH_AW_JS=<gh-aw checkout>/actions/setup/js.
"""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = ROOT / ".github/workflows/issue-triage.lock.yml"
WORKFLOW_MD = ROOT / ".github/workflows/issue-triage.md"
WORK = Path(os.environ.get("REPLAY_WORK", ROOT.parent / "triage-replay"))   # outside the repo and outside /tmp
AGENT_DIR = Path("/tmp/gh-aw/agent")                                          # fixed: the scripts and prompt use it
GH_AW_JS = Path(os.environ.get("GH_AW_JS", "/home/claude/ref/gh-aw/actions/setup/js"))
GH_AW_MD = GH_AW_JS.parent / "md"
MAINTAINER_ASSOC = {"OWNER", "MEMBER", "COLLABORATOR"}
RUN = os.environ.get("REPLAY_RUN", "run1")              # actual/<RUN>/ and logs/<RUN>/, so repeated runs sit side by side
ACTUAL, LOGS = HERE / "actual" / RUN, HERE / "logs" / RUN

lock = yaml.safe_load(LOCK.read_text())
agent_steps = {s.get("name"): s for s in lock["jobs"]["activation"]["steps"]}   # the prompt is built in activation
agent_steps.update({s.get("name"): s for s in lock["jobs"]["agent"]["steps"]})


def step_env(name):
    return agent_steps[name].get("env") or {}


def claude_flags():
    run = agent_steps["Execute Claude Code CLI"]["run"]
    allowed = re.search(r"--allowed-tools '\\''(.*?)'\\''", run).group(1)
    return {"allowed": allowed,
            "disallowed": re.search(r"--disallowed-tools (\S+)", run).group(1),
            "max_turns": re.search(r"--max-turns (\d+)", run).group(1),
            "permission_mode": re.search(r"--permission-mode (\S+)", run).group(1),
            "model": step_env("Execute Claude Code CLI")["ANTHROPIC_MODEL"]}


def sparse_paths():
    co = lock["jobs"]["agent"]["steps"]
    for s in co:
        if str(s.get("uses", "")).startswith("actions/checkout") and (s.get("with") or {}).get("sparse-checkout"):
            return s["with"]["sparse-checkout"].split()
    raise SystemExit("lock file has no sparse checkout")


def build_workspace(dest):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for p in ROOT.iterdir():          # cone-mode sparse checkout always includes root-level files
        if p.is_file():
            shutil.copy2(p, dest / p.name)
    for rel in sparse_paths():
        src = ROOT / rel
        if src.is_dir():
            shutil.copytree(src, dest / rel, dirs_exist_ok=True)
        elif src.is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / rel)


_corpus, _docs = None, None


def build_snapshot(case, dest):
    global _corpus, _docs
    if _corpus is None:
        _corpus = json.load(gzip.open(ROOT / "evals/data/corpus.json.gz"))
        _docs = json.load(gzip.open(ROOT / "evals/data/resource_docs.json.gz"))
    t, number = case["as_of"], case["event"]["issue"]["number"]
    issues = []
    for c in _corpus + case.get("corpus_extra", []):
        if c["created_at"] >= t or c["number"] == number:
            continue
        closed = c.get("closed_at") and c["closed_at"] <= t
        issues.append({**c, "state": "closed" if closed else "open",
                       "state_reason": (c.get("state_reason") or "").lower() or None if closed else None,
                       "closed_at": c.get("closed_at") if closed else None})
    names = sorted({n.removeprefix("data.") for n, when in _docs.items() if when <= t})
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "meta.json").write_text(json.dumps({"as_of": t}))
    (dest / "corpus.json").write_text(json.dumps({"issues": issues}))
    (dest / "resources.txt").write_text("\n".join(names) + "\n")
    return len(issues), len(names)


def prepare(case, ws):
    if AGENT_DIR.exists():
        shutil.rmtree(AGENT_DIR)
    AGENT_DIR.mkdir(parents=True)
    snap = WORK / "snapshot"
    n_corpus, n_res = build_snapshot(case, snap)
    event_path = WORK / "event.json"
    event_path.write_text(json.dumps(case["event"]))
    env = {**os.environ, "GITHUB_EVENT_PATH": str(event_path), "TRIAGE_SNAPSHOT_DIR": str(snap)}
    subprocess.run([sys.executable, ".claude/skills/issue-triage/scripts/prepare_context.py", "--out", str(AGENT_DIR)],
                   cwd=ws, env=env, check=True, capture_output=True, text=True)
    return {"corpus": n_corpus, "resources": n_res}


def build_prompt(number):
    env = step_env("Create prompt with built-in context")
    items = json.loads(env["GH_AW_PROMPT_CONFIG"])["items"]
    parts = []
    for it in items:
        if "file" in it:
            if it["file"] == "mcp_cli_tools_with_safeoutputs_prompt.md":
                continue   # the replay exposes safe outputs over MCP only, not as a CLI on PATH
            parts.append((GH_AW_MD / it["file"]).read_text())
        else:
            text = env[it["content_env"]]
            if "{{#runtime-import" in text:
                body = WORKFLOW_MD.read_text().split("\n---\n", 1)[1]
                text = body.replace("${{ github.event.issue.number }}", str(number))
            parts.append(text)
    return "\n".join(parts)


def safeoutputs_setup(case, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = out_dir / "config.json"
    cfg.write_text(step_env("Generate Safe Outputs Config")["GH_AW_SAFE_OUTPUTS_CONFIG"])
    tenv = step_env("Generate Safe Outputs Tools")
    env = {**os.environ, "GH_AW_TOOLS_META_JSON": tenv["GH_AW_TOOLS_META_JSON"],
           "GH_AW_VALIDATION_JSON": tenv["GH_AW_VALIDATION_JSON"],
           "GH_AW_SAFE_OUTPUTS_TOOLS_SOURCE_PATH": str(GH_AW_JS / "safe_outputs_tools.json"),
           "GH_AW_SAFE_OUTPUTS_CONFIG_PATH": str(cfg), "GH_AW_SAFE_OUTPUTS_TOOLS_PATH": str(out_dir / "tools.json")}
    subprocess.run(["node", "-e", f"require('{GH_AW_JS}/shim.cjs'); require('{GH_AW_JS}/generate_safe_outputs_tools.cjs').main()"],
                   env=env, check=True, capture_output=True)
    outputs = out_dir / "outputs.jsonl"
    outputs.unlink(missing_ok=True)
    mcp = {"mcpServers": {"safeoutputs": {"command": "node", "args": [str(GH_AW_JS / "safe_outputs_mcp_server.cjs")], "env": {
        "GH_AW_SAFE_OUTPUTS": str(outputs), "GH_AW_SAFE_OUTPUTS_CONFIG_PATH": str(cfg),
        "GH_AW_SAFE_OUTPUTS_TOOLS_PATH": str(out_dir / "tools.json"), "GH_AW_MCP_LOG_DIR": str(out_dir / "mcp-logs"),
        "GITHUB_EVENT_NAME": "issues", "GITHUB_EVENT_PATH": str(WORK / "event.json"),
        "GITHUB_REPOSITORY": "replay/terraform-provider-aws-sandbox"}}}}
    (out_dir / "mcp.json").write_text(json.dumps(mcp))
    return cfg, outputs, out_dir / "mcp.json"


def summarize_stream(log_path):
    tools, denials, skill_loaded, scripts, result = [], [], False, [], {}
    for line in log_path.read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for b in ev["message"].get("content", []):
                if b.get("type") == "tool_use":
                    inp = b.get("input", {})
                    tools.append({"tool": b["name"], "input": json.dumps(inp)[:300]})
                    if b["name"] == "Skill" and "issue-triage" in json.dumps(inp):
                        skill_loaded = True
                    if b["name"] == "Bash":
                        scripts.append(inp.get("command", ""))
        if ev.get("type") == "result":
            result = {k: ev.get(k) for k in ("subtype", "num_turns", "total_cost_usd", "duration_ms", "is_error")}
            denials = ev.get("permission_denials", [])
    return {"skill_loaded": skill_loaded, "bash_commands": scripts, "tool_calls": tools,
            "permission_denials": denials, "result": result}


def run_case(cid, flags):
    case = json.loads((HERE / "cases" / cid / "input.json").read_text())
    issue = case["event"]["issue"]
    actual = {"id": cid, "replayed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "model": flags["model"]}
    if issue["author_association"] in MAINTAINER_ASSOC:
        actual.update(skipped="pre-activation skip-roles: reporter is a repository member", applied=None)
        (ACTUAL / f"{cid}.json").write_text(json.dumps(actual, indent=2) + "\n")
        return actual
    ws = WORK / "workspace"
    build_workspace(ws)
    actual["context"] = prepare(case, ws)
    cfg, outputs, mcp = safeoutputs_setup(case, WORK / "safeoutputs")
    home = WORK / "home"
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)
    env = {**os.environ, "HOME": str(home), "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
           "DISABLE_BUG_COMMAND": "1", "BASH_DEFAULT_TIMEOUT_MS": "60000", "BASH_MAX_TIMEOUT_MS": "60000",
           "MCP_TIMEOUT": "120000", "MCP_TOOL_TIMEOUT": "60000", "GH_AW_CLAUDE_DISABLE_REPO_EDITS": "true",
           "GITHUB_WORKSPACE": str(ws)}
    cmd = ["claude", "--print", "--no-chrome", "--strict-mcp-config", "--setting-sources", "project",
           "--model", flags["model"], "--max-turns", flags["max_turns"],
           "--allowed-tools", flags["allowed"], "--disallowed-tools", flags["disallowed"],
           "--permission-mode", flags["permission_mode"], "--output-format", "stream-json", "--verbose",
           "--mcp-config", str(mcp)]
    log_path = LOGS / f"{cid}.stream.jsonl"
    with open(log_path, "w") as log:
        proc = subprocess.run(cmd, input=build_prompt(issue["number"]), cwd=ws, env=env, stdout=log,
                              stderr=subprocess.PIPE, text=True, timeout=20 * 60)
    actual["exit_code"] = proc.returncode
    actual["trace"] = summarize_stream(log_path)
    actual["raw_outputs"] = [json.loads(l) for l in outputs.read_text().splitlines()] if outputs.exists() else []
    allowed_domains = step_env("Ingest agent output").get("GH_AW_ALLOWED_DOMAINS", "")
    applied = subprocess.run(["node", str(HERE / "apply_safe_outputs.cjs"), str(outputs), str(cfg), issue["user"]["login"]],
                             env={**os.environ, "GH_AW_JS": str(GH_AW_JS), "GH_AW_ALLOWED_DOMAINS": allowed_domains},
                             check=True, capture_output=True, text=True).stdout
    actual["applied"] = json.loads(applied)
    for name in ("plan.json", "checks.json"):
        p = AGENT_DIR / name
        if p.exists():
            actual[name.split(".")[0]] = json.loads(p.read_text())
    (ACTUAL / f"{cid}.json").write_text(json.dumps(actual, indent=2) + "\n")
    return actual


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "prepare"):
        raise SystemExit(__doc__)
    WORK.mkdir(parents=True, exist_ok=True)
    ACTUAL.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    if sys.argv[1] == "prepare":
        case = json.loads((HERE / "cases" / sys.argv[2] / "input.json").read_text())
        ws = WORK / "workspace"
        build_workspace(ws)
        print(prepare(case, ws))
        subprocess.run([sys.executable, ".claude/skills/issue-triage/scripts/triage_checks.py"], cwd=ws, check=True)
        return
    flags = claude_flags()
    ids = sys.argv[2:] or sorted(p.name for p in (HERE / "cases").iterdir())
    for cid in ids:
        a = run_case(cid, flags)
        app = a.get("applied") or {}
        print(f"{cid}: skipped={bool(a.get('skipped'))} labels={app.get('labels')} comment={'yes' if app.get('comment') else 'no'} "
              f"noop={'yes' if app.get('noop') else 'no'} skill={a.get('trace', {}).get('skill_loaded')} "
              f"cost={a.get('trace', {}).get('result', {}).get('total_cost_usd')}", flush=True)


if __name__ == "__main__":
    main()
