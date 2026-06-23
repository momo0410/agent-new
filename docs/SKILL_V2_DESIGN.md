# Skill 引擎技术设计册

最后更新: 2026-06-23
配套文档: PROJECT_STATUS_AND_GOALS.md（项目定位、现状、本期任务）
本文档定位: 给实施 / 维护 Skill 引擎的人看的技术细节

---

## 一、为什么有 Skill v2.0

### 1.1 v1.0 的局限

旧版 skill 长这样（以 vsftpd 为例）:

```
## When to Use
vsftpd 2.3.4 后门利用。当检测到 vsftpd 2.3.4 时触发。

## Workflow
Step 1: msfconsole -q -x 'use exploit/unix/ftp/vsftpd_234_backdoor; ...'
Step 2: ...
```

问题:

1. 没解释漏洞原理（为什么连 21 端口会触发 6200 bindshell?）
2. 没有检测指纹细节（怎么判断"检测到 vsftpd 2.3.4"?）
3. 没有失败回退（端口 6200 被防火墙拦了怎么办?）
4. 没有迁移规则（今后遇到类似漏洞怎么做?）

结果是 LLM 只会照抄命令，遇到新场景就卡死。

### 1.2 v2.0 的设计目标

让 skill 从"命令手册"变成"知识 + 方法论":

| 章节 | 目的 |
|------|------|
| Principle | 让模型理解为什么 |
| Detection Fingerprint | 让模型自己判断是否适用 |
| Workflow | 给可执行方案（多个方法） |
| Failure Modes | 教推理而非教结论 |
| Generalization | 直接教方法论 |

---

## 二、v2.0 SKILL.md 五段式结构

frontmatter 字段:

- name: 唯一标识
- description: 一句话描述（指纹 + 影响）
- domain: penetration-testing
- subdomain: exploitation
- tags: 标签列表，含 CVE 编号
- cve: CVE-XXXX-XXXX（新增字段）
- severity: critical / high / medium / low（新增字段）
- version: 2.0

正文章节（按此顺序）:

1. **Principle** — 漏洞原理。讲清楚漏洞的内部机制、为什么形成，不是讲怎么打
2. **Detection Fingerprint** — 检测指纹。列出至少 2 条精确条件 + 反例（什么时候不该触发此 skill）
3. **Workflow** — 利用流程。给 2-3 种方法（msf / 手动 / 备选）
4. **Failure Modes** — 失败回退。用表格列出常见失败现象、原因、下一步
5. **Generalization** — 迁移规则。这是最重要的章节。识别这是哪一类漏洞，列出同类漏洞，给通用利用模板
6. **Key Concepts** — 速查表

参考完整范例: skills/exploit-skills/exploit-vsftpd-backdoor/SKILL.md

---

## 三、SkillMatcher 注入策略

文件: src-python/app/services/skill_engine/skill_matcher.py

### 3.1 phase 参数三阶段

format_knowledge_for_prompt() 增加了 phase 参数:

| phase | 注入优先级 | 用途 |
|-------|---------|------|
| planning | Principle > Detection > Generalization > 其他 | 让模型先理解再决策 |
| execution | Workflow > Detection > Failure Modes > Principle | 让模型有可执行步骤 |
| recovery | Failure Modes > Workflow > Detection | 失败后告诉模型怎么回退 |

### 3.2 反过拟合保护

注入头部强制加入指令（核心保护）:

- 重要提示: 以下技能知识是参考方案，并非必须照搬的固定命令序列
- 先理解再行动: 重点看 Principle 和 Detection Fingerprint
- 可以调整: 若不完全匹配，请基于 Principle 推演新方案
- 可以跳过: 若指纹不符，请说明跳过原因
- 重点参考 Generalization 章节的通用方法论
- 失败时查 Failure Modes
- 执行任何命令前先输出适用性判断

这段头部是为了避免模型把 skill 当成"答题模板"机械执行，让它保持思考能力。

---

## 四、SkillGenerator 双层架构

文件: src-python/app/services/skill_engine/skill_generator.py

### 4.1 第一层: 程序提取事实

从 State 中提取:

- 成功执行的命令序列
- 失败的尝试（作为 Failure Modes 素材）
- 找到的凭据
- 触发的 CVE 编号
- 漏洞元数据

### 4.2 第二层: LLM 反思生成

调用 LLM，prompt 包含:

- 渗透事实（JSON 格式）
- v2.0 范例 skill（内置在代码中的 _V2_TEMPLATE_EXAMPLE）
- 严格的输出要求（必须含五段式、必须有 Generalization 等）

输出: 完整的 v2.0 格式 SKILL.md

### 4.3 Fallback 机制

LLM 不可用 / 调用失败 / 输出格式不合格 时:

自动回退到原有的模板拼接版本（_render_skill_md 方法），不会中断渗透流程。

---

## 五、Agent 自升级闭环

