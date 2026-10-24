# Evaluation

Everything here is offline. Nothing in `evals/` writes to GitHub, and the agent's sparse checkout
does not include this directory, so the agent never sees the expected outcomes.

| Path | What it is |
|---|---|
| `data/` | Frozen read-only data from hashicorp/terraform-provider-aws, fetched 2026-10-24 (`fetch_meta.json`) |
| `metrics/` | Repository metrics that motivate and size the agent (`results.md`) |
| `golden/cases/NN-*/` | 18 golden cases: `input.json` (the event) and `expected.json` (written before any run) |
| `golden/actual/<run>/` | What the agent did in each replay: tool trace, raw safe outputs, what would reach GitHub |
| `golden/logs/<run>/` | Full Claude Code stream-JSON transcripts, one per case |
| `golden/results-<run>.md` | Actual against expected, case by case, with every failure explained |
| `golden/dev-smoke/` | The one development run (case 08) used to debug the harness. It is not scored |
| `golden/duplicate_recall.md` | Offline recall of the duplicate search against 28 maintainer-confirmed duplicates |

## Reproduce

```sh
# 1. Data (optional: the packed files are committed). Needs an authenticated gh; only GraphQL reads.
python3 evals/data/fetch_upstream.py && python3 evals/data/pack.py raw
# 2. Metrics
python3 evals/metrics/compute_metrics.py
# 3. Golden-case inputs (expected.json files are hand-written and never regenerated)
python3 evals/golden/build_cases.py
# 4. Dry-run replay through the compiled workflow (about USD 0.15 per case), then score
GH_AW_JS=<gh-aw v0.93.x checkout>/actions/setup/js REPLAY_RUN=run1 python3 evals/golden/replay.py run
python3 evals/golden/score.py run1
```

## How the replay works

`replay.py` reads `.github/workflows/issue-triage.lock.yml`, not the `.md`, so it tests what would
actually run. For each case it:

1. builds a workspace from the lock file's sparse-checkout paths only;
2. freezes the upstream data at the case's `as_of` time (below) and runs the real
   `prepare_context.py` against a synthetic `issues.opened` event;
3. applies the `skip-roles` rule from the lock file (case 10 is filed by a maintainer, so it is skipped);
4. builds the prompt from the lock file's prompt steps and runs `claude` with the lock file's
   model, `--max-turns`, `--allowed-tools`, `--disallowed-tools` and permission mode;
5. connects gh-aw's own safe-outputs MCP server, so the agent has exactly the tools and limits it
   would have in Actions;
6. passes the recorded outputs through gh-aw's own label validator and content sanitizer
   (`apply_safe_outputs.cjs`), with the lock file's allowed domains, to get what would reach GitHub.

## Leakage controls

- **Issue text.** The body is the text as first submitted. Later edits by the reporter or by a
  maintainer are dropped, using the edit history.
- **Labels.** Only the labels the reporter's issue form added at creation are kept. Every
  maintainer and bot label is dropped.
- **Corpus.** The duplicate-search corpus holds only issues created before `as_of`, with their
  open or closed state recomputed at `as_of`. The corpus never contains labels.
- **Resources and releases.** The known-resource list holds only resources whose docs page existed
  at `as_of`. Release notes come from `CHANGELOG.md`, but only for releases dated on or before `as_of`.
- **Expectations.** Every `expected.json` was committed (5ad9a88) before the first scored run. Its
  `maintainer_history` field records what maintainers actually did, which the agent never sees.

What still leaks: the issue forms, labeler config and docs are from 2026-10-16, not from each case's
date, and the model's training data may include some of these public issues.

## Limits of this dry run

These controls are configured but could not be exercised offline, so they are untested:
`skip-if-match` (the kill switch), `skip-bots`, `stop-after`, the `timeout-minutes` values,
`max-ai-credits` and `max-daily-ai-credits`, the AWF network firewall, the threat-detection job, and the
`safe_outputs` job writing to the real GitHub API. The local Claude Code CLI (2.1.310) is newer than the
pinned one (2.1.300), and the gh-aw JavaScript comes from v0.93.3, while the lock was compiled by
v0.93.2.
