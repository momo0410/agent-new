import json
import re
import shlex
from typing import Any, Dict, List, Optional
from app.models.types import LogAnalysisEntry, LogAnalysisOutput, LogFileInfo
from app.services.ssh_manager import SSHManager
HIGHLIGHT_KEYWORDS = [
    "error", "fail", "denied", "refused", "invalid", "unauthorized",
    "critical", "alert", "emergency", "warning", "attack", "breach",
    "malware", "intrusion", "exploit", "vulnerability",
]
JOURNALCTL_PRIORITY_MAP = {
    "0": "error",
    "1": "error",
    "2": "error",
    "3": "error",
    "4": "warning",
    "5": "info",
    "6": "info",
    "7": "info",
}
COMMON_LOG_FILES: Dict[str, str] = {
    "/var/log/auth.log": "认证日志",
    "/var/log/syslog": "系统日志",
    "/var/log/kern.log": "内核日志",
    "/var/log/dmesg": "启动日志",
    "/var/log/secure": "安全日志",
    "/var/log/messages": "消息日志",
    "/var/log/nginx/access.log": "Nginx访问日志",
    "/var/log/nginx/error.log": "Nginx错误日志",
    "/var/log/apache2/access.log": "Apache访问日志",
    "/var/log/apache2/error.log": "Apache错误日志",
    "/var/log/mysql/error.log": "MySQL错误日志",
    "/var/log/postgresql/postgresql.log": "PostgreSQL日志",
}
def _parse_journalctl_json_line(line: str) -> Optional[LogAnalysisEntry]:
    if line.startswith('\x1e'):
        line = line[1:]
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None
    message = data.get("MESSAGE", "")
    priority = data.get("PRIORITY", "6")
    timestamp = data.get("__REALTIME_TIMESTAMP", "") or data.get("_SOURCE_REALTIME_TIMESTAMP", "")
    level = JOURNALCTL_PRIORITY_MAP.get(str(priority), "info")
    line_lower = message.lower()
    highlighted = any(kw in line_lower for kw in HIGHLIGHT_KEYWORDS)
    return LogAnalysisEntry(line=message, level=level, highlighted=highlighted, timestamp=timestamp)
def _parse_log_line(line: str) -> LogAnalysisEntry:
    line_lower = line.lower()
    highlighted = any(kw in line_lower for kw in HIGHLIGHT_KEYWORDS)
    level = "info"
    priority_match = re.match(r'^(\d+)>', line)
    if priority_match:
        priority_num = int(priority_match.group(1))
        severity = priority_num & 0x07
        level = JOURNALCTL_PRIORITY_MAP.get(str(severity), "info")
    else:
        # 尝试从行中提取显式的日志级别标记
        # 支持多种常见格式:
        # - "2025-03-18 01:57:53,789 INFO ..."
        # - "[ERROR] ..."
        # - "level=error ..."
        # - "status: warning ..."
        # 使用更精确的模式，避免匹配到单词中间
        level_patterns = [
            # 方括号包裹: [ERROR], [WARN], [INFO]
            r'\[(error|err|critical|crit|emergency|emerg|alert|fatal|warning|warn|info|information|debug|trace)\]',
            # 等号格式: level=error, level=info
            r'level[=:]\s*(error|err|critical|crit|emergency|emerg|alert|fatal|warning|warn|info|information|debug|trace)',
            # 空格分隔的级别标记（在时间戳后）
            r'\d{2}:\d{2}:\d{2}[\.,\d]*\s+(error|err|critical|crit|emergency|emerg|alert|fatal|warning|warn|info|information|debug|trace)\b',
            # 通用单词边界匹配（优先级最低）
            r'\b(error|err|critical|crit|emergency|emerg|alert|fatal|warning|warn|info|information|debug|trace)\b',
        ]
        level_match = None
        for pattern in level_patterns:
            level_match = re.search(pattern, line_lower)
            if level_match:
                break
        if level_match:
            matched = level_match.group(1)
            if matched in ("error", "err", "critical", "crit", "emergency", "emerg", "alert", "fatal"):
                level = "error"
            elif matched in ("warning", "warn"):
                level = "warning"
            elif matched in ("info", "information"):
                level = "info"
            elif matched in ("debug", "trace"):
                level = "debug"
        else:
            # 回退到关键词检测（仅当整行包含明确的错误/警告关键词时）
            if any(kw in line_lower for kw in ["critical", "emergency", "alert"]):
                level = "error"
            elif "warning" in line_lower:
                level = "warning"
    timestamp = None
    ts_match = re.match(r'^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})', line)
    if ts_match:
        timestamp = ts_match.group(1)
    else:
        ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})', line)
        if ts_match:
            timestamp = ts_match.group(1)
    return LogAnalysisEntry(line=line, level=level, highlighted=highlighted, timestamp=timestamp)
