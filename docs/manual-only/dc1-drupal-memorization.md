# DC-1 Drupal 背题决策卡（.139 专用强化版）

> 用途：这是一份给模型“背题”的人工参考笔记，只服务当前 .139 / DC-1 / Drupal 类目标的优先推理。
>
> 约束：它不应该替代通用逻辑，但当目标是 `192.168.136.139` 时，应优先参考这份资料来决定攻击顺序、成功判定和失败转移。

## 一句话判断

如果目标表现为：

- `80/http` 是主入口
- 指纹或漏洞信息指向 `Drupal 7.x`
- 已验证 `CVE-2014-3704`

那么默认把它当成：

- `web_app`
- `cms_candidate`
- `drupal_cve2014_3704_target`

并优先走：

- `web_entry -> drupal_exploit -> app_login_or_shell -> local_config_harvest -> db_followup -> app_takeover -> priv_esc`

## 当前题型的核心原则

1. 不要平均打所有端口
2. 不要让 SSH brute 和 RPC 验证抢走 Drupal 主线的预算
3. `searchsploit` 只是找到利用线索，不算利用成功
4. `python3 34992.py ...` 跑完但没有明确证据，不算利用成功
5. `curl` 返回 200 或页面内容，不自动等于登录成功
6. 只要 `CVE-2014-3704` 还没被明确证伪，`80` 不应过早 exhausted

## 标准攻击顺序

### 阶段 1：确认 Drupal 主线

优先检查：

- Web 指纹里是否出现 Drupal
- `nmap http-vuln-cve2014-3704`
- `searchsploit drupal 7`
- exploit-db 是否能定位到 `34992.py` / Drupalgeddon 相关脚本

如果已经满足：

- Drupal 7.x 信号成立
- `CVE-2014-3704` 已验证

则默认进入：

- `drupal_exploit_focus`

### 阶段 2：获取 exploit 并执行

优先动作：

1. `searchsploit drupal 7`
2. `searchsploit -m 34992.py`
3. 查看 exploit 使用方式
4. 执行 Drupal 漏洞利用

这里的重点不是“拿到 exploit 文件就算推进”，而是：

- exploit 文件是否真正执行
- 执行后是否新增用户、登录能力、shell、会话或明确成功提示

## 成功 / 失败判定

### 下面这些算成功推进

- 成功创建 Drupal 用户
- 成功获得有效登录凭据
- 成功登录 `/user/login` 或后台，且有明确成功证据
- 成功得到 Web shell / 命令执行 / session
- 成功新增 `credentials` / `sessions` / `artifacts.config_paths`

### 下面这些不算成功

- 仅 `searchsploit` 找到利用脚本
- 仅把 `34992.py` 复制到本地
- `python3 34992.py ...` 跑完但输出为空
- `curl` 只是返回 200 / 页面 HTML
- 只有漏洞存在证据，没有利用落地证据

### 未成功前禁止做的事情

只要下面这些证据一个都没有：

- `session`
- `interactive_session_connected`
- 明确 shell / 命令执行证据
- 明确登录成功证据
- 新增凭据或可用账户

那么默认视为：**还没有打进去**。

在这种情况下，禁止：

- 执行 `local:` 开头的 shell 检查
- 执行 `whoami`、`id`、`hostname` 这类本地 post 命令
- 检查 `/tmp/drupal_shell`、`/tmp/*shell*` 之类假定 shell 文件
- 进入 `post` 风格任务
- 把“应该已经有 shell”当成事实

模型必须先回答：

- 我是否已经有明确可用的访问能力？
- 证据是 session、login 还是命令执行？

如果回答不出来，就继续停留在 `exploit`，而不是进入 `post`。

### 遇到这些情况时，默认判为“未成功，但值得继续”

- exploit 执行 completed，但 stdout/stderr 没有明确成功提示
- 登录请求返回不稳定，但没有明确失败证据
- 只有研究线索，没有 session / credential / artifact 增量

这类情况不能直接把 `80` exhausted。

## 如果 exploit 跑了但没有明确成功证据，下一步怎么转

