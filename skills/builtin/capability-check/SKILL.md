---
name: capability_check
description: Probe target host remediation capabilities before executing mutations.
domain: host-remediation
subdomain: capability-discovery
tags:
  - capability
  - os-detection
  - sudo
  - firewall
  - services
version: '1.0'
---

# Capability Check

## When to Use
- Before executing any remediation action on a target host
- When you need to know what tools/commands are available on the target
- When determining if a remediation can succeed (e.g., does the host have sudo? is the firewall configurable?)

## Prerequisites
- SSH access to the target host (via `ssh_manager` context)
- The target host must be reachable

## Workflow

### Step 1: Detect OS Family
Identify whether the target runs Linux, Windows, or macOS.

### Step 2: Detect Distribution Details
Collect distro-specific release info (e.g., Ubuntu 22.04, CentOS 7).

### Step 3: Check Sudo Capability
Verify whether the current account can elevate privileges with sudo.

### Step 4: Detect Firewall Type
Identify the firewall stack (iptables, nftables, firewalld, ufw, etc.).

### Step 5: Check Critical Files
Verify whether remediation-related files exist on the target.

### Step 6: Check Service Capability
Verify whether service-management commands are available.

### Step 7: Generate Capability Report
Summarize all detected capabilities into a capability matrix.

## Key Concepts

| Concept | Description |
|---------|-------------|
| Capability Matrix | A table mapping remediation actions to host capabilities |
| OS Detection | Determining OS family + distro to select correct commands |
| Sudo Check | Privilege escalation availability for privileged remediation |
| Firewall Detection | Identifying the firewall stack for rule modifications |

## Output Format

```
Capability Check Report:
  OS:           Ubuntu 22.04 LTS
  Sudo:         available (passwordless)
  Firewall:     ufw (active)
  Services:     systemd
  Critical Files: /etc/ssh/sshd_config ✓
  Overall:      READY for remediation
```
