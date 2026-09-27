"""
NetSage AI — Evaluation

Compares pipeline/ai_results.csv against the expected answers already in
data/cases.csv, and (once you've done human review) against
review/review_log.csv, to produce agreement metrics for the dashboard.

"Agreement" here means: does the AI's concept_tag / osi_layer match the
expected concept/osi_layer for that case? This is a coarse automatic check —
final ground truth on correctness is always the human reviewer's decision in
review_log.csv (Accepted / Edited / Rejected), which the dashboard also reads.

Run:
    python evaluate.py
"""

import os
import re
import csv
import json

RESULTS_CSV = os.path.join(os.path.dirname(__file__), "ai_results.csv")
SUMMARY_JSON = os.path.join(os.path.dirname(__file__), "evaluation_summary.json")


def normalize(text: str) -> str:
    return (text or "").strip().lower()


def extract_layers(text: str) -> set:
    """The real dataset's osi_layer column has inconsistent free text
    (e.g. 'Layer 3 (First-Hop Redundancy / Layer 1-2 uplink dependency)',
    'Layer2/3', 'Layer 3 or Layer 7'). Exact-string matching against the AI's
    much simpler 'Layer 3' answer would almost always fail. Instead, pull out
    every layer number mentioned and compare as a set — a match counts if the
    AI named any layer that's also named in the expected value."""
    return set(re.findall(r'layer\s*([1-7])', (text or "").lower()))


def main():
    if not os.path.exists(RESULTS_CSV):
        print(f"No results file found at {RESULTS_CSV}. Run ai_diagnose.py first.")
        return

    with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    osi_matches = 0
    concept_evidence_present = 0
    confidence_counts = {"low": 0, "medium": 0, "high": 0}
    per_case = []

    for row in rows:
        ai_layers = extract_layers(row["ai_osi_layer"])
        expected_layers = extract_layers(row["expected_osi_layer"])
        osi_match = bool(ai_layers & expected_layers)  # any overlap counts as agreement
        osi_matches += int(osi_match)

        # crude "evidence use" check: did the AI reference something plausibly
        # concrete rather than an empty/placeholder string?
        has_evidence = len(row.get("ai_evidence", "").strip()) > 15
        concept_evidence_present += int(has_evidence)

        conf = normalize(row.get("ai_confidence", ""))
        if conf in confidence_counts:
            confidence_counts[conf] += 1

        per_case.append({
            "case_id": row["case_id"],
            "osi_layer_match": osi_match,
            "has_evidence": has_evidence,
            "ai_confidence": row.get("ai_confidence", ""),
        })

    summary = {
        "total_cases": total,
        "osi_layer_agreement_rate": round(osi_matches / total, 3) if total else 0,
        "evidence_present_rate": round(concept_evidence_present / total, 3) if total else 0,
        "confidence_distribution": confidence_counts,
        "per_case": per_case,
    }

    with open(SUMMARY_JSON, "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary, indent=2))
    print(f"\nSaved summary to {SUMMARY_JSON}")


if __name__ == "__main__":
    main()
