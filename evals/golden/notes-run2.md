## Failure analysis (hand-written)

**Run.** All 20 cases were replayed on 2026-10-24 after the fixes from run1 (commit a896ad3). Model served:
`claude-sonnet-5-5`. CLI 2.1.310. The workflow and lock file are unchanged since run1. The replay's
CHANGELOG.md dropped releases dated on the issue's day, matching the script.

### What the run1 fixes changed

- **06 now passes.** `newer_fixes` listed v6.61.0, and the agent asked for a retest without claiming a fix.
- **20 passes without the leak.** The checks now report v6.59.0 as the latest release, so v6.60.0 no longer
  reaches the agent. It asked for the empty configuration and added `regression` and `waiting-response`.
- **No permission denials** (8 in run1). The agent now writes `plan.json` with the Edit tool, as step 4 says.

### Outcome failures

| Case | What happened | Why | Fixed for run3? |
|---|---|---|---|
| 03 | Same as run1: a retest request instead of #46265 | Search limit (see run1) | No |
| 11 | `noop`, where run1 added `regression` | **A side effect of the case 20 fix.** v6.57.0 was released the day the issue was opened, so the stricter rule hid it. The checks then said the reporter's v6.57.0 was `newer_than_latest_release`, and the agent stopped treating "works on v6.56.0, fails on v6.57.0" as a regression. | Yes. A release dated that day counts when the reporter is on it, because the report shows it was already out. Later releases from the same day stay hidden. There is a unit test. The replay's CHANGELOG.md keeps same-day releases so the script can apply this rule, and a new control check confirms the agent never reads CHANGELOG.md directly. |
| 19 | Same as run1: it asked for the start of the panic, logs and a configuration | Held out; no resource name to match a release note | No |

### Lesson

The fix for one leakage case broke a case that had passed. A full replay after every change caught it.
A spot check of cases 06 and 20 alone would have missed it.
