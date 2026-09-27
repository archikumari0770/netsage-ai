"""
NetSage AI — Dashboard

Reads data/cases.csv, pipeline/ai_results.csv (if present), and
review/review_log.csv (if present), and generates PNG charts summarizing:
  1. Issue-type (concept) counts
  2. Severity distribution
  3. AI vs human agreement (osi_layer match rate)
  4. Human review outcomes (Accepted / Edited / Rejected)

Run:
    pip install matplotlib
    python dashboard.py

Output goes to dashboard/output/*.png
"""

import os
import csv
import json
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE = os.path.dirname(__file__)
CASES_CSV = os.path.join(BASE, "..", "data", "cases.csv")
AI_RESULTS_CSV = os.path.join(BASE, "..", "pipeline", "ai_results.csv")
EVAL_SUMMARY_JSON = os.path.join(BASE, "..", "pipeline", "evaluation_summary.json")
REVIEW_LOG_CSV = os.path.join(BASE, "..", "review", "review_log.csv")
OUTPUT_DIR = os.path.join(BASE, "output")

os.makedirs(OUTPUT_DIR, exist_ok=True)


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chart_issue_types():
    rows = load_csv(CASES_CSV)
    if not rows:
        print("No cases.csv found, skipping issue-type chart.")
        return
    # concept_tag in this dataset is fine-grained (e.g. "OSPF / Hello-Dead Timer
    # Mismatch"), so bucket by the broad category before the first "/" to keep
    # the chart readable. Falls back to the full tag if there's no "/".
    def bucket(tag):
        tag = (tag or "Unknown").strip().lstrip(":").strip()
        return tag.split("/")[0].strip() or "Unknown"

    counts = Counter(bucket(r.get("concept_tag", "")) for r in rows)
    labels, values = zip(*sorted(counts.items(), key=lambda x: -x[1]))

    plt.figure(figsize=(10, 5))
    plt.bar(labels, values, color="#2563eb")
    plt.title("Case Count by Issue Category")
    plt.ylabel("Number of cases")
    plt.xticks(rotation=40, ha="right")
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "issue_types.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved {out}")


def chart_severity():
    rows = load_csv(CASES_CSV)
    if not rows:
        return
    counts = Counter(r.get("severity", "Unknown") or "Unknown" for r in rows)
    order = ["Low", "Medium", "High", "Unknown"]
    labels = [l for l in order if l in counts] + [l for l in counts if l not in order]
    values = [counts[l] for l in labels]
    colors = {"Low": "#22c55e", "Medium": "#f59e0b", "High": "#ef4444", "Unknown": "#94a3b8"}

    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=labels, autopct="%1.0f%%",
            colors=[colors.get(l, "#94a3b8") for l in labels])
    plt.title("Case Severity Distribution")
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "severity.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved {out}")


def chart_ai_agreement():
    if not os.path.exists(EVAL_SUMMARY_JSON):
        print("No evaluation_summary.json found. Run pipeline/evaluate.py after ai_diagnose.py.")
        return
    with open(EVAL_SUMMARY_JSON) as f:
        summary = json.load(f)

    agree = summary.get("osi_layer_agreement_rate", 0) * 100
    disagree = 100 - agree

    plt.figure(figsize=(5, 5))
    plt.pie([agree, disagree], labels=["Agrees with expected", "Disagrees"],
            autopct="%1.0f%%", colors=["#2563eb", "#e2e8f0"])
    plt.title("AI vs Expected — OSI Layer Agreement")
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "ai_agreement.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved {out}")


def chart_review_outcomes():
    rows = load_csv(REVIEW_LOG_CSV)
    if not rows:
        print("No review_log.csv found, skipping review-outcomes chart.")
        return
    counts = Counter(r.get("reviewer_decision", "Unreviewed") or "Unreviewed" for r in rows)
    order = ["Accepted", "Edited", "Rejected", "Unreviewed"]
    labels = [l for l in order if l in counts] + [l for l in counts if l not in order]
    values = [counts[l] for l in labels]
    colors = {"Accepted": "#22c55e", "Edited": "#f59e0b", "Rejected": "#ef4444", "Unreviewed": "#94a3b8"}

    plt.figure(figsize=(6, 5))
    plt.bar(labels, values, color=[colors.get(l, "#94a3b8") for l in labels])
    plt.title("Human Review Outcomes")
    plt.ylabel("Number of cases")
    plt.tight_layout()
    out = os.path.join(OUTPUT_DIR, "review_outcomes.png")
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"Saved {out}")


if __name__ == "__main__":
    chart_issue_types()
    chart_severity()
    chart_ai_agreement()
    chart_review_outcomes()
    print(f"\nAll available charts saved to {OUTPUT_DIR}/")
