## Failure analysis (hand-written)

**Run.** A second replay of the submitted configuration, identical to run4. It was run to measure run-to-run
variance, not to test a change.

**Result: 17/20, with no control-check failures.**

| Case | What happened | Why |
|---|---|---|
| 03 | Retest request instead of #46265 | Search limit |
| 19 | Only `crash`, with no comment | Same as run4. Not matching a release note to it is the known gap. |
| 20 | A configuration request without `regression` | Same as run4. The model did not treat "works correctly on v6.58.0" as a regression signal. |

Case 06 passed again: the agent followed rule 3.

**Variance on one configuration (runs 4 and 5).** 16 and 17 of 20. Cases 03 and 19 fail in both runs, case 20
fails in both, and case 06 passes in one of the two. Across all five runs (`drift.md`), 16 cases gave the same
decision and labels every time. The four that moved (06, 11, 19, 20) are all cases whose right answer depends on
reading version information. Case 11 moved only because of the run2 script change.

**Proposed, not applied** (more tuning on these cases would make the score less meaningful):
- move rule 3 into `validate_plan.py`, so that a `noop` on a bug report with `newer_fixes` is rejected;
- have `triage_checks.py` report a regression signal (an earlier version named as working), so `regression`
  no longer depends on the model noticing it.

Both are non-judgement checks, which the rule-placement principle in `DESIGN.md` says belong in scripts.
