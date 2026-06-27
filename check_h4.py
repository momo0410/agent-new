import json, glob
files = sorted(glob.glob("/root/agent-new/reports/H4_nexus/*/state.json"))
s = json.load(open(files[-1]))
for a in s.get("actions_taken", []):
    tool = str(a.get("tool", ""))
    args = str(a.get("args", ""))
    if "llm" in tool.lower() or ("llm" in args.lower()[:20]):
        print(f"[{tool}] args_len={len(args)}")
        print(f"  code: {args[:400]}")
        err = str(a.get("error", ""))
        if err:
            print(f"  error: {err[:100]}")
        summary = str(a.get("result_summary", ""))
        if summary:
            print(f"  result: {summary[:200]}")
        print()