MONTH_MAP = {
    '01': 'Jan', '02': 'Feb', '03': 'Mar', '04': 'Apr',
    '05': 'May', '06': 'Jun', '07': 'Jul', '08': 'Aug',
    '09': 'Sep', '10': 'Oct', '11': 'Nov', '12': 'Dec',
}
def _build_date_grep_pattern(date_filter: str) -> str:
    if not date_filter or len(date_filter) < 10:
        return date_filter
    try:
        parts = date_filter.split('-')
        if len(parts) == 3:
            year, month, day = parts
            month_name = MONTH_MAP.get(month, '')
            if month_name:
                day_int = int(day)
                pattern = f"({year}-{month}-{day}|{month_name} {day}|{month_name}  {day_int})"
                return pattern
    except (ValueError, IndexError):
        pass
    return date_filter


def _shell_quote(value: str) -> str:
    return shlex.quote(value)


def _build_log_pipeline(
    log_path: str,
    filter_text: Optional[str] = None,
    date_filter: Optional[str] = None,
) -> str:
    cmd = f"cat {_shell_quote(log_path)} 2>/dev/null"
    if date_filter:
        grep_pattern = _shell_quote(_build_date_grep_pattern(date_filter))
        cmd = f"{cmd} | grep -E {grep_pattern}"
    if filter_text:
        cmd = f"{cmd} | grep -i {_shell_quote(filter_text)}"
    return cmd


def _build_journalctl_command(
    unit: Optional[str] = None,
    filter_text: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
) -> str:
    cmd_parts = ["journalctl --no-pager -o json"]
    if unit:
        cmd_parts.append(f"-u {_shell_quote(unit)}")
    if since:
        cmd_parts.append(f"--since {_shell_quote(since)}")
    if until:
        cmd_parts.append(f"--until {_shell_quote(until)}")
    if filter_text:
        cmd_parts.append(f"--grep {_shell_quote(filter_text)}")
    return " ".join(cmd_parts)
def _generate_list_log_files_command() -> str:
    find_expr = (
        "/var/log -maxdepth 2 -type f -readable "
        "\\( -name '*.log' -o -name '*.log.*' -o -name 'messages' -o -name 'secure' "
        "-o -name 'auth.log' -o -name 'syslog' -o -name 'kern.log' -o -name 'dmesg' "
        "-o -name 'Xorg.*' -o -name 'boot.log' -o -name 'cron' -o -name 'faillog' "
        "-o -name 'maillog' -o -name 'spooler' \\) "
        "! -name 'lastlog' ! -name 'btmp' ! -name 'wtmp' ! -name 'utmp' "
        "! -name '*.gz' ! -name '*.xz' ! -name '*.bz2' ! -name '*.zst'"
    )
    return (
        f"find {find_expr} 2>/dev/null | "
        "head -100 | "
        "xargs -d '\n' stat -c '%s|%n|%Y' 2>/dev/null"
    )
def _generate_log_file_info_command(log_path: str) -> str:
    return f"stat -c 'size:%s|modified:%Y' '{log_path}' 2>/dev/null || echo 'readable:no'"
def _parse_level_filter(level_filter: Optional[str]) -> Optional[List[str]]:
    """解析日志级别过滤字符串，如 'error,warning' -> ['error', 'warning']"""
    if not level_filter:
        return None
    levels = [lvl.strip().lower() for lvl in level_filter.split(',') if lvl.strip()]
    return levels if levels else None


def _parse_int_output(raw: str) -> int:
    try:
        return int((raw or "").strip() or "0")
    except (TypeError, ValueError):
        return 0