文件: src-python/app/services/pentest_agent/agent.py 第 588-608 行

流程:

1. 渗透完成 -> 生成报告
2. from app.services.skill_engine import SkillGenerator
3. from .llm_client import get_llm_client
4. llm_client = get_llm_client()
5. generator = SkillGenerator(SKILLS_ROOT, llm_client=llm_client)
6. generated_skills = generator.generate_from_state(state)
7. 写入 skills/learned/
8. 清空 loader._skills_cache 和 matcher._skills_cache
9. 下一次渗透即可使用刚生成的知识

---

## 六、关于"模型看 skill 还会思考吗"

这是设计 v2.0 时反复权衡的核心问题。

**回答: 不会变弱，反而更强，前提是注入方式正确。**

### 6.1 错误注入方式

prompt: "按照下面 Workflow 步骤执行: Step 1 ... Step 2 ..."

模型会直接照抄，泛用性锁死。

### 6.2 正确注入方式（v2.0 已实现）

prompt: "以下是知识参考，不必照搬。请基于当前情况制定方案。"

加上:

- 先理解原理再决定
- 看反例判断适用性
- 失败模式表格指导回退
- Generalization 提供方法论

模型仍然会思考，且因为有原理和迁移规则，思考更准确。

### 6.3 示例

skill exploit-samba-usermap 的 Generalization 章节写了:

"这是命令注入的经典案例。识别套路:
1. 服务把用户可控字段拼接到 system() 调用
2. 用户输入未做 shell 元字符过滤
3. 注入字符: 反引号、$()、分号、&&、|、换行符"

模型看到这段，下次遇到一个没在 skill 里写过的服务（比如某 IoT 路由器的认证接口），会知道:

- 此服务把 username 拼到 system() -> 命中模式 1
- 尝试反引号或 $() 注入
- 不依赖任何具体 CVE

这就是泛用性的来源。

---

## 七、v3.0 联网检索规划（仅设计，本期不实现）

### 7.1 为什么 v3.0 才做

当前 v2.0 体系仍有三个结构性局限:

- 静态知识截止: 17 个 skill 写死磁盘，新 CVE 不知道
- LLM 训练 cutoff: 2023 年后的漏洞模型完全不知道
- Hallucination: 模型猜的 CVE 编号、利用步骤可能错

但本期定位是"先把教学场景跑稳"，所以联网放到 v3.0。

### 7.2 总体架构（v3.0 落地参考）

四层结构:

A. Planner 决策层 — 看到服务指纹时:
1. 先查本地 SkillMatcher 有无命中，有就用本地
2. 本地无 -> 决定调用 search_online 工具
3. 拿到检索结果 -> 理解 -> 生成计划 -> 执行

B. ToolRegistry — 注册 4 个新工具:
- search_cve(cve_id)
- search_exploit(keyword)
- lookup_msf_module(name)
- lookup_default_creds(product)

C. 新增模块 OnlineSearchService — 路径: src-python/app/services/online_search/
- nvd_client.py — NVD REST API v2.0
- exploit_db_client.py — 本地 searchsploit + 在线
- default_creds_client.py — 公开默认密码
- msf_module_client.py — 查 MSF 模块文档
- cache.py — 三级缓存
- registry.py — 统一入口 + 限流

D. Skill 知识层 — 新增 4 个 builtin skill 用 v2.0 五段式写，告诉模型何时该调用检索:
- skills/builtin/search-cve/SKILL.md
- skills/builtin/search-exploit/SKILL.md
- skills/builtin/search-msf-module/SKILL.md
- skills/builtin/search-default-creds/SKILL.md

### 7.3 与 v2.0 体系的协作

关键设计决策: 联网检索不替代 skill，而是本地缺失时的补充 + 反哺 skill 生成。

优先级顺序:

1. 本地 skill 命中 -> 用本地（快、省钱、Token 少）
2. 本地未命中 -> 联网检索 -> 执行
3. 检索结果 + 执行结果 -> SkillGenerator 提炼 -> 写入 skills/learned/（下次命中第 1 步）

### 7.4 推荐的零配置数据源

- NVD API v2.0 — 无需 key，全部 CVE 详情。地址: services.nvd.nist.gov/rest/json/cves/2.0
- 本地 searchsploit — Kali 自带
- Rapid7 MSF docs — MSF 模块文档。地址: rapid7.com/db/modules/
- cirt.net — 默认密码数据库

需 key 的增强源（可选）: Vulners、GitHub Search、Shodan

### 7.5 缓存策略

三级缓存:

- L1 内存: 同次渗透生命周期，秒回
- L2 磁盘: 用户 cache 目录，7 天 TTL
- L3 永久: skills/knowledge_base/cve/，CVE 信息不变

### 7.6 v3.0 实施时建议参考

到 v3.0 启动时，本节内容会被扩展成独立的 v3.0 设计文档。当前先冻结这份架构草案。
