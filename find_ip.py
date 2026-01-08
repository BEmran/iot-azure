#!/usr/bin/env python3
import subprocess
import re
import ipaddress
import sys
from typing import List, Optional, Tuple

# -----------------------------
# CONFIG: Add your vendor OUIs here (uppercase)
# -----------------------------
VENDOR_OUIS = {
    "00:01:A9",  # replace with known vendor OUI(s)
}

# -----------------------------
# Helpers
# -----------------------------
def run_cmd(cmd: List[str]) -> str:
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout

def get_default_iface() -> Optional[str]:
    """
    Returns the interface used for the default route (e.g., wlan0 or eth0).
    """
    try:
        out = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return None

    m = re.search(r"\bdev\s+(\S+)", out)
    return m.group(1) if m else None

def get_iface_cidr(iface: str) -> Optional[str]:
    """
    Returns IPv4 CIDR for interface, e.g. "192.168.1.23/24"
    """
    try:
        out = subprocess.run(
            ["ip", "-4", "addr", "show", "dev", iface],
            capture_output=True, text=True, check=True
        ).stdout
    except Exception:
        return None

    m = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)\b", out)
    return m.group(1) if m else None

def get_subnet_from_default_route() -> Tuple[str, str, str]:
    """
    Returns (iface, cidr, subnet) e.g. ("wlan0", "192.168.1.23/24", "192.168.1.0/24")
    """
    iface = get_default_iface()
    if not iface:
        raise RuntimeError("Could not determine default interface (no default route).")

    cidr = get_iface_cidr(iface)
    if not cidr:
        raise RuntimeError(f"Could not determine IPv4 CIDR for interface {iface}.")

    subnet = str(ipaddress.ip_network(cidr, strict=False))
    return iface, cidr, subnet

def parse_nmap_443_state(nmap_output: str):
    """
    Returns dict:
    {
        IP : "open",
        IP : "closed",
        IP : "filtered"
    }
    """
    results = {}
    current_ip = None

    for line in nmap_output.splitlines():
        line = line.strip()

        m = re.search(r"Nmap scan report for\s+(.+)$", line)
        if m:
            host = m.group(1)
            ip_match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)$", host)
            current_ip = ip_match.group(1) if ip_match else host
            continue

        # Example: "443/tcp open https"
        if current_ip and line.startswith("443/tcp"):
            parts = line.split()
            if len(parts) >= 2:
                state = parts[1].lower()
                results[current_ip] = state

    return results

def get_mac_from_ip_neigh(ip: str) -> Optional[str]:
    try:
        out = run_cmd(["ip", "neigh", "show", ip])
    except Exception:
        return None

    m = re.search(r"lladdr\s+([0-9a-fA-F:]{17})", out)
    return m.group(1).upper() if m else None

def get_mac_from_arp(ip: str) -> Optional[str]:
    try:
        out = run_cmd(["arp", "-n", ip])
    except Exception:
        return None

    m = re.search(r"([0-9a-fA-F:]{17})", out)
    return m.group(1).upper() if m else None

def get_mac(ip: str) -> Optional[str]:
    mac = get_mac_from_ip_neigh(ip)
    if mac:
        return mac

    # try to populate ARP cache
    subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                   capture_output=True, text=True, check=False)

    mac = get_mac_from_ip_neigh(ip)
    if mac:
        return mac

    return get_mac_from_arp(ip)

def oui(mac: str) -> str:
    parts = mac.split(":")
    return ":".join(parts[:3]).upper()
    
def find_vendor_ips_in_subnet(subnet: str) -> None:
    """
    Scans the given subnet for hosts with TCP/443 open and matches their MAC OUIs
    against the VENDOR_OUIS set. Prints results to stdout.
    """
    if subnet == "":
        print(f"[INFO] no subnet is provided")
        iface, cidr, subnet = get_subnet_from_default_route()
        print(f"[INFO] Auto-detected default iface: {iface}")
        print(f"[INFO] Interface CIDR: {cidr}")
        print(f"[INFO] Auto subnet: {subnet}")

    print(f"\n[INFO] Scanning {subnet} for TCP/443 state ...\n")

    try:
        # nmap_out = run_cmd(["nmap", "-p", "443", "--open", subnet])
        nmap_out = run_cmd(["nmap", "-p", "443", subnet])
    except subprocess.CalledProcessError as e:
        print("[ERROR] nmap failed:")
        print(e.stderr or str(e))
        sys.exit(2)

    ips = parse_nmap_443_state(nmap_out)

    if not ips:
        print("[INFO] No hosts responded.")
        return

    print(f"[INFO] Found {len(ips)} host(s) with TCP/443 open.\n")

    matches = []
    for ip in ips:
        mac = get_mac(ip)
        if not mac:
            print(f"[WARN] {ip}: 443 open but MAC not found (ARP/neigh missing).")
            continue

        ip_oui = oui(mac)
        if ip_oui in VENDOR_OUIS:
            print(f"[MATCH] {ip}  MAC={mac}  OUI={ip_oui}")
            matches.append((ip, mac))
        else:
            print(f"[INFO]  {ip}  MAC={mac}  OUI={ip_oui} (not in vendor list)")

    print("\n[INFO] Summary:")
    if matches:
        for ip, mac in matches:
            print(f"  - {ip} ({mac})")
        return matches[0][0]  # return first matching IP
    else:
        print("  No vendor matches found. Add correct OUIs or scan different ports.")
        return ""

if __name__ == "__main__":
    # Optional override: allow user to pass subnet manually
    subnet = ""
    if len(sys.argv) > 1:
        subnet = sys.argv[1]
    ip = find_vendor_ips_in_subnet(subnet)
    print(f"\n[INFO] Done. Found vendor IPs: {ip}")
    
