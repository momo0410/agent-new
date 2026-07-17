import re

with open("/root/agent-new/batch_targets.sh", "r") as f:
    lines = f.readlines()

# Find the IFS line and add skip logic after it
new_lines = []
for i, line in enumerate(lines):
    new_lines.append(line)
    if "IFS='|' read -r NAME IMAGE PORT DESC" in line:
        new_lines.append('    # Skip already tested targets\n')
        new_lines.append('    if grep -q "\\"${NAME}\\"" "${REPORT_ROOT}/../BATCH_20260627/summary.jsonl" 2>/dev/null; then\n')
        new_lines.append('        log "  ⏭ already tested, skip"\n')
        new_lines.append('        continue\n')
        new_lines.append('    fi\n')

with open("/root/agent-new/batch_targets.sh", "w") as f:
    f.writelines(new_lines)

print("patched")
