# Contributing

This repository is a sandbox: a subset of the Terraform AWS Provider plus an issue-triage agent and
its evaluation. Contributions to the provider itself belong upstream, in
[hashicorp/terraform-provider-aws](https://github.com/hashicorp/terraform-provider-aws). Its
contributor guide is in `docs/`.

## Changes to the triage agent

- **Behaviour.** Change the procedure in `.claude/skills/issue-triage/SKILL.md`. Change the facts in `AGENTS.md`.
- **Limits.** Change the frontmatter of `.github/workflows/issue-triage.md` and run `gh aw compile issue-triage`.
  Commit both the `.md` and the regenerated `.lock.yml` in the same commit.
- Every change to the workflow, the skill or `AGENTS.md` must:
  1. pass `python3 -m unittest discover .claude/skills/issue-triage/tests`;
  2. come with a replay of the golden cases (`python3 evals/golden/replay.py run`, then `score.py`),
     with the new `evals/golden/results.md` committed. A drop in passing cases needs a written reason in the PR;
  3. be reviewed by a code owner (`.github/CODEOWNERS`). A change that widens permissions, tools,
     network access or safe outputs also needs a second maintainer's approval.
- When you add a golden case, write and commit its `expected.json` before you run it.

## AI-contribution policy

This project follows the upstream [AI usage policy](docs/ai-usage.md): transparency, accountability and quality.
The rules below add what applies here, both to people who use AI tools and to the triage agent itself.

**People using AI tools**

- State in the PR description which parts an AI tool wrote or changed. Add `🤖🤖🤖` to the title
  when an agent opened the PR.
- The human who opens the PR owns every line. They must be able to explain it without the tool's help.
- Do not paste AI output into issues or reviews unedited. The maintainers have already had to retract a
  confident but wrong AI-written triage answer (upstream #48821).
- Never give an AI tool repository secrets, or write access it does not need for the task.

**The triage agent**

- It is a bot and says so: every comment ends with a fixed disclosure line, and gh-aw adds a link to the run.
- It only suggests. It may add at most three allow-listed labels and post one comment per issue.
  It cannot close, lock, edit, assign, remove labels, merge or push. These limits are enforced
  by the workflow's permissions and safe outputs, not by its instructions.
- Maintainers make every decision: `needs-triage`, priority, duplicates, closing. Treat a wrong label
  or comment from the agent like any triage mistake. Fix it, then link the issue in a new issue so that
  it can be added to the golden set.
- To stop it at once, add the label `triage-agent-paused` to any issue (see DESIGN.md, Q5).
- Its runs, prompts, tool calls and outputs are kept as workflow artifacts. Its model is pinned in the workflow.

## Reporting a security issue

Do not open a public issue. Follow https://www.hashicorp.com/security for the provider. For this
sandbox, contact the repository owner privately.
