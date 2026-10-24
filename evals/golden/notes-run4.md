## Failure analysis (hand-written)

**Run.** All 20 cases were replayed on 2026-10-24 on the submitted configuration. Compared with run3, the lock
file adds `user-rate-limit`, which is a pre-activation step only: the agent job and prompt are byte-identical.
The agent's workspace also had a new `DESIGN.md` and `README.md` and two small edits to `AGENTS.md`. The
transcripts show the agent never opened `DESIGN.md` or `README.md`, but `AGENTS.md` is loaded into its context.
Model served: `claude-sonnet-5-5`. CLI 2.1.310.

**Result: 16/20, with no control-check failures.**

| Case | What happened | Why |
|---|---|---|
| 03 | Retest request instead of #46265 | Search limit, as in every run |
| 06 | `noop`. The agent decided the v6.61.0 fix "is for `environment`, not memory `retrieval_config`" | **The model overrode skill rule 3**, which asks for a retest whenever `newer_fixes` names the resource. Runs 2, 3 and 5 followed the rule. The model's reading is plausible, but the maintainer asked for the retest. |
| 19 | Only the `crash` label, with no comment ("form complete, provider current") | Variance. Runs 1–3 asked for the start of the panic. The outcome fails either way, because the expected retest on v6.49.0 needs a resource name to match. |
| 20 | A configuration request and `waiting-response`, but no `regression`, although the version block says "works correctly on v6.58.0" | Variance in a judgement call. Runs 1–3 added `regression`. |

**What this shows.** Cases 06, 19 and 20 changed without any change to a rule. So run3's claim that a fixed
configuration gives fixed decisions does not hold, and it is corrected in `notes-run3.md`. Run5 repeats this
exact configuration to measure the variance.
