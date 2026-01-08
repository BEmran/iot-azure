#!/usr/bin/env python3
import subprocess
import re
import ipaddress
from typing import Optional, Tuple, List, Dict
import logger
import sys

# Put your known vendor OUIs here (uppercase)
VENDOR_OUIS = {
    "00:01:A9",
}

def run(cmd: List[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout

def get_default_iface() -> Optional[str]:
    out = run(["ip", "route", "show", "default"]).strip()
    m = re.search(r"\bdev\s+(\S+)", out)
    return m.group(1) if m else None

def get_iface_cidr(iface: str) -> Optional[str]:
    out = run(["ip", "-4", "addr", "show", "dev", iface])
    m = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+/\d+)\b", out)
    return m.group(1) if m else None

def get_subnet_from_default_route() -> Tuple[str, str, str]:
    iface = get_default_iface()
    if not iface:
        raise RuntimeError("No default route; cannot detect active interface.")
    cidr = get_iface_cidr(iface)
    if not cidr:
        raise RuntimeError(f"No IPv4 CIDR found for interface {iface}.")
    subnet = str(ipaddress.ip_network(cidr, strict=False))
    return iface, cidr, subnet

def parse_nmap_sn_alive_ips(nmap_out: str) -> List[str]:
    """
    Parse `nmap -sn` output and return list of alive IPs.
    """
    ips = []
    current_ip: Optional[str] = None
    alive = False

    for line in nmap_out.splitlines():
        line = line.strip()

        m = re.search(r"Nmap scan report for\s+(.+)$", line)
        if m:
            # finalize previous host
            if current_ip and alive:
                ips.append(current_ip)

            host = m.group(1)
            ip_match = re.search(r"\((\d+\.\d+\.\d+\.\d+)\)$", host)
            current_ip = ip_match.group(1) if ip_match else host
            alive = False
            continue

        # Nmap prints: "Host is up (0.0010s latency)."
        if current_ip and line.startswith("Host is up"):
            alive = True

    if current_ip and alive:
        ips.append(current_ip)

    return ips

def get_mac_from_ip_neigh(ip: str) -> Optional[str]:
    try:
        out = run(["ip", "neigh", "show", ip])
    except Exception:
        return None
    m = re.search(r"lladdr\s+([0-9A-Fa-f:]{17})", out)
    return m.group(1).upper() if m else None

def oui(mac: str) -> str:
    return ":".join(mac.split(":")[:3]).upper()

def find_vendor_ips_in_subnet(subnet: str) -> str:
    """
    Scans the given subnet for hosts with MAC OUIs matching VENDOR_OUIS.
    Prints results to stdout.
    """
    logger.debug("Determining default interface and subnet...")
    if subnet == "":
        iface, cidr, subnet = get_subnet_from_default_route()
        logger.debug(f"Default iface: {iface}")
        logger.debug(f"CIDR: {cidr}")
        logger.debug(f"Subnet: {subnet}\n")

    # Key change: -PR forces ARP discovery on local LAN, -n disables DNS (faster/cleaner)
    logger.debug("Discovering hosts using ARP-based discovery (nmap -sn -PR -n) ...")
    nmap_out = run(["nmap", "-sn", "-PR", "-n", subnet])

    ips = parse_nmap_sn_alive_ips(nmap_out)
    if not ips:
        logger.warn("No alive hosts found.")
        return

    logger.debug(f"Found {len(ips)} alive host(s). Checking MAC OUIs...\n")

    matches = []
    for ip in ips:
        mac = get_mac_from_ip_neigh(ip)
        if not mac:
            # Sometimes ARP entry isn't present yet; try to “touch” it once
            subprocess.run(["ping", "-c", "1", "-W", "1", ip],
                           capture_output=True, text=True, check=False)
            mac = get_mac_from_ip_neigh(ip)

        if not mac:
            logger.debug(f" {ip:15}  MAC=UNKNOWN (couldn't resolve)")
            continue

        o = oui(mac)
        if o in VENDOR_OUIS:
            logger.debug(f" {ip:15}  MAC={mac}  OUI={o} <-------- MATCH!")
            matches.append((ip, mac))
        else:
            logger.debug(f" {ip:15}  MAC={mac}  OUI={o} (not in list)")

    logger.debug("Summary:")
    if matches:
        for ip, mac in matches:
            logger.debug(f"  - {ip} ({mac})")
        return matches[0][0]  # return first matching IP
    else:
        logger.debug("No vendor OUI matches found. Verify OUIs and that device is on the same subnet/L2.")
        return ""

if __name__ == "__main__":
    subnet = ""
    if len(sys.argv) > 1:
        subnet = sys.argv[1]
    ip = find_vendor_ips_in_subnet(subnet)
    print(f"Done scanning subnet and found {ip}.")
