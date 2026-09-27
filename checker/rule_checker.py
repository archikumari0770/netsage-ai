"""
NetSage AI — Deterministic Rule Checker

Regex/heuristic checks over raw Cisco show-command text (the `show_output`
column in cases.csv). These run independently of the AI and catch the
"obvious" config mistakes the project spec calls out:
  - duplicate IPs
  - wrong subnet masks
  - gateway mismatch
  - interface down
  - missing VLAN
  - missing routes

Run standalone:
    python rule_checker.py ../data/cases.csv

Or import `run_all_checks(show_output_text, context)` from ai_diagnose.py / evaluate.py
to run checks before or after the AI diagnosis and attach the findings as extra
evidence.
"""

import re
import sys
import csv
import json
from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class Finding:
    check: str
    severity: str  # info | warning | critical
    message: str


def check_duplicate_ips(text: str) -> List[Finding]:
    """Flags the same host IPv4 address (a HOST address, not a network prefix)
    being assigned/seen on two different interfaces or ARP entries. Deliberately
    ignores route-table and ACL lines, since the same /24 network legitimately
    appears in both — that is not a duplicate-IP condition."""
    findings = []
    # Only look at lines that plausibly assign/report a *host* IP, not a
    # route/ACL/network-prefix line.
    host_ip_pattern = re.compile(
        r'(?:ip address|Internet Address|Address:)\D*(\d{1,3}(?:\.\d{1,3}){3})', re.I
    )
    # ARP-style: "Internet  192.168.1.10   0   aabb.cc00.0100  ARPA   Vlan10"
    arp_pattern = re.compile(
        r'Internet\s+(\d{1,3}(?:\.\d{1,3}){3})\s+\S+\s+([0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})', re.I
    )

    ip_to_lines = {}
    for line in text.splitlines():
        if re.search(r'(deny|permit|access-list|is directly connected|show ip route)', line, re.I):
            continue  # skip ACL / routing-table lines entirely
        # A line like "HQ(config-if)#ip address ..." is an admin typing a
        # command in config mode, usually the *new* value replacing a prior
        # one on the same interface — not a second device claiming the IP.
        # Only count it if it's not paired with an obviously prior config-mode
        # entry for the same IP (best-effort: skip config-mode command lines
        # when a 'show running-config'-style line already reported this IP).
        is_config_mode_entry = bool(re.search(r'\(config[^)]*\)#', line))
        for ip in host_ip_pattern.findall(line):
            if is_config_mode_entry and ip in ip_to_lines:
                continue  # treat as an update to the same interface, not a dup
            ip_to_lines.setdefault(ip, set()).add(line.strip())

    for ip, lines in ip_to_lines.items():
        if len(lines) > 1:
            findings.append(Finding(
                check="duplicate_ip",
                severity="critical",
                message=f"Host IP {ip} is assigned/reported on more than one line, possible duplicate assignment: {lines}"
            ))

    # Cisco's own duplicate-address syslog message is the most reliable signal
    # available — trust it directly rather than inferring from context.
    dupaddr_pattern = re.compile(
        r'%IP-4-DUPADDR:\s*Duplicate address\s*(\d{1,3}(?:\.\d{1,3}){3})', re.I
    )
    for line in text.splitlines():
        m = dupaddr_pattern.search(line)
        if m:
            findings.append(Finding(
                check="duplicate_ip",
                severity="critical",
                message=f"Device-reported duplicate IP: {line.strip()}"
            ))

    # ARP table: same IP resolving to two different MACs = definite duplicate
    arp_ip_to_macs = {}
    for ip, mac in arp_pattern.findall(text):
        arp_ip_to_macs.setdefault(ip, set()).add(mac.lower())
    for ip, macs in arp_ip_to_macs.items():
        if len(macs) > 1:
            findings.append(Finding(
                check="duplicate_ip",
                severity="critical",
                message=f"ARP shows IP {ip} resolving to multiple MAC addresses {macs} — duplicate IP on the network"
            ))
    return findings


def check_wrong_mask(text: str, expected_prefix: int = None) -> List[Finding]:
    """Flags subnet masks that don't match a /24-style expectation, or mismatched
    masks between two interfaces claiming to be on the same subnet."""
    findings = []
    mask_pattern = re.compile(
        r'(\d{1,3}(?:\.\d{1,3}){3})\s*(?:mask\s*)?(255(?:\.\d{1,3}){3}|/\d{1,2})'
    )
    seen = {}
    for line in text.splitlines():
        m = mask_pattern.search(line)
        if m:
            ip, mask = m.groups()
            octets = ip.split(".")
            network = ".".join(octets[:3])  # crude /24 network bucket
            seen.setdefault(network, set()).add(mask)
    for network, masks in seen.items():
        if len(masks) > 1:
            findings.append(Finding(
                check="wrong_mask",
                severity="warning",
                message=f"Interfaces on {network}.0/24 report inconsistent masks: {masks}"
            ))
    return findings


