import sys
sys.path.insert(0, ".")
from app.services.pentest_agent.executor import Executor
from app.services.pentest_agent.state import State
state = State("/tmp/test_tools_state.json")
ex = Executor(state=state)
tools = ex.list_tools()
key_tools = ["sqlmap", "nikto", "gobuster", "wfuzz", "wpscan", "whatweb", "ffuf", "dirb", "hydra", "nmap", "msfconsole", "searchsploit", "curl", "python_exploit", "shell", "search_cve", "search_exploit", "nikto"]
for tool in key_tools:
    found = False
    for line in tools.split("\n"):
        if line.strip().startswith(tool + ":"):
            print(f"  OK {line.strip()[:80]}")
            found = True
            break
    if not found:
        print(f"  MISSING {tool}")

print(f"\nTotal tools: {len(tools.split(chr(10)))}")
