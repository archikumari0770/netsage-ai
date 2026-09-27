"""
NetSage AI — AI Diagnosis Pipeline (Groq version)

Same job as ai_diagnose.py / ai_diagnose_gemini.py, but calls Groq's API.
Groq's free tier is generous and fast; output format (ai_results.csv) is
identical to the other two, so evaluate.py and dashboard.py work unchanged
no matter which provider you use.

Setup:
    pip install groq
    export GROQ_API_KEY=gsk_...        (get one free at console.groq.com/keys)

Run:
    python ai_diagnose_groq.py                 # all cases
    python ai_diagnose_groq.py --limit 5         # just the first 5
    python ai_diagnose_groq.py --case CASE-002   # a single case by id

This script only calls the AI and records its answer — it never applies a fix.
Human review happens afterwards in review/review_log.csv.
"""

import os
import csv
import json
import time
import argparse

from groq import Groq

MODEL = "openai/gpt-oss-120b"  # llama-3.3-70b-versatile was deprecated by
                                # Groq in 2026; check console.groq.com/docs/models
                                # if this one is retired too
REQUEST_DELAY_SECONDS = 1   # Groq is fast and its free tier is generous, but
                             # a small gap avoids bursting into rate limits
CASES_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "cases.csv")
RESULTS_CSV = os.path.join(os.path.dirname(__file__), "ai_results.csv")

SYSTEM_PROMPT = """You are NetSage AI, a network troubleshooting assistant for Cisco-style lab
networks (Packet Tracer). You help junior engineers connect a symptom to its
root cause. You do NOT have access to the live network — you only see the
symptom, topology note, and show-command output given to you.

Rules:
1. Base every claim on the evidence given. If the evidence is insufficient to
   be confident, say so and set confidence to "low".
2. Quote or reference specific lines from the show-command output as evidence
   — never invent command output you were not given.
3. Identify the most likely OSI layer of the fault (Layer 1, 2, 3, 3/4, or 7).
4. Recommend exactly one next command to run if more evidence is needed, or
   "none" if the evidence already supports a diagnosis.
5. You are a recommendation engine only. A human reviewer must approve, edit,
   or reject your diagnosis before any fix is applied to the lab.
6. Respond with ONLY a single JSON object. No prose before or after it, no
   markdown code fences.

Output schema:
{
  "root_cause": "string",
  "osi_layer": "string",
  "confidence": "low | medium | high",
  "evidence": "string",
  "next_command": "string",
  "fix_steps": ["array of short imperative strings"],
  "concept_tag": "string — short category, e.g. VLAN, DHCP, OSPF, HSRP, STP, VTP, ACL, NAT, Port Security, EtherChannel, DNS, SSH, NTP, Wireless, Routing. Not limited to this list."
}"""


def build_user_message(row: dict) -> str:
    return (
        f"Symptom: {row['symptom']}\n"
        f"Topology note: {row['topology_note']}\n"
        f"Show output:\n{row['show_output']}"
    )


def diagnose_case(client: Groq, row: dict) -> dict:
    completion = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(row)},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=3000,
        reasoning_effort="low",  # gpt-oss models spend part of the token
                                  # budget "thinking" before answering; low
                                  # effort leaves more room for the actual
                                  # JSON output on dense cases
    )
    raw_text = (completion.choices[0].message.content or "").strip()
    cleaned = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        parsed = {
            "root_cause": "PARSE_ERROR",
            "osi_layer": "",
            "confidence": "low",
            "evidence": f"Could not parse model response as JSON: {raw_text[:300]}",
            "next_command": "",
            "fix_steps": [],
            "concept_tag": "",
        }
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--case", type=str, default=None)
    args = parser.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: set GROQ_API_KEY first, e.g. export GROQ_API_KEY=gsk_...")
        return
    client = Groq(api_key=api_key)

    with open(CASES_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if args.case:
        rows = [r for r in rows if r["case_id"] == args.case]
    if args.limit:
        rows = rows[: args.limit]

    results_by_id = {}
    # If ai_results.csv already exists, load it first so that re-running a
    # single --case doesn't wipe out everyone else's previously saved results.
    if os.path.exists(RESULTS_CSV):
        with open(RESULTS_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                results_by_id[r["case_id"]] = r

    for i, row in enumerate(rows, 1):
        print(f"[{i}/{len(rows)}] Diagnosing {row['case_id']}...")
        try:
            diagnosis = diagnose_case(client, row)
        except Exception as e:
            print(f"  ERROR: {e}")
            diagnosis = {
                "root_cause": "API_ERROR", "osi_layer": "", "confidence": "low",
                "evidence": str(e), "next_command": "", "fix_steps": [], "concept_tag": "",
            }
        results_by_id[row["case_id"]] = {
            "case_id": row["case_id"],
            "expected_fault": row.get("expected_fault", ""),
            "expected_osi_layer": row.get("osi_layer", ""),
            "ai_root_cause": diagnosis.get("root_cause", ""),
            "ai_osi_layer": diagnosis.get("osi_layer", ""),
            "ai_confidence": diagnosis.get("confidence", ""),
            "ai_evidence": diagnosis.get("evidence", ""),
            "ai_next_command": diagnosis.get("next_command", ""),
            "ai_fix_steps": " | ".join(diagnosis.get("fix_steps", [])),
            "ai_concept_tag": diagnosis.get("concept_tag", ""),
        }
        time.sleep(REQUEST_DELAY_SECONDS)

    results = list(results_by_id.values())
    fieldnames = list(results[0].keys()) if results else []
    with open(RESULTS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"\nSaved {len(results)} total diagnoses (across all runs) to {RESULTS_CSV}")


if __name__ == "__main__":
    main()