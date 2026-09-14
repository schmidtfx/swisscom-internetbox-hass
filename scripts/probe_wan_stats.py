#!/usr/bin/env python3
"""Probe an InternetBox for a readable WAN byte counter.

Enumerates every NeMo interface via ``getMIBs`` (``getIntfs`` answers HTTP 401
and ``HomeLan`` does not exist on this firmware), then probes
``getNetDevStats`` on each one to see which the webui role may read.

Findings on an InternetBox 5 / IB5-P-00 on GPON, firmware as of 2026-09:
only 2 of its 83 interfaces are readable, ``veip0`` (the WAN uplink, which is
what the integration now uses) and ``bridge`` (the LAN side, whose counters are
the WAN's mirrored). Every other interface answers HTTP 401, and objects or
functions that do not exist answer HTTP 404 -- so on this firmware 401 means
"not permitted" rather than "session expired".

Keep this around for the next firmware or a DSL box, where the answer differs.

Usage:
    INETBOX_PASSWORD=... python scripts/probe_wan_stats.py [--host 192.168.1.1]

Pass ``--dump replies.json`` to write every full reply for offline reading;
the console output truncates long ones.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from sc_inetbox_adapter import InternetboxAdapter

# Seeds for the interface walk. getMIBs on any one of these reports its
# neighbours in ULIntf/LLIntf, so the walk expands from here.
SEED_INTERFACES: tuple[str, ...] = ("data", "lo", "lan", "bridge", "eth0", "veip0")

# Rounds of getMIBs expansion. The stack is only a handful deep, so this is
# just a guard against a cycle in the graph.
MAX_ROUNDS = 6

# Candidates that do not depend on the interface list. HomeLan is gone from
# this list: it 404s on this box.
FIXED_CANDIDATES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("/sysbus/NMC:getWANStatus", {}),
    ("/sysbus/NeMo/Intf/data:getMIBs", {}),
    ("/sysbus/DeviceInfo:get", {}),
    ("/sysbus/Devices/Device/HGW:get", {}),
    ("/sysbus/NMC:getWANCounters", {}),
    ("/sysbus/NMC/Wan:get", {}),
)

COUNTER_KEYS = ("BytesReceived", "BytesSent", "RxBytes", "TxBytes")


def call(adapter: InternetboxAdapter, path: str, parameters: dict[str, Any]) -> Any:
    """POST one sysbus call and return the decoded body (or an error marker)."""
    headers = adapter._add_auth_header()
    payload = json.dumps({"parameters": parameters})
    response = adapter._send_request(path, payload, headers)
    if response.status_code != 200:
        return {"__http__": response.status_code}
    try:
        return response.json()
    except ValueError:
        return {"__body__": response.text[:200]}


def describe(reply: Any, width: int = 400) -> str:
    """Collapse a reply to one line: the counters, or why there are none."""
    if isinstance(reply, dict):
        if "__http__" in reply:
            return f"HTTP {reply['__http__']}"
        if "__body__" in reply:
            return f"non-JSON: {reply['__body__']!r}"
        errors = reply.get("errors")
        if errors:
            first = errors[0] if isinstance(errors, list) and errors else errors
            if isinstance(first, dict):
                return (
                    f"error {first.get('error')}: {first.get('description')}"
                    f" ({first.get('info')})"
                )
            return f"error: {errors}"
        if reply.get("status") is None:
            return "empty status"
    blob = json.dumps(reply)
    return f"OK {blob[:width]}" + ("..." if len(blob) > width else "")


def error_code(reply: Any) -> int | None:
    """The numeric sysbus error, if the reply is a rejection."""
    if not isinstance(reply, dict):
        return None
    errors = reply.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        code = errors[0].get("error")
        return code if isinstance(code, int) else None
    return None


def byte_counters(reply: Any) -> bool:
    """True when the reply mentions something that looks like a byte counter."""
    blob = json.dumps(reply)
    return any(needle in blob for needle in COUNTER_KEYS)


def collect_names(node: Any, found: set[str]) -> None:
    """Harvest interface names from a getMIBs reply.

    Names show up as the keys of the ``ULIntf``/``LLIntf`` maps nested
    anywhere inside the reply, and as ``Name`` values.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("ULIntf", "LLIntf") and isinstance(value, dict):
                found.update(name for name in value if isinstance(name, str))
            elif key == "Name" and isinstance(value, str) and value:
                found.add(value)
            collect_names(value, found)
    elif isinstance(node, list):
        for item in node:
            collect_names(item, found)


