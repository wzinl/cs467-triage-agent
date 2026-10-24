"""Unit tests for the issue-triage scripts. Run from the repo root: python3 -m unittest discover .claude/skills/issue-triage/tests"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / ".claude/skills/issue-triage/scripts"
sys.path.insert(0, str(SCRIPTS))
import triage_checks as tc  # noqa: E402
import validate_plan as vp  # noqa: E402

tc.REPO = vp.REPO = str(ROOT)
vp.WORKFLOW = str(ROOT / ".github/workflows/issue-triage.md")
FOOTER = vp.FOOTER

BUG = """### Terraform and AWS Provider Version

```console
Terraform v1.15.5
+ provider registry.terraform.io/hashicorp/aws v{ver}
```

### Affected Resource(s) or Data Source(s)

* `aws_s3_bucket`

### Expected Behavior

no drift

### Actual Behavior

drift

### Sample Terraform Configuration

<details open>
<summary>Click to expand configuration</summary>

```hcl

```
</details>

### Steps to Reproduce

apply twice
"""
AS_OF = datetime(2026, 9, 20, tzinfo=timezone.utc)


class Checks(unittest.TestCase):
    def test_release_dated_same_day_is_not_yet_known(self):
        # 6.60.0 is dated 2026-08-13; an issue opened at 02:42 that day must not see it (golden case 20).
        latest = tc.releases(datetime(2026, 8, 13, 2, 42, tzinfo=timezone.utc))[0][0]
        self.assertEqual(latest, "6.59.0")
        self.assertEqual(tc.releases(datetime(2026, 8, 14, tzinfo=timezone.utc))[0][0], "6.60.0")

    def test_reporter_on_same_day_release_counts_as_current(self):
        # Golden case 11: the issue reports v6.57.0 on the day it was released.
        opened = datetime(2026, 8, 13, 2, 42, tzinfo=timezone.utc)
        v = tc.version_check(BUG.format(ver="6.60.0"), opened)
        self.assertEqual((v["latest_release"], v["provider_status"]), ("6.60.0", "current"))
        self.assertEqual(tc.version_check(BUG.format(ver="6.59.0"), opened)["latest_release"], "6.59.0")

    def test_newer_fix_for_named_resource_is_reported(self):
        body = BUG.format(ver="6.59.0").replace("aws_s3_bucket", "aws_network_acl_rule")
        v = tc.version_check(body, datetime(2026, 8, 14, tzinfo=timezone.utc), ["aws_network_acl_rule"])
        self.assertEqual(v["provider_status"], "current")
        self.assertEqual(v["newer_fixes"], ["6.60.0"])

    def test_empty_configuration_is_missing(self):
        f = tc.form_check(BUG.format(ver="6.60.0"))
        self.assertEqual(f["template"], "Report a Bug")
        self.assertIn("Sample Terraform Configuration", f["missing_required"])

    def test_versions(self):
        self.assertEqual(tc.version_check(BUG.format(ver="5.100.0"), AS_OF)["provider_status"], "older_major")
        self.assertEqual(tc.version_check(BUG.format(ver="6.40.0"), AS_OF)["provider_status"], "outdated")
        v = tc.version_check(BUG.format(ver="6.64.0"), AS_OF)
        self.assertEqual((v["provider_status"], v["latest_release"]), ("current", "6.65.0"))
        self.assertEqual(tc.version_check("no version here", AS_OF)["provider_status"], "not_reported")

    def test_release_notes_after_reported_version(self):
        v = tc.version_check(BUG.format(ver="6.60.0"), datetime(2026, 8, 20, tzinfo=timezone.utc), ["aws_bedrockagentcore_harness"])
        self.assertTrue(any(n["version"] == "6.61.0" and "Fix" in n["note"] for n in v["newer_release_notes"]))
        self.assertTrue(all(n["version"] != "6.62.0" for n in v["newer_release_notes"]))   # released after as_of

    def test_services(self):
        s = tc.service_check("aws_s3_bucket drift", BUG.format(ver="6.60.0"))
        self.assertIn("service/s3", s["regex_labeler_would_apply"])
        self.assertEqual(s["primary_service_label"], "service/s3")
        s = tc.service_check("Affected: aws_opensearch_domain.x", "aws_opensearch_domain.aiml_options")
        self.assertEqual((s["regex_labeler_would_apply"], s["primary_service_label"]), ([], "service/opensearch"))

    def test_duplicate_search_ranks_the_same_issue_first(self):
        corpus = [{"number": 1, "title": "aws_s3_bucket lifecycle rule drift", "body": "lifecycle rule drift after apply"},
                  {"number": 2, "title": "aws_iam_role trust policy error", "body": "trust policy"},
                  {"number": 3, "title": "aws_lambda_function timeout", "body": "timeout"}]
        hits = tc.similar_issues({"number": 9, "title": "aws_s3_bucket: lifecycle rule drift", "body": "drift after apply"}, corpus)
        self.assertEqual(hits[0]["number"], 1)


class Plan(unittest.TestCase):
    checks = {"services": {"primary_service_label": "service/opensearch", "regex_labeler_would_apply": ["service/iam", "bug"],
                           "resources_mentioned": [{"name": "aws_opensearch_domain", "service_label": "service/opensearch"}]},
              "similar_issues": [{"number": 77, "score": 0.5, "band": "likely"}]}
    issue = {"number": 9, "author": "reporter", "labels": ["bug"]}

    def errors(self, **plan):
        base = {"decision": "labels", "labels": [], "comment": None, "duplicate_of": [], "reason": "r"}
        return vp.validate({**base, **plan}, self.checks, self.issue)[0]

    def test_valid_plans(self):
        self.assertEqual(self.errors(labels=["service/opensearch"]), [])
        self.assertEqual(self.errors(decision="noop"), [])
        ok = f"Thanks, @reporter. Could you add the configuration?\n\n{FOOTER}"
        self.assertEqual(self.errors(decision="comment", labels=["waiting-response"], comment=ok), [])
        dup = f"Thanks, @reporter. This may be the same as #77.\n\n{FOOTER}"
        self.assertEqual(self.errors(decision="comment", comment=dup, duplicate_of=[77]), [])

    def test_rejected_labels(self):
        self.assertTrue(self.errors(labels=["needs-triage"]))          # blocked
        self.assertTrue(self.errors(labels=["prioritized"]))           # blocked
        self.assertTrue(self.errors(labels=["tests"]))                 # exists, not allowlisted
        self.assertTrue(self.errors(labels=["bug"]))                   # already on the issue
        self.assertTrue(self.errors(labels=["service/iam"]))           # regex labeler adds it
        self.assertTrue(self.errors(labels=["service/s3"]))            # not about this issue
        self.assertTrue(self.errors(labels=["enhancement", "documentation"]))   # two type labels
        self.assertTrue(self.errors(labels=["a", "b", "c", "d"]))
        self.assertTrue(self.errors(labels=["waiting-response"]))      # needs a question

    def test_rejected_comments(self):
        def c(text):
            return self.errors(decision="comment", comment=text)
        self.assertTrue(c("Thanks @reporter."))                                         # no footer
        self.assertTrue(c(f"cc @ewbankkit\n\n{FOOTER}"))                                # mentions a maintainer
        self.assertTrue(c(f"I have closed the stale issues.\n\n{FOOTER}"))              # claims an action
        self.assertTrue(c(f"A maintainer has approved this.\n\n{FOOTER}"))
        self.assertTrue(c(f"Same as #12345.\n\n{FOOTER}"))                              # not a search result
        self.assertTrue(c(f"See https://example.invalid/x\n\n{FOOTER}"))                # domain not allowed
        self.assertTrue(c("x" * 1600 + FOOTER))
        self.assertTrue(self.errors(decision="noop", labels=["bug"]))

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            for name, obj in (("plan.json", {"decision": "noop", "labels": [], "comment": None, "reason": "x"}),
                              ("checks.json", self.checks), ("issue.json", self.issue)):
                Path(d, name).write_text(json.dumps(obj))
            env = {**os.environ, "TRIAGE_DIR": d}
            ok = subprocess.run([sys.executable, str(SCRIPTS / "validate_plan.py")], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, ok.stdout)
            Path(d, "plan.json").write_text("{not json")
            bad = subprocess.run([sys.executable, str(SCRIPTS / "validate_plan.py")], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 1)


class Prepare(unittest.TestCase):
    def test_snapshot_mode(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "snap").mkdir()
            (d / "snap/meta.json").write_text(json.dumps({"as_of": "2026-09-01T00:00:00Z"}))
            (d / "snap/corpus.json").write_text(json.dumps({"issues": [{"number": 1, "title": "t", "body": "b"}]}))
            (d / "snap/resources.txt").write_text("aws_s3_bucket\n")
            (d / "event.json").write_text(json.dumps({"issue": {"number": 5, "title": "T", "body": "B\x00", "user": {"login": "u"},
                                                                 "author_association": "NONE", "labels": [{"name": "bug"}],
                                                                 "created_at": "2026-10-01T00:00:00Z"}}))
            env = {**os.environ, "GITHUB_EVENT_PATH": str(d / "event.json"), "TRIAGE_SNAPSHOT_DIR": str(d / "snap")}
            subprocess.run([sys.executable, str(SCRIPTS / "prepare_context.py"), "--out", str(d / "out")], cwd=ROOT, env=env, check=True,
                           capture_output=True)
            issue = json.loads((d / "out/issue.json").read_text())
            self.assertEqual((issue["as_of"], issue["body"], issue["labels"]), ("2026-09-01T00:00:00Z", "B", ["bug"]))
            self.assertEqual(json.loads((d / "out/plan.json").read_text())["decision"], None)


if __name__ == "__main__":
    unittest.main()