def _parse_journal_entries(raw_output: str, allowed_levels: Optional[List[str]] = None) -> List[LogAnalysisEntry]:
    entries: List[LogAnalysisEntry] = []
    raw_output = (raw_output or "").strip()
    if not raw_output or "no entries" in raw_output.lower():
        return entries

    try:
        data_array = json.loads(raw_output)
        if isinstance(data_array, list):
            for item in data_array:
                parsed = _parse_journalctl_json_line(json.dumps(item))
                if parsed and (not allowed_levels or parsed.level in allowed_levels):
                    entries.append(parsed)
            if entries:
                print(f"[log_analysis] 方法1: 解析为 JSON 数组，共 {len(entries)} 条")
                return entries
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        decoder = json.JSONDecoder()
        pos = 0
        length = len(raw_output)
        while pos < length:
            while pos < length and raw_output[pos] in ' \t\n\r':
                pos += 1
            if pos >= length:
                break
            obj, end = decoder.raw_decode(raw_output, pos)
            parsed = _parse_journalctl_json_line(json.dumps(obj))
            if parsed and (not allowed_levels or parsed.level in allowed_levels):
                entries.append(parsed)
            pos = end
        if entries:
            print(f"[log_analysis] 方法2: JSONDecoder 逐对象解析，共 {len(entries)} 条")
            return entries
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[log_analysis] 方法2 失败: {e}")

    if '\x1e' in raw_output:
        for line in raw_output.split('\x1e'):
            line = line.strip()
            if not line:
                continue
            parsed = _parse_journalctl_json_line(line)
            if parsed and (not allowed_levels or parsed.level in allowed_levels):
                entries.append(parsed)
        if entries:
            print(f"[log_analysis] 方法3: json-seq 格式解析，共 {len(entries)} 条")
            return entries

    blocks = re.split(r'\n\s*\n', raw_output)
    for block in blocks:
        block = block.strip()
        if not block or block.startswith('{') is False:
            continue
        try:
            obj = json.loads(block)
            parsed = _parse_journalctl_json_line(json.dumps(obj))
            if parsed and (not allowed_levels or parsed.level in allowed_levels):
                entries.append(parsed)
        except (json.JSONDecodeError, ValueError):
            continue
    if entries:
        print(f"[log_analysis] 方法4: 空行分割解析，共 {len(entries)} 条")
        return entries

    print(f"[log_analysis] 所有解析方法均失败")
    print(f"[log_analysis] 原始输出前 500 字符: {raw_output[:500]}")
    return entries
async def read_system_log(
    manager: SSHManager,
    log_path: str,
    page: int = 1,
    page_size: int = 100,
    filter_text: Optional[str] = None,
    date_filter: Optional[str] = None,
    level_filter: Optional[str] = None,
) -> LogAnalysisOutput:
    if not manager.is_connected():
        raise ConnectionError("没有活动的 SSH 连接")
    allowed_levels = _parse_level_filter(level_filter)
    pipeline = _build_log_pipeline(log_path, filter_text, date_filter)
    print(f"[log_analysis] 读取系统日志: {pipeline}")

    if not allowed_levels:
        start = max((page - 1) * page_size, 0)
        page_cmd = f"{pipeline} | tail -n +{start + 1} | head -n {page_size}"
        count_cmd = f"{pipeline} | wc -l"
        page_output = await manager.execute_command(page_cmd)
        count_output = await manager.execute_command(count_cmd)
        if page_output.exit_code and page_output.exit_code != 0:
            print(f"[log_analysis] page 退出码: {page_output.exit_code}")
        total_count = _parse_int_output(count_output.output)
        entries = []
        for line in page_output.output.split("\n"):
            line = line.strip()
            if not line or "Log file not found" in line or "No matching entries" in line:
                continue
            entries.append(_parse_log_line(line))
        highlighted_count = sum(1 for e in entries if e.highlighted)
        return LogAnalysisOutput(total_count=total_count, highlighted_count=highlighted_count, entries=entries)

    full_output = await manager.execute_command(pipeline)
    if full_output.exit_code and full_output.exit_code != 0:
        print(f"[log_analysis] 退出码: {full_output.exit_code}")
    entries = []
    print(f"[log_analysis] level_filter={level_filter}, allowed_levels={allowed_levels}")
    for line in full_output.output.split("\n"):
        line = line.strip()
        if not line or "Log file not found" in line or "No matching entries" in line:
            continue
        entry = _parse_log_line(line)
        if entry.level not in allowed_levels:
            continue
        entries.append(entry)
    print(f"[log_analysis] 解析到 {len(entries)} 条日志")
    return _paginate_and_return(entries, page, page_size)