按这个顺序转，不要发散：

1. 先确认 exploit 脚本参数是否正确
   - 目标 URL
   - 用户名/密码参数
   - 脚本适配的 Drupal 版本范围
2. 再检查 exploit 输出说明
   - 是否提示创建用户成功
   - 是否提示需要手动登录验证
3. 再转应用层验证
   - `/user/login`
   - 新建用户是否可登录
4. 若应用层仍无证据
   - 保持 `80` 为第一优先面
   - 补轻量 Drupal 特征确认
   - 不要立即切回 SSH brute
5. 只有在明确看到多种 Drupal 路线都失败、且无新增证据时，才允许降低 80 的优先级

## 不推荐的错误动作

### 错误 1：Drupal 主线未跑透，就回去爆 SSH

如果同时满足：

- `CVE-2014-3704` 已验证
- exploit 已找到
- Web 仍是最强主入口

那么 SSH brute 默认降权。

### 错误 2：RPC 和 55535 反复上桌

RPC 在这题里通常不是第一主线。
除非 Drupal 主线被明确证伪，否则：

- `111`
- `55535`

只能作为陪衬验证面，不能压过 `80`。

### 错误 3：把 research 当成 exploit 完成

下面这些都只是 research，不是 exploit 成功：

- `searchsploit drupal 7`
- `searchsploit -m 34992.py`
- 看到 exploit-db 结果
- 看到 Drupal 相关漏洞说明

## 进入后渗透之前，模型必须问自己

在宣布主线推进前，至少确认一项：

- 有没有新增 session
- 有没有新增凭据
- 有没有新增配置路径
- 有没有明确登录成功证据
- 有没有命令执行证据

如果这些都没有，就还在 exploit 阶段，不应假装进入 post。

### 允许进入 post 的最小门槛

至少满足以下任一条件：

- 已有可用 session
- 已有明确 shell / RCE 证据
- 已有明确后台/应用登录成功证据
- 已有能被复用的有效凭据，并且已验证可用

如果不满足这些门槛：

- 不允许执行本地 post 检查
- 不允许把 post 当成“确认 shell 是否存在”的试探阶段
- 不允许用假定路径来证明已经打进目标

## 80 端口的特殊规则

对 `.139`：

- `80` 是默认第一优先面
- 只要 `CVE-2014-3704` 还在且没被证伪，就不要轻易 exhausted
- `80` 的 exploit / login / CMS follow-up 默认优先于 SSH brute 和低收益 RPC

### 80 可以 exhausted 的前提

只有在以下条件大部分成立时，才允许把 `80` 降为 exhausted：

- Drupal 主线已经被明确尝试过多种方式
- exploit 参数与入口已经核对过
- 应用层登录验证已经做过
- 仍然没有 session / credential / artifact 增量
- 有明确失败证据，而不是空输出或未判定结果

如果只是：

- exploit 空输出
- 登录返回不明确
- 只有 research 结果

那么 `80` 仍然不该 exhausted。

## 建议的失败转移顺序

如果 Drupal exploit 不顺，转移顺序应该是：

1. 调整 exploit 参数
2. 做应用层登录验证
3. 补 Drupal 特征确认或路径确认
4. 检查是否能从 exploit 结果拿到账户线索
5. 再考虑其他辅助面

不是：

1. exploit 没立即成功
2. 立刻爆 SSH
3. 再去反复扫 RPC

## 给模型的直接指令

当目标是 `192.168.136.139` 时，默认遵守：

- 把这份文件当成优先 playbook
- 优先推进 `80/Drupal/CVE-2014-3704`
- 研究结果不等于利用成功
- 无明确成功证据时，不要把 `80` 过早 exhausted
- 不要让 SSH brute 和 RPC 侧线抢走主流程

## 使用边界

- 这是背题决策卡，不是真理
- 它只用于帮助模型在 `.139` / DC-1 / Drupal 类目标上更快进入正确主线
- 它不应该自动覆盖所有靶机
- 如果当前证据明确反驳 Drupal 主线，应服从实时证据