def walk_interfaces(
    adapter: InternetboxAdapter, dump: dict[str, Any]
) -> tuple[set[str], int]:
    """Expand the interface graph from the seeds via repeated getMIBs calls."""
    names: set[str] = set()
    queried: set[str] = set()
    frontier = set(SEED_INTERFACES)
    calls = 0

    for _ in range(MAX_ROUNDS):
        frontier -= queried
        if not frontier:
            break
        for name in sorted(frontier):
            path = f"/sysbus/NeMo/Intf/{name}:getMIBs"
            reply = call(adapter, path, {})
            dump[path] = reply
            queried.add(name)
            calls += 1
            status = reply.get("status") if isinstance(reply, dict) else None
            if isinstance(status, dict):
                names.add(name)
                # status is keyed by MIB name ("base", "netdev", ...); the
                # interface names are one level below that.
                for mib in status.values():
                    if isinstance(mib, dict):
                        names.update(k for k in mib if isinstance(k, str))
                collect_names(status, names)
        frontier = names - queried

    return names, calls


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("INETBOX_HOST", "192.168.1.1"))
    parser.add_argument("--password", default=os.environ.get("INETBOX_PASSWORD"))
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--dump", help="write every full reply to this JSON file")
    args = parser.parse_args()

    if not args.password:
        parser.error("set INETBOX_PASSWORD or pass --password")

    adapter = InternetboxAdapter(
        admin_password=args.password,
        host=args.host,
        verify_ssl=not args.no_verify_ssl,
    )
    status = adapter.create_session()
    if int(status) != 200:
        print(f"login failed: HTTP {status}", file=sys.stderr)
        return 1

    dump: dict[str, Any] = {}
    hits: list[str] = []
    denied: list[str] = []
    missing: list[str] = []

    try:
        print("== walking the NeMo interface graph via getMIBs ==")
        names, calls = walk_interfaces(adapter, dump)
        print(f"{calls} getMIBs calls found {len(names)} interfaces:")
        print("  " + ", ".join(sorted(names)) if names else "  (none)")

        print(f"\n== getNetDevStats on {len(names)} interfaces ==")
        for name in sorted(names):
            path = f"/sysbus/NeMo/Intf/{name}:getNetDevStats"
            reply = call(adapter, path, {})
            dump[path] = reply
            print(f"{path}: {describe(reply, width=200)}")
            if byte_counters(reply):
                hits.append(path)
            elif error_code(reply) == 13:
                denied.append(name)
            elif error_code(reply) == 196618:
                missing.append(name)

        print("\n== fixed candidates ==")
        for path, parameters in FIXED_CANDIDATES:
            reply = call(adapter, path, parameters)
            dump[f"{path} {json.dumps(parameters)}"] = reply
            suffix = f" {parameters}" if parameters else ""
            print(f"{path}{suffix}: {describe(reply, width=200)}")
            if byte_counters(reply):
                hits.append(f"{path}{suffix}")
    finally:
        adapter.logout_session()

    print("\n== summary ==")
    print(f"paths with byte counters: {len(hits)}")
    for hit in hits:
        print(f"  {hit}")
    if not hits:
        print("  (none)")
    # A netdev that exists but is ACL-blocked is a different problem from one
    # that does not exist, and only the first kind is worth chasing further.
    print(f"permission denied (netdev exists, role blocked): {', '.join(denied) or '-'}")
    print(f"no getNetDevStats function (not a netdev): {', '.join(missing) or '-'}")

    if args.dump:
        with open(args.dump, "w") as handle:
            json.dump(dump, handle, indent=2, sort_keys=True)
        print(f"\nfull replies written to {args.dump}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
