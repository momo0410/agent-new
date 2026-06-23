"""
将 Anthropic Cybersecurity Skills 压缩包的 754 个 skill
以「一个文件夹 = 一个 skill」的形式导入到 skills/imported/ 目录。

每个 skill 目录保留原始结构：
  skill-name/
    SKILL.md              # 知识文档（核心）
    references/           # API 参考、标准、工作流
    assets/               # 模板
    scripts/              # 参考实现 (agent.py 等)
    LICENSE

导入后均为 knowledge 模式（LLM 自主执行）。
后续可按需为部分 skill 添加 skill.json 升级为 hybrid/pipeline 模式。
"""

import os
import shutil
import sys

SRC = "/tmp/anthropic-cyber/Anthropic-Cybersecurity-Skills-1.2.0/skills"
DST = "/home/tqc/new-lovely4.23/new-lovely/skills/imported"


def main():
    if not os.path.isdir(SRC):
        print(f"源目录不存在: {SRC}")
        sys.exit(1)

    os.makedirs(DST, exist_ok=True)

    skill_dirs = sorted([
        d for d in os.listdir(SRC)
        if os.path.isdir(os.path.join(SRC, d))
    ])

    imported = 0
    skipped = 0

    for skill_name in skill_dirs:
        src_path = os.path.join(SRC, skill_name)
        dst_path = os.path.join(DST, skill_name)

        if os.path.exists(dst_path):
            shutil.rmtree(dst_path)

        shutil.copytree(src_path, dst_path)
        imported += 1

        if imported % 100 == 0:
            print(f"  已导入 {imported}/{len(skill_dirs)}...")

    print(f"\n完成: 导入 {imported} 个 skill 到 {DST}")

    subdomain_stats = {}
    for skill_name in sorted(os.listdir(DST)):
        md_path = os.path.join(DST, skill_name, "SKILL.md")
        if not os.path.isfile(md_path):
            continue
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                import yaml
                try:
                    fm = yaml.safe_load(content[3:end])
                    sd = fm.get("subdomain", "unknown")
                    subdomain_stats[sd] = subdomain_stats.get(sd, 0) + 1
                except:
                    pass

    print(f"\n按子域分布:")
    for sd, count in sorted(subdomain_stats.items(), key=lambda x: -x[1])[:20]:
        print(f"  {sd:35s} {count}")


if __name__ == "__main__":
    main()
