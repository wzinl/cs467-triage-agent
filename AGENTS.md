# AGENTS.md

Facts for AI agents working in this repository. Procedures live in skills (`.claude/skills/`).
Hard limits live in the workflow's permissions and safe outputs (`.github/workflows/issue-triage.md`),
not here, because an instruction in this file cannot stop anything.

## What this repository is

A sandbox for an issue-triage agent for the Terraform AWS Provider. It holds a subset of
[hashicorp/terraform-provider-aws](https://github.com/hashicorp/terraform-provider-aws) at commit
`eaaaff0` (2026-10-16): the issue forms, the regex labeler configs, the label taxonomy, the
contributor docs, `CHANGELOG.md` and one service package. On top of that it adds the agent, its
skill and its evaluation. The provider itself does not build here: `go.mod` is present, but most of `internal/` is not.

## Commands

| Task | Command |
|---|---|
| Unit-test the triage scripts | `python3 -m unittest discover .claude/skills/issue-triage/tests` |
| Recompile the workflow after editing `issue-triage.md` | `gh aw compile issue-triage` (gh-aw v0.93.2), then commit both files |
| Rebuild golden-case inputs | `python3 evals/golden/build_cases.py` |
| Replay the golden cases (calls the model) | `REPLAY_RUN=<name> python3 evals/golden/replay.py run` |
| Score a replay, then compare runs for drift | `python3 evals/golden/score.py <name>`, then `score.py compare <run> <run> ...` |
| Duplicate-search recall | `python3 evals/golden/duplicate_recall.py` |
| Repository metrics | `python3 evals/metrics/compute_metrics.py` |
| Upstream build and test (full upstream checkout only) | `make build`, `make test PKG=<service>`, `make quick-fix PKG=<service>` |

Scripts use the Python 3 standard library only, except `evals/golden/replay.py`, which needs PyYAML,
Node.js and a gh-aw source checkout (`GH_AW_JS`).

## Layout

```
.github/workflows/issue-triage.md         agent workflow (source); issue-triage.lock.yml is generated
.github/ISSUE_TEMPLATE/                   upstream issue forms (required fields come from here)
.github/labeler-issue-*.yml               upstream regex labeler (generated upstream; do not edit)
.claude/skills/issue-triage/              triage procedure, scripts, tests, comment format
infrastructure/repository/labels-*.tf     label taxonomy; labels-service.tf is generated upstream
evals/data/                               frozen upstream issue data and the fetch/pack scripts
evals/golden/                             golden cases, replay harness, results and logs
evals/metrics/                            repository metrics and their limits
```

## Triage facts

- Every new issue from a non-maintainer gets `needs-triage` from upstream automation. Only a maintainer removes it.
- The upstream regex labeler adds `service/*` labels from resource names in list items or
  `resource "aws_..."` blocks. It also adds `bug` for `[Bug]:` titles and `crash` for `panic:`. It often over-labels:
  maintainers removed 114 `service/*` labels, on 67 of the 580 non-maintainer issues that got one, from June to October 2026.
- `waiting-response` is removed automatically when the reporter comments.
- Usage questions belong on https://discuss.hashicorp.com/c/terraform-providers/tf-aws. Terraform core
  bugs belong in https://github.com/hashicorp/terraform. Security reports go to https://www.hashicorp.com/security.
- AI-assisted contributions follow `docs/ai-usage.md` and `CONTRIBUTING.md`.

## Conventions

- Change agent behaviour in `.claude/skills/issue-triage/SKILL.md` (procedure) or in the workflow
  frontmatter (limits). Never put a limit only in prose.
- Golden cases are append-only. Add a new case directory instead of editing an `expected.json` after it has been run.
  The commit history shows that every expectation predates its run.
- Keep comments the agent posts short and in the format in `references/comment-format.md`.

## Forbidden changes

- Hand-editing `.github/workflows/*.lock.yml`. Edit the `.md` and recompile.
- Widening the workflow's `permissions`, `network`, `tools`, `safe-outputs` or label allowlist, or
  removing `skip-roles`, `skip-if-match`, `stop-after`, `user-rate-limit`, the credit limits or the timeouts,
  without a CODEOWNERS review.
- Giving the agent any way to close, lock, delete, edit or un-label issues, to merge, or to push.
- Editing generated upstream files (`labeler-issue-triage.yml`, `labels-service.tf`, `CHANGELOG.md`).
- Committing secrets or tokens. The only secret is `ANTHROPIC_API_KEY`, stored as an Actions secret.
- Deploying this workflow to a repository you do not maintain.
