## Failure analysis (hand-written)

**Run.** All 20 cases were replayed on 2026-10-24 after the case 11 fix (commit after run2). Model served:
`claude-sonnet-5-5`. CLI 2.1.310. The workflow and lock file are unchanged since run1.

**Result: 18/20, no control-check failures.** The two failures were both predicted before any run:

| Case | What happened | Why |
|---|---|---|
| 03 | A retest request (v6.42.0 against v6.50.0) instead of linking #46265 | TF-IDF search limit: the canonical issue misspells the resource, so it ranks 9th. Known and unfixed. |
| 19 | It asked for the start of the panic and a configuration, not a retest on v6.49.0 | Held out. The issue names no `aws_*` resource, so no release note is matched to it. Known and unfixed. |

Case 11 is back to `regression`. Case 20 still never sees v6.60.0, and case 06 still asks for a retest on v6.61.0.

**Stability.** `drift.md` (`score.py compare run1 run2 run3`) puts each case's decision and labels side by
side. Only cases 06, 11 and 20 changed across the three runs, and each change follows a deliberate script or
skill change. The other 17 cases gave identical decisions and labels three times. That is what makes a
golden replay usable as a drift detector: with the configuration fixed, a changed row means the model changed.

[Corrected after run4 and run5: this does not hold.
- Between run3 and run4, the only agent-facing changes were two lines of `AGENTS.md` and new
  `DESIGN.md` and `README.md` files, which the agent never opened. Even so, cases 06, 19 and 20 changed.
- Between run4 and run5, which used the same configuration, case 06 changed.

A changed row can be ordinary variance, so drift has to be judged from pass rates over repeated runs.
See `notes-run5.md`.]

**Cost.** Mean USD 0.08 per agent run (Claude Code's estimate), down from 0.13. The drop starts at case 03
and matches prompt-cache reuse within the run, not a configuration change.
