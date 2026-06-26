import json, glob, sys

files = sorted(glob.glob("/root/agent-new/reports/R25_MSF2/*/state.json"))
if not files:
    print("no state"); sys.exit()

s = json.load(open(files[-1]))

print("=== FINDINGS (first 20) ===")
for f in s.get("findings", [])[:20]:
    port = f.get("port", "")
    svc = f.get("service", "")
    prod = f.get("product", "")
    ver = f.get("version", "")
    print(f"  port={port} svc=[{svc}] prod=[{prod}] ver=[{ver}]")

print("\n=== P13 ACTIONS ===")
p13 = [a for a in s.get("actions_taken", []) if "_p13" in str(a.get("tool", ""))]
print(f"Total: {len(p13)}")
for a in p13:
    err = a.get("error", "")
    args = str(a.get("args", ""))[:80]
    summary = str(a.get("result_summary", ""))[:60]
    status = "OK" if not err else f"ERR:{err[:30]}"
    print(f"  [{status}] {args}")
    if summary:
        print(f"    -> {summary}")

print("\n=== SURFACES ===")
surfaces = s.get("attack_surfaces", [])
by_status = {}
for surf in surfaces:
    st = surf.get("status", "unknown")
    by_status.setdefault(st, []).append(surf.get("surface_id", ""))
for st, ids in sorted(by_status.items()):
    print(f"  [{st}] ({len(ids)}): {ids}")