def check_gateway_mismatch(text: str) -> List[Finding]:
    """Flags when a PC/host default-gateway IP doesn't share a /24 with its own IP,
    or when 'default gateway' and the router's actual interface IP disagree."""
    findings = []
    gw_pattern = re.compile(r'(?:default[- ]gateway|Default Gateway)\D*(\d{1,3}(?:\.\d{1,3}){3})', re.I)
    ip_pattern = re.compile(r'(?:IP Address|ip address)\D*(\d{1,3}(?:\.\d{1,3}){3})', re.I)

    gws = gw_pattern.findall(text)
    ips = ip_pattern.findall(text)
    for gw in gws:
        gw_net = ".".join(gw.split(".")[:3])
        for ip in ips:
            ip_net = ".".join(ip.split(".")[:3])
            if ip_net != gw_net:
                findings.append(Finding(
                    check="gateway_mismatch",
                    severity="critical",
                    message=f"Host IP {ip} and gateway {gw} are not on the same /24 subnet"
                ))
    return findings


def check_interface_down(text: str) -> List[Finding]:
    """Flags interfaces reported down/administratively down in 'show ip interface
    brief' or 'show interfaces'/syslog output. Deliberately ignores OSPF/EIGRP
    neighbor-adjacency log lines (e.g. '%OSPF-5-ADJCHG ... FULL to DOWN') —
    those report a *neighbor* transition, not necessarily the local interface
    itself being down, and including them drowned out real interface-down
    findings with noise on real router logs."""
    findings = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.search(r'(ADJCHG|Nbr\s|neighbor)', stripped, re.I):
            continue  # adjacency-change log line, not an interface-state line
        is_interface_line = re.search(r'(Fa|Gi|Se|Vlan|Eth|Port-channel)\S*\d', stripped)
        if not is_interface_line:
            continue
        looks_down = (
            re.search(r'administratively down', stripped, re.I)
            or re.search(r'line protocol.*(is|changed state to)\s*down', stripped, re.I)
            or re.search(r'changed state to down', stripped, re.I)
            # 'show ip interface brief' style: two down-ish tokens at line end
            or re.search(r'\bdown\s+down\b', stripped, re.I)
        )
        if looks_down:
            findings.append(Finding(
                check="interface_down",
                severity="critical",
                message=f"Interface reported down: {stripped}"
            ))

    # Adjacency changes are still useful evidence, just lower-confidence and
    # labeled separately so they don't get conflated with "the interface is down".
    for line in text.splitlines():
        stripped = line.strip()
        if re.search(r'ADJCHG.*FULL to DOWN', stripped, re.I):
            findings.append(Finding(
                check="ospf_adjacency_down",
                severity="warning",
                message=f"Routing adjacency dropped (check local config/mask/timers, not just link state): {stripped}"
            ))
    return findings


def check_missing_vlan(text: str, expected_vlan: str = None) -> List[Finding]:
    """Flags when an expected VLAN ID is referenced in the case but does not
    appear as 'active' in a 'show vlan brief' style block."""
    findings = []
    if not expected_vlan:
        return findings
    vlan_active = re.search(
        rf'\bVLAN\s*{re.escape(expected_vlan)}\b.*?(active|Status:\s*active)', text, re.I | re.S
    )
    vlan_mentioned = re.search(rf'\bVLAN\s*{re.escape(expected_vlan)}\b', text, re.I)
    if vlan_mentioned and not vlan_active:
        findings.append(Finding(
            check="missing_vlan",
            severity="warning",
            message=f"VLAN {expected_vlan} is referenced but not confirmed active in show output"
        ))
    if not vlan_mentioned:
        findings.append(Finding(
            check="missing_vlan",
            severity="critical",
            message=f"Expected VLAN {expected_vlan} does not appear anywhere in show output"
        ))
    return findings


def check_missing_route(text: str, expected_network: str = None) -> List[Finding]:
    """Flags when an expected destination network is absent from 'show ip route'."""
    findings = []
    if not expected_network:
        return findings
    route_block = re.search(r'show ip route.*', text, re.I | re.S)
    if route_block and expected_network not in route_block.group(0):
        findings.append(Finding(
            check="missing_route",
            severity="critical",
            message=f"Expected network {expected_network} not found in show ip route output"
        ))
    return findings


def run_all_checks(show_output: str, expected_vlan: str = None, expected_network: str = None) -> List[Dict]:
    findings: List[Finding] = []
    findings += check_duplicate_ips(show_output)
    findings += check_wrong_mask(show_output)
    findings += check_gateway_mismatch(show_output)
    findings += check_interface_down(show_output)
    findings += check_missing_vlan(show_output, expected_vlan)
    findings += check_missing_route(show_output, expected_network)
    return [f.__dict__ for f in findings]


def run_on_csv(path: str):
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        results = {}
        for row in reader:
            case_id = row.get("case_id", "UNKNOWN")
            show_output = row.get("show_output", "")
            findings = run_all_checks(show_output)
            results[case_id] = findings
            print(f"\n=== {case_id} ===")
            if not findings:
                print("  No deterministic issues flagged.")
            for fnd in findings:
                print(f"  [{fnd['severity'].upper()}] {fnd['check']}: {fnd['message']}")
        return results


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "../data/cases.csv"
    all_results = run_on_csv(csv_path)
    with open("rule_checker_results.json", "w") as out:
        json.dump(all_results, out, indent=2)
    print(f"\nSaved full results to rule_checker_results.json")
