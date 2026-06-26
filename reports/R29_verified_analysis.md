# R29 Verified Services P13 Action Analysis

## Summary

13 services are marked as `verified` (not `exploited`) in R29 state.json. Analysis reveals **two distinct failure patterns**:

1. **P13 action ran but failed** (3 ports: 25, 53, 3632) — action executed, but the exploit technique didn't achieve shell/command execution
2. **No P13 action at all** (10 ports: 5900, 6000, 6697, 8009, 8180, 8787, 33314, 43828, 48249, 58779) — exploit was never generated or executed

---

## Detailed Analysis by Port

### GROUP 1: P13 Action Ran But Failed to Exploit

#### Port 25 (SMTP — Postfix smtpd)
- **P13 actions**: 6 attempts (all identical strategy)
- **Command**: `auto-direct direct SMTP VRFY 192.168.136.137:25`
- **Output**: SMTP VRFY enumeration succeeded — found users (root, msfadmin, user, postgres, www-data, daemon, nobody, mail, postfix, service)
- **Error**: None (rc=0)
- **Why not exploited**: The action only does **recon/enumeration** (VRFY user discovery), not exploitation. SMTP VRFY is an information disclosure, not a shell. The P13 tool chose the wrong strategy — it should have tried SMTP command injection, open relay abuse, or other attack vectors, but instead just repeated VRFY queries 6 times.
- **llm_decision**: `[AI 未提供决策过程]` (no AI decision provided)
- **Surface notes**: `attempt_count=0`, `via_action=''` — surface wasn't even updated with attempt info

#### Port 53 (DNS — ISC BIND 9.4.2)
- **P13 actions**: 6 attempts (all identical strategy)
- **Command**: `auto-direct direct DNS enum 192.168.136.137:53`
- **Output**: DNS version query succeeded (BIND 9.4.2), **zone transfer succeeded** (`DNS_ZONE_TRANSFER_OK`)
- **Error**: None (rc=0)
- **Why not exploited**: The action only does **recon/enumeration** (version query + zone transfer). Zone transfer is information disclosure, not code execution. The P13 tool repeated the same recon 6 times without ever attempting actual exploitation.
- **llm_decision**: `[AI 未提供决策过程]`

#### Port 3632 (distccd — distccd v1, GNU 4.2.4)
- **P13 actions**: 5 attempts (all identical strategy)
- **Command**: `auto-direct direct distcc exec 192.168.136.137:3632`
- **Output**: `DISTCC_ERROR: [Errno 32] Broken pipe` → `DISTCC_ALL_FAILED`
- **Error**: None (rc=0, but all attempts failed internally)
- **msfconsole attempt**: Also failed — `exploit/unix/misc/distcc_exec` with `cmd/unix/reverse_perl` timed out (90s)
- **Why not exploited**: The P13 direct exploit script couldn't execute commands via distcc. The Python-based distcc exploit consistently gets Broken pipe errors. Metasploit module also timed out. The exploit technique is fundamentally broken in this implementation.
- **Surface**: `attempt_count=1`, `via_action=4bb44fff32ff...` (the msfconsole attempt)

### GROUP 2: No P13 Action Generated

#### Port 5900 (VNC)
- **Surface**: `status=verified`, `last_tool=hydra`, `via_action=34fdf4c7841a...`
- **Hydra attempt**: Failed with rc=255 — `[ERROR] The redis, adam6500, cisco, oracle-listener, s7-300, snmp and vnc modules are only using the -p or -P option, not login (-l, -L) or colon file (-C).`
- **Why not exploited**: Hydra VNC brute-force failed due to incorrect argument format. **No P13 exploit action was generated** — the system only tried hydra, which failed, and never attempted a direct exploit.

#### Port 6000 (X11)
- **Surface**: `status=verified`, `last_tool=nmap`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.** The system identified X11 as open but never generated any exploit action.

#### Port 6697 (IRC/TLS — UnrealIRCd)
- **Surface**: `status=verified`, `last_tool=nmap`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.** Despite being listed as `suspected` UnrealIRCd backdoor (same vuln as port 6667 which WAS exploited), no exploit was attempted on port 6697.
- **Note**: Port 6667 was successfully exploited via msfconsole (`unreal_ircd_3281_backdoor`), but port 6697 (TLS variant) was never tried.

