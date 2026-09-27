# Responsible AI Log

This log documents cases where a human reviewer corrected or rejected the
AI's diagnosis, and why — evidence that human review is a real safety check,
not a rubber stamp, on the NetSage AI pipeline (Groq / openai/gpt-oss-120b).

Reviewer: Nikhil Pratee
Date: 30-08-2026

---

## Entry 1

### Case: C003
- **AI diagnosis:** FastEthernet0/1 on Router3 is not participating in RIP (assumed interface down or set as passive), so routes to Router4 are no longer advertised/learned. (confidence: medium)
- **Human decision:** Edited
- **What was wrong with the AI's answer:** The AI correctly identified the observable symptom — RIP routes were only being learned via FastEthernet0/0, not Fa0/1 — but guessed the wrong underlying mechanism. It assumed an interface or passive-interface problem. The actual fault was that the RIP `network` statement for 192.168.5.0 had been removed from Router3's router configuration entirely, which is a different failure than an interface being administratively down.
- **Correct root cause:** RIP network statement for 192.168.5.0 was removed from Router3, stopping advertisement through that segment; the ring topology's redundant path masked the failure from end users.
- **Why this matters / lesson:** The AI pattern-matched on "route missing from one interface" and reached for the most common cause (interface state) without checking whether the routing protocol's own configuration (the `network` statement) was still present. A reviewer should always verify the AI checked the actual protocol config, not just interface status, before accepting a routing-related diagnosis.

## Entry 2

### Case: C009
- **AI diagnosis:** OSPF network statement was changed to only advertise 192.168.4.0/24, removing the default 0.0.0.0 statement, causing all OSPF adjacencies to drop. (confidence: high)
- **Human decision:** Rejected
- **What was wrong with the AI's answer:** The diagnosis text itself was substantively correct. The problem was a structural/reliability failure in the AI's output: the `concept_tag` field came back empty, and the literal fragment `"concept_tag | : | OSPF"` leaked into the `fix_steps` field — a sign the model's JSON generation broke partway through formatting its answer, likely due to the length/complexity of this case combined with token constraints.
- **Correct root cause:** (Diagnosis text matches expected fault: OSPF network statement on C-RT2 uses wildcard 0.0.0.0 with address 192.168.4.0, which requires an exact match; no interface matches, so OSPF is disabled everywhere.)
- **Why this matters / lesson:** A correct diagnosis wrapped in a broken output format is not safe to trust in an automated pipeline — if `fix_steps` were fed directly into a script or displayed to a junior engineer without review, the malformed field could cause confusion or downstream errors. This is a good illustration of why structured-output validation (not just "does the reasoning sound right") needs to be part of any AI-assisted workflow, and why a human-in-the-loop step catches failures that a pure accuracy metric would miss.

## Entry 3

### Case: C010
- **AI diagnosis:** C-RT1's uplink (GigabitEthernet0/0) is administratively shut down, causing it to lose connectivity while still being HSRP Active for VLAN20. (confidence: medium)
- **Human decision:** Edited
- **What was wrong with the AI's answer:** The AI correctly observed the symptom (the uplink was down, yet C-RT1 remained HSRP Active) but did not identify why HSRP failed to react to that failure. It treated the interface being down as the root cause, rather than recognizing that HSRP is only capable of responding to an uplink failure if interface tracking is explicitly configured — and that tracking configuration was the piece that had been removed.
- **Correct root cause:** The `standby 20 track GigabitEthernet0/0` line was removed from C-RT1's VLAN20 subinterface, so HSRP had no mechanism to detect the uplink failure and lower C-RT1's priority; C-RT2 never took over.
- **Why this matters / lesson:** The AI's suggested fix (`no shutdown` on the interface) would restore connectivity in this specific instance but would not fix the underlying gap — the same failure mode would recur on any future uplink outage because HSRP tracking still wouldn't be configured. This highlights the difference between a fix that resolves the current symptom and one that addresses the root design flaw; a reviewer needs to check whether the recommended fix actually prevents recurrence.

## Entry 4

### Case: C002
- **AI diagnosis:** The static route to Google (74.0.0.0/8) points to next-hop 192.168.2.9, "which is likely unreachable or misconfigured." (confidence: medium)
- **Human decision:** Edited
- **What was wrong with the AI's answer:** The AI correctly identified the faulty route and the wrong next-hop IP, but hedged on the specific cause ("likely unreachable or misconfigured") rather than stating plainly that the IP address itself was simply mistyped/incorrect. The AI's own medium confidence rating reflects this uncertainty.
- **Correct root cause:** Static route to Google network has an incorrect next-hop IP (192.168.2.9 instead of the correct 192.168.2.2).
- **Why this matters / lesson:** When the AI hedges between multiple possible causes for the same symptom, a reviewer should check the underlying config, not just accept the hedge as good calibration. Here, the actual evidence available (a single obviously-wrong IP) supported a precise, confident answer — the AI under-committed rather than over-committed, which is a milder failure mode but still worth correcting so the written fix instructions are precise.

## Entry 5

### Case: C027
- **AI diagnosis:** D-SW1 has a higher STP priority (24586) than A-SW1 (4106) for VLAN 10, causing A-SW1 to become the root bridge. (confidence: high)
- **Human decision:** Edited
- **What was wrong with the AI's answer:** The final conclusion (A-SW1 incorrectly became root bridge) matches the expected fault. However, the AI's own cited evidence is internally inconsistent: it states D-SW1's "Root ID priority" is 4106, but 4106 should only be A-SW1's own bridge priority as broadcast in root announcements — D-SW1 reporting a Root ID of 4106 while its own Bridge ID priority is 24586 is exactly what should be expected once A-SW1 is root, but the AI's phrasing conflates "Root ID priority" and "own Bridge ID priority" in a way that reads as contradictory rather than confirmatory.
- **Correct root cause:** A-SW1's STP priority for VLAN10 was manually lowered from the default (32768) to 4096, well below D-SW1's priority (24586).
- **Why this matters / lesson:** A right answer with confusing or contradictory-looking evidence is still a reviewer risk — if a junior engineer reads the evidence field literally without already knowing the correct STP terminology, they could come away more confused than informed. This is a reminder that "evidence present" (which the automated evaluate.py check confirms) is not the same as "evidence clearly and correctly explained."