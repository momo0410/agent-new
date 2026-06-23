# Skill Spec v1

## 目标

`Skill Spec v1` 是当前仓库的统一声明式技能描述格式，用于把 builtin、generated、experimental 三类 skill 收敛到同一套：

- 可版本化
- 可校验
- 可测试
- 可审核
- 可落盘
- 与 SKILL.md 知识文档共存

本版本不替换现有执行引擎，而是把声明层统一到 spec，配合 SkillLoader + SkillMdParser 实现 json+md 共存加载。

## 目录结构

仓库根目录新增：

```text
skills/
  builtin/
  generated/
  experimental/
```

语义：

- `skills/builtin`: 受控内建技能，默认可被 loader 自动加载
- `skills/generated`: 生成式技能落盘目录，默认 `draft`，不会自动启用
- `skills/experimental`: 实验性技能目录，默认不进入默认 registry，需显式 opt-in

## Schema 入口

代码入口：

- `app.services.skill_engine.skill_loader.SkillLoader`
- `app.services.skill_engine.skill_md_parser.SkillMdParser`

Pydantic schema 会导出 JSON Schema：

```python
from app.services.skill_engine import SkillLoader

loader = SkillLoader("skills/")
skills = loader.load_all()
```

## 顶层字段

`SkillSpec` 的核心字段如下：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `schema_version` | literal | 是 | 当前固定为 `skill-spec/v1` |
| `name` | string | 是 | skill 唯一名称 |
| `version` | semver string | 是 | 版本号，如 `1.0.0` |
| `description` | string | 是 | skill 描述 |
| `category` | string | 是 | 类别，如 `investigation` |
| `status` | enum | 是 | `draft` / `active` / `disabled` / `deprecated` |
| `source` | enum | 是 | `builtin` / `generated` / `experimental` / `legacy_python` / `runtime` |
| `parameters` | list | 否 | 输入参数定义，沿用 `SkillParameter` |
| `steps` | list | 是 | 执行步骤定义 |
| `required_context_keys` | list | 否 | 运行时上下文依赖 |
| `output_template` | string | 否 | 报告模板 |
| `tags` | list | 否 | 标签 |
| `owners` | list | 否 | 维护者 |
| `knowledge_file` | string | 否 | 同目录下 SKILL.md 的文件名，供 LLM 上下文注入 |
| `domain` | string | 否 | 领域（如 cybersecurity） |
| `subdomain` | string | 否 | 子领域（如 digital-forensics） |
| `nist_csf` | list | 否 | NIST CSF 映射标识 |
| `legacy_compatibility` | object | 否 | 旧版 Python class 对应关系（已废弃，保留字段向后兼容） |

## Step 字段

每个 step 的字段如下：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| `id` | string | 否 | 未提供时自动生成 |
| `name` | string | 是 | 步骤名称 |
| `description` | string | 是 | 步骤说明 |
| `tool_name` | string | 是 | 要调用的 tool |
| `parameters` | object | 否 | tool 参数 |
| `depends_on` | list | 否 | 依赖步骤 ID |

## 状态语义

### `draft`

- 用于新生成或待审核 skill
- 可被 loader 发现
- 默认不会自动注册进默认 `SkillRegistry`

### `active`

- 可自动加载
- builtin 和批准后的 generated skill 使用该状态

### `disabled`

- 已停用，不自动加载
- 可用于 rejected / expired generated skill

### `deprecated`

- 历史兼容保留，不建议继续使用
- 默认不自动加载

## 默认加载规则

默认 `SkillLoader` 行为：

- 自动加载 `builtin` + `generated` 中 `status=active` 的 spec
- `generated` 中 `draft` spec 不自动加载
- `experimental` spec 默认不进入默认 registry

可选行为：

- `include_drafts=True`: 允许加载 `draft`
- `allow_experimental=True`: 允许加载 `experimental`

## Generated Skill 规则

生成式技能落盘时会被标准化为 `SkillSpec`：

- `source=generated`
- `status=draft`
- `version=0.1.0`（可后续递增）

这条规则用于保证：

- 生成技能先审后用
- 默认 registry 不会直接启用新生成 skill
- generated skill 可以进入版本化目录并参与审计

## Loader 闭环

当前闭环如下：

1. `SkillLoader` 从仓库根目录 `skills/` 发现 JSON + SKILL.md 文件
2. 同目录 json + md 共存 → mode=hybrid
3. 仅 json → mode=pipeline
4. 仅 md → mode=knowledge
5. 合并后 `LoadedSkill` 包含 json 步骤 + md 知识

默认 registry 组装顺序：

1. 先注册 legacy Python builtin skills
2. 再加载声明式 spec
3. 同名 spec 覆盖同名 legacy skill

这样可以保证：

- spec 成功时，优先使用声明式 skill
- spec 缺失或校验失败时，旧 Python skill 仍可用

## 示例

当前已迁移两个 builtin skill 样例：

- `skills/builtin/capability-check/` (hybrid: skill.json + SKILL.md)
- `skills/builtin/remediation-verification/` (pipeline: skill.json)

## 向后兼容

- `legacy_compatibility` 字段保留但已废弃，不再引用实际 Python class
- 旧的 flat 文件结构（直接放在 builtin/ 下的 .json）已迁移到子目录结构

## JSON + SKILL.md 共存模式

### 设计原则

skill.json 是**执行入口**（规则引擎，声明式步骤调度），SKILL.md 是**知识增强**（AI 调度，供 LLM 上下文参考）。两者不是 1:1 绑定——json 是按需升级件，md 是默认主力。

### 三种模式

| 模式 | 文件组成 | 调度方式 | 适用场景 |
|------|---------|---------|---------|
| `knowledge` | 仅 SKILL.md | LLM 读取 md 自行推理执行 | 探索性、灵活场景 |
| `pipeline` | 仅 skill.json | 引擎按 steps[] 硬控调度 | 纯自动化流水线 |
| `hybrid` | json + md | 引擎调度 steps，同时将 md 注入 LLM 上下文 | 关键节点硬控 + 细节 AI 补全 |

### 目录结构示例

```text
skills/
  builtin/
    capability-check/
      skill.json            # pipeline 或 hybrid 模式
      SKILL.md              # hybrid 时存在
    remediation-verification/
      skill.json
  experimental/
    pentest-agent/
      skill.json            # hybrid 模式
      SKILL.md              # 知识文档
    pentest-recon/
      SKILL.md              # knowledge 模式，仅 md
  generated/
    some-ai-skill/
      SKILL.md              # knowledge 模式
```

### knowledge_file 字段

skill.json 中可通过 `knowledge_file` 显式指向同目录下的 SKILL.md：

```json
{
  "schema_version": "skill-spec/v1",
  "name": "capability-check",
  "knowledge_file": "SKILL.md",
  ...
}
```

不设置时，SkillLoader 会自动发现同目录下的 SKILL.md。

### 调度流程

```
用户请求 → SkillLoader 发现 skill
           ├─ mode=knowledge → 读取 SKILL.md → 注入 LLM system prompt → LLM 自主执行
           ├─ mode=pipeline  → 读取 skill.json → 引擎按 steps[] 调度执行
           └─ mode=hybrid    → 读取 skill.json + SKILL.md
                                → md 内容注入 LLM 上下文
                                → 引擎按 steps[] 调度（LLM 参考 md 补全细节）
```
