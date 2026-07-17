#!/bin/bash
# SDIT 批量靶机测试脚本
# 用法: bash batch_targets.sh
# 功能: 逐个启动 Docker 靶机 → 运行 pentest agent → 收集结果 → 下一个

set -e

REPORT_ROOT="/root/agent-new/reports/BATCH_$(date +%Y%m%d)"
AGENT_DIR="/root/agent-new/src-python"
LOG_FILE="${REPORT_ROOT}/batch.log"
SUMMARY_FILE="${REPORT_ROOT}/summary.jsonl"

mkdir -p "$REPORT_ROOT"

log() {
    echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ═══════════════════════════════════════════════════════════════
# 靶机列表: NAME|IMAGE|PORT|DESCRIPTION
# ═══════════════════════════════════════════════════════════════
TARGETS=(
# ── Web 应用漏洞 ──
"dvwa|vulnerables/web-dvwa|80|DVWA - SQLi/XSS/Command Injection"
"juice-shop|bkimminich/juice-shop|3000|OWASP Juice Shop - Modern Web"
"pikachu|area39/pikachu|80|Pikachu - Chinese Web Vuln"
"mutillidae|webgoat/mutillidae:owasp-mutillidae|80|Mutillidae - OWASP Web"

# ── 经典 CVE 靶机 (Vulhub) ──
"httpd2449|vulhub/httpd:2.4.49|80|Apache 2.4.49 CVE-2021-41773 Path Traversal"
"httpd2450|vulhub/httpd:2.4.50|80|Apache 2.4.50 CVE-2021-42013 Path Traversal"
"struts2-2525|vulhub/struts2:2.5.25|8080|Struts2 S2-045 OGNL RCE"
"struts2-2333|vulhub/struts2:2.3.33|8080|Struts2 S2-045/S2-046"
"solr811|vulhub/solr:8.1.1|8983|Solr CVE-2019-17558 Velocity RCE"
"solr820|vulhub/solr:8.2.0|8983|Solr CVE-2019-7548 Velocity RCE"
"nexus|vulhub/nexus:3.21.1|8081|Nexus CVE-2019-7238 Expression Injection"
"tomcat85|vulhub/tomcat:8.5|8080|Tomcat Manager Default Creds"
"tomcat7|cschdockerhub/tomcat-privesc|8080|Tomcat 7 WAR Deploy"
"redis4|vulhub/redis:4.0.14|6379|Redis Unauth Access"
"redis5|vulhub/redis:5.0.5|6379|Redis 5 Unauth Access"
"activemq|vulhub/activemq:5.11.1|8161|ActiveMQ CVE-2015-5254 Deserialization"
"jenkins|vulhub/jenkins:2.138|8080|Jenkins 2.138 Script Console RCE"
"thinkphp5023|vulhub/thinkphp:5.0.23|8080|ThinkPHP 5.0.23 RCE"
"php-xxe|vulhub/php-xxe|80|PHP XXE Injection"
"flask111|vulhub/flask:1.1.1|5000|Flask SSTI/Jinja2 RCE"
"shiro124|vulhub/shiro:1.2.4|8080|Apache Shiro Deserialization"
"spring-cloud|vulhub/spring-cloud-gateway:3.0.3|8080|Spring Cloud Gateway CVE-2022-22947"
"weblogic|vulhub/weblogic:10.3.6|7001|WebLogic CVE-2017-10271"
"confluence|vulhub/confluence:7.4.6|8090|Confluence CVE-2022-26134 RCE"

# ── 数据库 ──
"mysql56|vulhub/mysql:5.6|3306|MySQL 5.6 Weak Creds"
"postgres96|vulhub/postgres:9.6|5432|PostgreSQL 9.6 Weak Creds"
"mongodb3|vulhub/mongodb:3.4|27017|MongoDB Unauth Access"
"memcached|vulhub/memcached:1.4|11211|Memcached Unauth Access"
"couchdb|vulhub/couchdb:2.1.0|5984|CouchDB CVE-2017-12635"

# ── 消息队列 ──
"rabbitmq|vulhub/rabbitmq:3.7.5|5672|RabbitMQ Default Creds"
"zookeeper|vulhub/zookeeper:3.4.14|2181|Zookeeper Unauth Access"

# ── 远程服务 ──
"smb|vulhub/samba:3.5.2|445|Samba CVE-2007-2447 usermap_script"
"ftp-vsftpd|vulhub/vsftpd:2.3.4|21|vsftpd 2.3.4 Backdoor CVE-2011-2523"
"ftp-proftpd|vulhub/proftpd:1.3.5|2121|ProFTPD mod_copy"
"irc-unreal|vulhub/unrealircd:3.2.8.1|6667|UnrealIRCd Backdoor CVE-2010-2075"

# ── 容器安全 ──
"dockersock|vulhub/dockersock|2375|Docker Socket Misconfiguration"

# ── IoT / 工控 ──
"linuxsrv01|cschdockerhub/linux-srv-01|80|Linux Server 01"
"linuxsrv02|cschdockerhub/linux-srv-02|80|Linux Server 02"
"linuxsrv03|cschdockerhub/linux-srv-03|80|Linux Server 03"

# ── 更多 Web 框架 ──
"django42|vulhub/django:4.2|8000|Django Debug Mode"
"spring15|vulhub/spring:1.5.0|8080|Spring Boot Actuator"
"laravel|vulhub/laravel:5.7|8000|Laravel Debug Mode"
"rails5|vulhub/rails:5.0|3000|Rails RCE"
"node-express|vulhub/node-express:1.0|3000|Node.js Express"
)

# ═══════════════════════════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════════════════════════

TOTAL=${#TARGETS[@]}
PASSED=0
FAILED=0
SKIPPED=0

log "=========================================="
log "SDIT 批量靶机测试开始"
log "目标数: $TOTAL"
log "报告目录: $REPORT_ROOT"
log "=========================================="

for i in "${!TARGETS[@]}"; do
    IFS='|' read -r NAME IMAGE PORT DESC <<< "${TARGETS[$i]}"
    IDX=$((i + 1))

    log ""
    log "━━━━━━━━ [$IDX/$TOTAL] $NAME ━━━━━━━━"
    log "  镜像: $IMAGE"
    log "  端口: $PORT"
    log "  描述: $DESC"

    # 1. 拉取镜像（如果不存在）
    if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        log "  拉取镜像..."
        if ! docker pull "$IMAGE" >> "$LOG_FILE" 2>&1; then
            log "  ❌ 镜像拉取失败，跳过"
            SKIPPED=$((SKIPPED + 1))
            echo "{\"name\":\"$NAME\",\"status\":\"skipped\",\"reason\":\"pull_failed\"}" >> "$SUMMARY_FILE"
            continue
        fi
    fi

    # 2. 停止并删除同名容器
    docker stop "$NAME" 2>/dev/null || true
    docker rm "$NAME" 2>/dev/null || true

    # 3. 启动容器
    log "  启动容器..."
    if ! docker run -d --name "$NAME" -p "$PORT:$PORT" -m 512m "$IMAGE" >> "$LOG_FILE" 2>&1; then
        log "  ❌ 容器启动失败，跳过"
        SKIPPED=$((SKIPPED + 1))
        echo "{\"name\":\"$NAME\",\"status\":\"skipped\",\"reason\":\"start_failed\"}" >> "$SUMMARY_FILE"
        continue
    fi

    # 4. 等待服务就绪
    CONTAINER_IP=$(docker inspect "$NAME" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' 2>/dev/null)
    log "  容器 IP: $CONTAINER_IP"

    READY=false
    for WAIT in 5 10 15 20 30; do
        sleep 5
        if curl -s -o /dev/null -w "%{http_code}" "http://$CONTAINER_IP:$PORT/" 2>/dev/null | grep -qE "^[23]"; then
            READY=true
            break
        fi
        # 也尝试 TCP 连接
        if nc -z -w2 "$CONTAINER_IP" "$PORT" 2>/dev/null; then
            READY=true
            break
        fi
    done

    if [ "$READY" = false ]; then
        log "  ⚠ 服务未就绪，仍然尝试测试..."
    fi

    # 5. 运行 pentest agent
    TASK_DIR="${REPORT_ROOT}/${NAME}"
    log "  启动渗透测试..."
    START_TIME=$(date +%s)

    timeout 600 python3 -u "$AGENT_DIR/../batch_pentest.py" \
        --targets "${CONTAINER_IP}:${PORT}" \
        --max-rounds 8 \
        --out-root "$TASK_DIR" \
        >> "${TASK_DIR}.log" 2>&1

    EXIT_CODE=$?
    END_TIME=$(date +%s)
    ELAPSED=$((END_TIME - START_TIME))

    # 6. 收集结果
    STATE_FILE=$(find "$TASK_DIR" -name "state.json" 2>/dev/null | head -1)
    if [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ]; then
        RESULT=$(python3 -c "
import json
s = json.load(open('$STATE_FILE'))
surfaces = s.get('attack_surfaces', [])
exploited = len([x for x in surfaces if x.get('status') == 'exploited'])
verified = len([x for x in surfaces if x.get('status') == 'verified'])
total = exploited + verified
creds = len(s.get('credentials', []))
vulns = len(s.get('vulnerabilities', []))
pct = (exploited * 100 // total) if total else 0
print(f'exploited={exploited} verified={verified} total={total} creds={creds} vulns={vulns} pct={pct}%')
" 2>/dev/null)

        log "  结果: $RESULT (${ELAPSED}s)"

        # JSON 汇总
        python3 -c "
import json
s = json.load(open('$STATE_FILE'))
surfaces = s.get('attack_surfaces', [])
exploited = len([x for x in surfaces if x.get('status') == 'exploited'])
verified = len([x for x in surfaces if x.get('status') == 'verified'])
total = exploited + verified
print(json.dumps({
    'name': '$NAME', 'image': '$IMAGE', 'port': $PORT,
    'exploited': exploited, 'verified': verified, 'total': total,
    'creds': len(s.get('credentials', [])),
    'vulns': len(s.get('vulnerabilities', [])),
    'elapsed': $ELAPSED, 'phase': s.get('phase', '?'),
    'pct': (exploited * 100 // total) if total else 0
}, ensure_ascii=False))
" >> "$SUMMARY_FILE" 2>/dev/null

        if [ "$EXIT_CODE" -eq 0 ]; then
            PASSED=$((PASSED + 1))
        else
            FAILED=$((FAILED + 1))
        fi
    else
        log "  ❌ 无 state 文件 (${ELAPSED}s)"
        FAILED=$((FAILED + 1))
        echo "{\"name\":\"$NAME\",\"status\":\"failed\",\"reason\":\"no_state\",\"elapsed\":$ELAPSED}" >> "$SUMMARY_FILE"
    fi

    # 7. 停止容器释放资源
    docker stop "$NAME" 2>/dev/null || true
    docker rm "$NAME" 2>/dev/null || true

    log "  ✅ 完成 [$IDX/$TOTAL]"
done

# ═══════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════
log ""
log "=========================================="
log "批量测试完成"
log "  总计: $TOTAL"
log "  通过: $PASSED"
log "  失败: $FAILED"
log "  跳过: $SKIPPED"
log "  汇总: $SUMMARY_FILE"
log "=========================================="

# 生成汇总报告
python3 -c "
import json
results = []
for line in open('$SUMMARY_FILE'):
    try:
        results.append(json.loads(line.strip()))
    except: pass

total = len(results)
exploited_total = sum(r.get('exploited', 0) for r in results)
verified_total = sum(r.get('verified', 0) for r in results)
passed = sum(1 for r in results if r.get('exploited', 0) > 0)

print()
print('=' * 60)
print('SDIT 批量测试汇总报告')
print('=' * 60)
print(f'靶机总数: {total}')
print(f'成功利用: {passed} ({passed*100//total if total else 0}%)')
print(f'总 exploited 面: {exploited_total}')
print(f'总 verified 面: {verified_total}')
print()
print(f'{\"靶机\":<25} {\"exploited\":>8} {\"verified\":>8} {\"耗时\":>6}')
print('-' * 50)
for r in sorted(results, key=lambda x: -x.get('exploited', 0)):
    name = r.get('name', '?')[:24]
    exp = r.get('exploited', 0)
    ver = r.get('verified', 0)
    elapsed = r.get('elapsed', 0)
    print(f'{name:<25} {exp:>8} {ver:>8} {elapsed:>5}s')
" 2>/dev/null | tee -a "$LOG_FILE"