#### Port 8009 (AJP — Apache Tomcat)
- **Surface**: `status=verified`, `last_tool=nmap`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.** AJP port identified but never targeted. Could try Ghostcat (CVE-2020-1938) or similar AJP exploits.

#### Port 8180 (HTTP — Tomcat Manager)
- **Surface**: `status=verified`, `last_tool=nmap`, `via_action=c36e86f864f1...`, `attempt_count=2`
- **Actions taken**: Two `curl` requests with `tomcat:tomcat` credentials to `/manager/html` — **both succeeded** (HTTP 200 with Tomcat Manager HTML)
- **Why not exploited**: The credentials `tomcat:tomcat` were validated and the manager page was accessible, but **no P13 exploit action was generated** to deploy a WAR file or execute commands. The system confirmed access but never pivoted to code execution.
- **Surface notes**: `last_tool=shell` (curl via shell), not P13

#### Port 8787 (Unknown service)
- **Surface**: `status=verified`, `last_tool=nmap`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.** Service identified but never targeted.

#### Port 33314 (Unknown/high port)
- **Surface**: `status=verified`, `last_tool=nmap+probe`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.**

#### Port 43828 (Unknown/high port)
- **Surface**: `status=verified`, `last_tool=nmap+probe`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.**

#### Port 48249 (RPC status)
- **Surface**: `status=verified`, `last_tool=nmap+probe`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.** This is `rpc.statd` (100024) which has known exploits.

#### Port 58779 (Unknown/high port)
- **Surface**: `status=verified`, `last_tool=nmap+probe`, `via_action=''`, `attempt_count=0`
- **Why not exploited**: **No exploit attempt at all.**

---

## Root Causes

### 1. P13 Repeats Recon Instead of Exploiting (Ports 25, 53)
The P13 direct exploit tool generates "exploit" actions that are actually **recon/enumeration only** (SMTP VRFY, DNS zone transfer). These produce useful information but no shell. The tool ran the same recon 6 times per port without escalating to actual exploitation techniques.

### 2. P13 Exploit Implementation Fails (Port 3632)
The distcc exploit implementation has a fundamental bug — it gets `[Errno 32] Broken pipe` on every attempt. The Metasploit fallback also timed out.

### 3. No P13 Action Generated (10 ports)
The majority of verified services (10/13) have **zero P13 exploit actions**. The system identified these services but never generated exploit code for them. This is the biggest gap.

### 4. Credential Validation ≠ Exploitation (Port 8180)
Tomcat Manager credentials were validated via curl, but the system never attempted to deploy a malicious WAR file or execute commands through the manager interface.

### 5. Successful Exploit Not Extended (Port 6697)
Port 6667 was exploited via UnrealIRCd backdoor, but port 6697 (same service, TLS variant) was never attempted — likely because the exploit was done via msfconsole which only targeted port 6667.

### 6. llm_decision Always Empty
Every P13 action has `llm_decision: [AI 未提供决策过程]` — the AI decision engine never provided reasoning, suggesting the P13 tool operates without LLM guidance on exploit selection.

---

## Statistics

| Category | Count | Ports |
|----------|-------|-------|
| Verified (total) | 13 | 25,53,3632,5900,6000,6697,8009,8180,8787,33314,43828,48249,58779 |
| P13 ran but only recon | 2 | 25, 53 |
| P13 ran but exploit failed | 1 | 3632 |
| No P13 action generated | 10 | 5900,6000,6697,8009,8180,8787,33314,43828,48249,58779 |
| Non-P13 action only | 2 | 5900 (hydra fail), 8180 (curl success) |
| Zero attempts at all | 7 | 6000,6697,8009,8787,33314,43828,48249,58779 |

## Key Recommendations

1. **Fix P13 strategy selection**: Distinguish between recon-only actions and actual exploit actions. Don't mark recon as "exploit attempts."
2. **Generate P13 actions for all verified services**: 10 ports had zero exploit attempts.
3. **Fix distcc exploit**: The Python implementation has a broken pipe bug.
4. **Extend successful exploits**: Port 6667 exploit should have been tried on port 6697.
5. **Deploy WAR via Tomcat Manager**: Credentials are valid — use them to deploy a webshell.
6. **Add LLM decision tracking**: The `[AI 未提供决策过程]` gap means there's no audit trail for exploit selection reasoning.
