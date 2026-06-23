#!/usr/bin/env python3
"""verify_skills_with_nvd.py — 用 NVD 权威数据反查修正已有 17 个 exploit skill 的 Principle

用途（见 docs/handoff-03-online-search-design.md 第十一步 Step 7）：
  1. 遍历 skills/exploit-skills/ 下所有 SKILL.md
  2. 提取 frontmatter 中的 cve 字段
  3. 调 NVD 查证每个 CVE 的权威描述
  4. 对比 skill 的 Principle 章节与 NVD 描述，报告差异
  5. --fix 模式下：差异大时由 LLM 修正 Principle 章节（需 LLM 配置）

用法：
  # 只查证，输出报告（默认）
  python scripts/verify_skills_with_nvd.py

  # 查证 + 自动修正（需要 LLM 配置）
  python scripts/verify_skills_with_nvd.py --fix

  # 指定 skills 根目录
  python scripts/verify_skills_with_nvd.py --skills-root /path/to/skills

  # 离线模式（只用已缓存的 NVD 数据，不联网）
  python scripts/verify_skills_with_nvd.py --offline
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Optional

# 把 src-python 加入 path，以便复用项目内的 NvdClient 和 SkillMdParser
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_SRC_PYTHON = os.path.join(_PROJECT_ROOT, "src-python")
sys.path.insert(0, _SRC_PYTHON)

from app.services.online_search.nvd_client import NvdClient  # noqa: E402

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """解析 SKILL.md 的 YAML frontmatter，返回 (frontmatter_dict, body)。"""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1].strip()
    body = parts[2]
    if yaml:
        try:
            fm = yaml.safe_load(fm_text) or {}
            return fm if isinstance(fm, dict) else {}, body
        except yaml.YAMLError:
            pass
    # 退化：正则提取 cve 字段
    fm: dict[str, Any] = {}
    m = re.search(r"^cve:\s*(.+)$", fm_text, re.MULTILINE)
    if m:
        fm["cve"] = m.group(1).strip().strip("'\"")
    return fm, body


def extract_principle(body: str) -> str:
    """从 SKILL.md body 中提取 Principle 章节内容。"""
    m = re.search(r"##\s*Principle\s*\n(.*?)(?=\n##\s|\Z)", body, re.DOTALL)
    return m.group(1).strip() if m else ""


def extract_cves_from_text(text: str) -> list[str]:
    """从文本中提取所有 CVE 编号。"""
    return list(dict.fromkeys(
        m.upper() for m in re.findall(r"CVE-\d{4}-\d{4,}", text, re.IGNORECASE)
    ))


def find_skill_files(skills_root: str) -> list[str]:
    """找到 skills/exploit-skills/ 下所有 SKILL.md。"""
    exploit_dir = os.path.join(skills_root, "exploit-skills")
    if not os.path.isdir(exploit_dir):
        print(f"[WARN] 目录不存在: {exploit_dir}")
        return []
    results: list[str] = []
    for root, _, files in os.walk(exploit_dir):
        for f in files:
            if f.upper() == "SKILL.MD":
                results.append(os.path.join(root, f))
    return sorted(results)


def compare_principle_with_nvd(
    skill_path: str,
    principle: str,
    cve_id: str,
    nvd_data: dict[str, Any],
) -> dict[str, Any]:
    """对比 skill 的 Principle 与 NVD 权威描述，返回差异报告。"""
    nvd_desc = nvd_data.get("description", "")
    nvd_cvss = nvd_data.get("cvss_score")
    nvd_severity = nvd_data.get("cvss_severity", "")

    # 简单差异指标
    principle_lower = principle.lower()
    nvd_lower = nvd_desc.lower()

    # 检查 Principle 是否包含 NVD 描述的关键词
    key_terms = set(re.findall(r"[a-z]{4,}", nvd_lower))
    principle_terms = set(re.findall(r"[a-z]{4,}", principle_lower))
    overlap = key_terms & principle_terms
    overlap_ratio = len(overlap) / max(len(key_terms), 1)

    # CVSS 一致性
    cvss_in_principle = re.search(r"CVSS[:\s]*(\d+\.?\d*)", principle, re.IGNORECASE)
    cvss_mismatch = False
    if cvss_in_principle and nvd_cvss:
        try:
            if abs(float(cvss_in_principle.group(1)) - float(nvd_cvss)) > 0.1:
                cvss_mismatch = True
        except ValueError:
            pass

    # 判定差异等级
    if overlap_ratio < 0.15:
        severity = "high"  # Principle 与 NVD 描述差异大
    elif overlap_ratio < 0.35 or cvss_mismatch:
        severity = "medium"
    else:
        severity = "low"

    return {
        "skill_path": skill_path,
        "cve_id": cve_id,
        "nvd_description": nvd_desc,
        "nvd_cvss": nvd_cvss,
        "nvd_severity": nvd_severity,
        "principle_excerpt": principle[:300],
        "overlap_ratio": round(overlap_ratio, 2),
        "cvss_mismatch": cvss_mismatch,
        "severity": severity,
        "nvd_references": [r.get("url", "") for r in nvd_data.get("references", [])[:3]],
    }


def run_verification(
    skills_root: str,
    offline: bool = False,
    fix: bool = False,
) -> list[dict[str, Any]]:
    """执行完整的反查流程，返回差异报告列表。"""
    skill_files = find_skill_files(skills_root)
    if not skill_files:
        print(f"[ERROR] 未找到 skill 文件: {skills_root}/exploit-skills/")
        return []

    print(f"[INFO] 发现 {len(skill_files)} 个 exploit skill")
    print(f"[INFO] 模式: {'离线' if offline else '在线'}{' + 自动修正' if fix else ''}")
    print()

    nvd = NvdClient(timeout=20)
    if offline:
        # 离线模式：用 OnlineSearchCache 的 L3 永久缓存
        from app.services.online_search.cache import OnlineSearchCache
        cache_dir = os.path.join(skills_root, "knowledge_base")
        cache = OnlineSearchCache(l3_dir=cache_dir)

    reports: list[dict[str, Any]] = []
    for idx, skill_path in enumerate(skill_files, 1):
        rel_path = os.path.relpath(skill_path, skills_root)
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()

        fm, body = parse_frontmatter(content)
        cve_id = str(fm.get("cve", "")).strip()
        principle = extract_principle(body)

        if not cve_id:
            print(f"[{idx}/{len(skill_files)}] {rel_path} — 无 CVE 字段，跳过")
            reports.append({"skill_path": rel_path, "cve_id": "", "severity": "skip", "reason": "无 CVE 字段"})
            continue

        # 查 NVD
        nvd_data = None
        if offline:
            from app.services.online_search.cache import stable_cache_key
            nvd_data = cache.get("cve", stable_cache_key("cve", cve_id.upper()))
        else:
            nvd_data = nvd.get_cve(cve_id)

        if not nvd_data:
            print(f"[{idx}/{len(skill_files)}] {rel_path} CVE={cve_id} — NVD 查询失败/无数据")
            reports.append({
                "skill_path": rel_path, "cve_id": cve_id,
                "severity": "error", "reason": "NVD 查询失败",
            })
            continue

        # 对比
        report = compare_principle_with_nvd(rel_path, principle, cve_id, nvd_data)
        reports.append(report)

        status_icon = {"low": "OK", "medium": "WARN", "high": "DIFF"}[report["severity"]]
        print(
            f"[{idx}/{len(skill_files)}] {status_icon} {rel_path} CVE={cve_id} "
            f"overlap={report['overlap_ratio']} cvss_mismatch={report['cvss_mismatch']}"
        )

        # --fix 模式：差异大时由 LLM 修正
        if fix and report["severity"] in ("high", "medium"):
            _try_fix_principle(skill_path, content, body, principle, report)

    return reports


def _try_fix_principle(
    skill_path: str,
    full_content: str,
    body: str,
    old_principle: str,
    report: dict[str, Any],
) -> bool:
    """尝试用 LLM 修正 Principle 章节。返回是否成功修改。"""
    try:
        from app.services.pentest_agent.llm_client import get_llm_client
        client = get_llm_client()
    except Exception:
        print(f"    [FIX] LLM 客户端不可用，跳过自动修正")
        return False

    prompt = f"""你是安全漏洞文档专家。请根据 NVD 权威信息重写以下 SKILL.md 的 Principle 章节。