async def read_journalctl_log(
    manager: SSHManager,
    page: int = 1,
    page_size: int = 100,
    unit: Optional[str] = None,
    filter_text: Optional[str] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    level_filter: Optional[str] = None,
) -> LogAnalysisOutput:
    if not manager.is_connected():
        raise ConnectionError("没有活动的 SSH 连接")
    allowed_levels = _parse_level_filter(level_filter)
    cmd = _build_journalctl_command(unit, filter_text, since, until)

    if not allowed_levels:
        start = max((page - 1) * page_size, 0)
        page_cmd = f"{cmd} | tail -n +{start + 1} | head -n {page_size}"
        count_cmd = f"{cmd} | wc -l"
        page_output = await manager.execute_command(page_cmd)
        count_output = await manager.execute_command(count_cmd)
        total_count = _parse_int_output(count_output.output)
        entries = _parse_journal_entries(page_output.output, None)
        highlighted_count = sum(1 for e in entries if e.highlighted)
        return LogAnalysisOutput(total_count=total_count, highlighted_count=highlighted_count, entries=entries)

    output = await manager.execute_command(cmd)
    entries = _parse_journal_entries(output.output, allowed_levels)
    return _paginate_and_return(entries, page, page_size)
def _paginate_and_return(entries: list, page: int, page_size: int) -> LogAnalysisOutput:
    total_count = len(entries)
    start = (page - 1) * page_size
    end = start + page_size
    paginated = entries[start:end]
    highlighted_count = sum(1 for e in paginated if e.highlighted)
    return LogAnalysisOutput(
        total_count=total_count,
        highlighted_count=highlighted_count,
        entries=paginated,
    )
async def list_log_files(manager: SSHManager) -> List[LogFileInfo]:
    if not manager.is_connected():
        raise ConnectionError("没有活动的 SSH 连接")
    cmd = _generate_list_log_files_command()
    print(f"[log_analysis] 执行日志文件列表命令: {cmd}")
    output = await manager.execute_command(cmd)
    print(f"[log_analysis] 命令输出 (前500字符): {output.output[:500]}")
    if output.output:
        print(f"[log_analysis] 输出行数: {len(output.output.strip().splitlines())}")
    print(f"[log_analysis] 退出码: {output.exit_code}")
    log_files = []
    for line in output.output.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 3:
            try:
                size = int(parts[0])
            except ValueError:
                size = 0
            path = parts[1]
            name = path.rsplit("/", 1)[-1]
            modified = parts[2]
            log_files.append(LogFileInfo(path=path, name=name, size=size, modified=modified, readable=True))
    print(f"[log_analysis] 找到 {len(log_files)} 个日志文件")
    for path, name in COMMON_LOG_FILES.items():
        if not any(f.path == path for f in log_files):
            log_files.append(LogFileInfo(path=path, name=name, size=0, modified="", readable=False))
    return log_files
async def get_log_file_info(manager: SSHManager, log_path: str) -> LogFileInfo:
    if not manager.is_connected():
        raise ConnectionError("没有活动的 SSH 连接")
    cmd = _generate_log_file_info_command(log_path)
    output = await manager.execute_command(cmd)
    name = log_path.rsplit("/", 1)[-1]
    if "readable:no" in output.output:
        return LogFileInfo(path=log_path, name=name, size=0, modified="", readable=False)
    size = 0
    modified = ""
    for part in output.output.split("|"):
        if part.startswith("size:"):
            try:
                size = int(part[5:])
            except ValueError:
                pass
        elif part.startswith("modified:"):
            modified = part[9:]
    return LogFileInfo(path=log_path, name=name, size=size, modified=modified, readable=True)
