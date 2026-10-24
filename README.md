# Issue-triage agent for the Terraform AWS Provider (CS467 sandbox)

This repository configures an existing AI agent (Claude Code, run by
[GitHub Agentic Workflows](https://github.com/github/gh-aw)) to give new issues on
[hashicorp/terraform-provider-aws](https://github.com/hashicorp/terraform-provider-aws) a first-pass triage.
The agent can add at most three allow-listed labels and post one comment per issue. It cannot close, edit,
remove labels, merge or push.

It is a sandbox. The agent has **not** been deployed to the upstream repository, and every test is an
offline replay of real upstream issues. The upstream files here are a subset of upstream at commit `eaaaff0`
(2026-10-16), imported in the first commit and licensed under MPL-2.0 (`LICENSE`). They include the issue
forms, the labeler configs, the label taxonomy, the contributor docs, `CHANGELOG.md` and one service package.

| Start here | |
|---|---|
| [`DESIGN.md`](DESIGN.md) | Why this workflow, its controls and governance, the test findings, the agent bill of materials and the five questions |
| [`.github/workflows/issue-triage.md`](.github/workflows/issue-triage.md) | The agentic workflow: trigger, permissions, tools, safe outputs, budgets and network. `issue-triage.lock.yml` is compiled from it |
| [`AGENTS.md`](AGENTS.md) | Facts and commands for agents, plus forbidden changes |
| [`.claude/skills/issue-triage/`](.claude/skills/issue-triage/SKILL.md) | The triage procedure, its deterministic check scripts and their tests |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | How to change the agent, and the AI-contribution policy |
| [`evals/`](evals/README.md) | Repository metrics, 20 golden cases, replay transcripts and results |

The upstream README is at https://github.com/hashicorp/terraform-provider-aws#readme.
