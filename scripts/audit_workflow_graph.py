"""Audit Domino workflow customization (read-only)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CUST = REPO / "test_sus_onedata.customization"


def main() -> int:
    data = json.loads(CUST.read_text(encoding="utf-8"))
    pieces = data["workflowPieces"]
    pdata = data["workflowPiecesData"]
    edges = data["workflowEdges"]

    id_to_name = {nid: meta["name"] for nid, meta in pieces.items()}
    up_to_node: dict[str, str] = {}
    for nid, node in pdata.items():
        uid = node.get("upstreamId")
        if uid:
            up_to_node[uid] = nid

    print("=== NODES & INPUTS ===")
    for nid, node in sorted(pdata.items(), key=lambda x: id_to_name.get(x[0], "")):
        name = id_to_name.get(nid, "?")
        print(f"\n{name}")
        for inp, spec in sorted((node.get("inputs") or {}).items()):
            if spec.get("fromUpstream"):
                uid = spec.get("upstreamId", "")
                src_node = up_to_node.get(uid, "?")
                src_name = id_to_name.get(src_node, uid)
                print(f"  {inp} <- {src_name}.{spec.get('upstreamArgument')}")
            else:
                v = spec.get("value", "")
                if len(str(v)) > 72:
                    v = str(v)[:69] + "..."
                print(f"  {inp} = {v!r}")

    print("\n=== EDGES ===")
    for e in edges:
        s = id_to_name.get(e["source"], e["source"])
        t = id_to_name.get(e["target"], e["target"])
        print(f"  {s} -> {t}")

    in_edges = {e["source"] for e in edges} | {e["target"] for e in edges}
    for nid in pdata:
        if nid not in in_edges:
            print(f"ISOLATED: {id_to_name.get(nid, nid)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
