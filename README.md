# NetSage AI — Project Scaffold

An AI-assisted troubleshooter for Cisco/Packet Tracer lab problems, with a
deterministic rule checker and mandatory human review, per the project brief.

## Folder guide

```
data/cases.csv            Your dataset (append your remaining cases here)
prompts/diagnose_prompt.md Prompt library — system prompt + JSON schema + 3 worked examples
checker/rule_checker.py    Deterministic checks (dup IPs, masks, gateway, interface down, VLAN, routes)
pipeline/ai_diagnose.py    Sends each case to Claude, saves ai_results.csv
pipeline/evaluate.py       Computes AI-vs-expected agreement -> evaluation_summary.json
review/review_log.csv      Human reviewer: Accepted / Edited / Rejected per case
responsible_ai/corrections_log.md   Write-up of 5+ AI corrections (deliverable)
dashboard/dashboard.py     Generates PNG charts into dashboard/output/
```

## 1. Finish the dataset

Keep appending rows to `data/cases.csv` in the existing format:

| column | meaning |
|---|---|
| case_id | e.g. CASE-004 |
| symptom | what the user/PC observes |
| topology_note | brief description of the lab topology relevant to this case |
| show_output | raw Cisco show-command output (multi-line, quote the whole cell) |
| expected_fault | the ground-truth root cause you already know |
| osi_layer | e.g. "Layer 2", "Layer 3/4" |
| concept | one of: VLAN, Gateway, DHCP, DNS, Routing, ACL, NAT, Wireless |
| severity | Low / Medium / High |

Target: 30+ cases covering VLAN, gateway, DHCP, DNS, routing, ACL, NAT, and
wireless issues (per the brief). The 3 sample rows already in the file show
the expected format and can be deleted or kept as real cases.

## 2. Run the rule checker (no AI needed, works right now)

```bash
cd checker
python rule_checker.py ../data/cases.csv
```

## 3. Run AI diagnosis (needs an Anthropic API key)

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
cd pipeline
python ai_diagnose.py              # all cases
python ai_diagnose.py --limit 3    # quick test on first 3
```

This writes `pipeline/ai_results.csv` — one row per case with the AI's
root_cause, osi_layer, confidence, evidence, next_command, fix_steps.

## 4. Evaluate AI vs expected answers

```bash
python evaluate.py
```

Writes `pipeline/evaluation_summary.json` (agreement rate, evidence-use rate,
confidence distribution) — the dashboard reads this.

## 5. Human review

Open `review/review_log.csv`, fill in one row per case: `reviewer_decision`
is `Accepted`, `Edited`, or `Rejected`. For every `Edited`/`Rejected` case,
also add an entry to `responsible_ai/corrections_log.md` explaining what the
AI got wrong — you need at least 5 of these.

## 6. Build the dashboard

```bash
pip install matplotlib
cd dashboard
python dashboard.py
```

Produces `dashboard/output/issue_types.png`, `severity.png`,
`ai_agreement.png`, `review_outcomes.png`.

## 7. Demo video

Show one broken case end-to-end: symptom + show output → AI diagnosis (with
confidence + evidence) → human reviewer decision → fix applied in Packet
Tracer → verification that it's fixed.

## Notes

- The rule checker is heuristic/regex-based over raw show-command text — good
  enough to catch obvious mistakes in lab output, but it's not a full CLI
  parser. If a check misses something in your specific output format, that's
  expected; tighten the regex for your actual command formatting as you go.
- The AI never applies fixes — `fix_steps` in its JSON output is a
  *suggestion* for the human reviewer, consistent with the brief's safety rule.