## 当前 Principle（可能有不准确之处）
{old_principle[:1000]}

## NVD 权威信息
- CVE: {report['cve_id']}
- CVSS: {report['nvd_cvss']} ({report['nvd_severity']})
- NVD 描述: {report['nvd_description']}
- 参考链接: {', '.join(report.get('nvd_references', []))}

## 要求
1. 只输出 Principle 章节的正文内容（不要 ## Principle 标题，不要其他章节）
2. 用中文写，解释漏洞的根本原理（为什么存在、怎么形成的）
3. 以 NVD 描述为权威依据，修正原 Principle 中不准确的部分
4. 保持简洁，300-600 字
5. 如果原 Principle 比 NVD 描述更详细（比如有代码逻辑分析），保留原有价值信息，只修正事实性错误
"""

    try:
        response = client.chat([
            {"role": "system", "content": "你是安全漏洞文档专家，擅长用中文写准确的漏洞原理分析。"},
            {"role": "user", "content": prompt},
        ])
    except Exception as e:
        print(f"    [FIX] LLM 调用失败: {e}")
        return False

    if not response or not isinstance(response, str):
        print(f"    [FIX] LLM 返回空")
        return False

    new_principle = response.strip()
    if len(new_principle) < 50:
        print(f"    [FIX] LLM 输出过短，跳过")
        return False

    # 替换 Principle 章节
    new_content = re.sub(
        r"(##\s*Principle\s*\n).*?(?=\n##\s)",
        lambda m: m.group(1) + new_principle + "\n",
        full_content,
        count=1,
        flags=re.DOTALL,
    )

    if new_content == full_content:
        print(f"    [FIX] 未匹配到 Principle 章节，跳过")
        return False

    # 备份原文件
    backup_path = skill_path + ".bak"
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(full_content)

    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"    [FIX] 已修正 Principle（原文件备份: {os.path.basename(backup_path)}）")
    return True


def print_summary(reports: list[dict[str, Any]]) -> None:
    """打印汇总报告。"""
    print()
    print("=" * 60)
    print("反查汇总报告")
    print("=" * 60)

    by_severity = {"low": 0, "medium": 0, "high": 0, "error": 0, "skip": 0}
    for r in reports:
        sev = r.get("severity", "error")
        by_severity[sev] = by_severity.get(sev, 0) + 1

    total = len(reports)
    print(f"总计: {total} 个 skill")
    print(f"  OK (差异小):     {by_severity['low']}")
    print(f"  WARN (有差异):   {by_severity['medium']}")
    print(f"  DIFF (差异大):   {by_severity['high']}")
    print(f"  ERROR (查询失败): {by_severity['error']}")
    print(f"  SKIP (无 CVE):   {by_severity['skip']}")

    # 列出差异大的
    high_diff = [r for r in reports if r.get("severity") == "high"]
    if high_diff:
        print()
        print("⚠️  差异较大的 skill（建议人工核查或加 --fix 修正）:")
        for r in high_diff:
            print(f"  - {r['skill_path']} (CVE={r['cve_id']}, overlap={r['overlap_ratio']})")
            print(f"    NVD: {r['nvd_description'][:120]}")
            print(f"    原 Principle: {r['principle_excerpt'][:120]}")

    # 输出 JSON 报告
    report_path = os.path.join(_PROJECT_ROOT, "reports", "nvd_verification_report.json")
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(reports, f, ensure_ascii=False, indent=2)
    print()
    print(f"完整报告已写入: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="用 NVD 权威数据反查修正 exploit skill 的 Principle")
    parser.add_argument("--skills-root", default=os.path.join(_PROJECT_ROOT, "skills"),
                        help="skills 根目录")
    parser.add_argument("--offline", action="store_true",
                        help="离线模式，只用已缓存的 NVD 数据")
    parser.add_argument("--fix", action="store_true",
                        help="差异大时由 LLM 自动修正 Principle（需 LLM 配置）")
    args = parser.parse_args()

    reports = run_verification(
        skills_root=args.skills_root,
        offline=args.offline,
        fix=args.fix,
    )
    print_summary(reports)

    # 退出码：有 high 差异时返回 1
    has_issues = any(r.get("severity") == "high" for r in reports)
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()
