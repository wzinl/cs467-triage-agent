// Replays the downstream half of the gh-aw safe-outputs pipeline on a recorded outputs.jsonl,
// using gh-aw's own validator and sanitizer, and prints what would reach GitHub.
// It does not call GitHub. Run: node apply_safe_outputs.cjs <outputs.jsonl> <config.json> <issue author>
// GH_AW_JS must point at gh-aw's actions/setup/js directory (the version that compiled the lock file).
const fs = require("fs");
const path = require("path");
const js = process.env.GH_AW_JS;
require(path.join(js, "shim.cjs"));
const { validateLabels } = require(path.join(js, "safe_output_validator.cjs"));
const { sanitizeContent } = require(path.join(js, "sanitize_content.cjs"));
const { normalizeIssueIntentLabelInputs } = require(path.join(js, "issue_intents.cjs"));

const [outputsPath, configPath, author] = process.argv.slice(2);
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const lines = fs.existsSync(outputsPath) ? fs.readFileSync(outputsPath, "utf8").split("\n").filter(Boolean) : [];
const result = { labels: [], comment: null, noop: null, rejected: [] };
const used = {};
for (const line of lines) {
  const msg = JSON.parse(line);
  const key = msg.type;
  const cfg = config[key];
  used[key] = (used[key] || 0) + 1;
  if (!cfg) { result.rejected.push({ type: key, reason: "not enabled" }); continue; }
  if (cfg.max && used[key] > cfg.max) { result.rejected.push({ type: key, reason: `over max ${cfg.max}` }); continue; }
  if (key === "add_labels") {
    // Labels may be plain names or {name, rationale, confidence} objects; add_labels.cjs validates the names.
    const names = normalizeIssueIntentLabelInputs(msg.labels || []).map(l => (typeof l === "string" ? l : l.name));
    const v = validateLabels(names, cfg.allowed || [], cfg.max_labels || 3, cfg.blocked || []);
    if (!v.valid) { result.rejected.push({ type: key, reason: v.error, requested: msg.labels }); continue; }
    const dropped = names.filter(l => !v.value.includes(l));
    if (dropped.length) result.rejected.push({ type: key, reason: "filtered by allowlist/blocklist", dropped });
    result.labels.push(...v.value);
  } else if (key === "add_comment") {
    result.comment = sanitizeContent(msg.body || "", { maxLength: 65000, maxBotMentions: config.max_bot_mentions, allowedAliases: [author] });
  } else if (key === "noop") {
    result.noop = msg.message;
  } else {
    result.rejected.push({ type: key, reason: "reported", message: msg });
  }
}
process.stdout.write(JSON.stringify(result, null, 2) + "\n");
