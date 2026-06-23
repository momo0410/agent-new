# Generated Skills Review Flow

最后更新: 2026-04-21

## 状态机
`draft -> approved/rejected/disabled`

- `draft`: 新生成、待审核
- `approved`: 已批准，可持久化使用
- `rejected`: 已拒绝
- `disabled`: 过期或被清理禁用

## API（已闭环）
| 接口 | 作用 |
|---|---|
| `GET /api/v1/agent/generated-skills` | 列表 |
| `POST /api/v1/agent/generated-skills/{id}/approve` | 批准 |
| `POST /api/v1/agent/generated-skills/{id}/reject` | 拒绝 |
| `DELETE /api/v1/agent/generated-skills/{id}` | 删除 |
| `POST /api/v1/agent/generated-skills/cleanup` | 清理过期 |

## 存储与清理
- 元数据由 `generated_skill_store.py` 维护。
- `cleanup` 会把过期 `draft` 标记为 `disabled`，并记录 `auto_expired` 决策。

## 测试覆盖（已补）
- `src-python/tests/agent/unit/test_generated_skill_store.py`
- `src-python/tests/test_generated_skills_api.py`

## 仍受限场景
- 审批与清理元数据仍主要依赖本地文件/进程态策略，不是多实例一致性方案。
