# DC-1 攻击链结构化摘要（基于公开文章提炼）

> 说明：这不是原文转载，而是基于公开文章内容整理出的结构化摘要，适合给软件作为参考知识片段使用。
>
> 原始来源：<https://blog.csdn.net/2401_88307848/article/details/152442104>
> 参考时间：2026-05-06

## 1. 目标类型画像

- 类型：VulnHub 风格 Linux Web 靶机
- 主要入口：HTTP/Drupal CMS
- 常见辅助面：SSH、数据库、本地提权
- 典型链路：
  1. 主机发现与端口探测
  2. Web 指纹识别出 Drupal
  3. 利用 Drupal RCE 拿到 Web Shell
  4. 从本地配置/脚本提取数据库凭据
  5. 进入数据库并修改 CMS 账户口令
  6. 登录后台或站点继续取证
  7. 枚举本地用户与 SUID
  8. 本地提权拿到 root

## 2. 文章里体现出的关键证据信号

### Recon 信号

- `nmap -sV -p- <target>` 后重点关注 `22` 与 `80`
- `whatweb` 或类似指纹工具可识别出 Drupal
- 目录枚举有价值，但不是第一突破口

### Web/CMS 信号

- 页面或指纹显示 `Drupal`
- Web 根目录或站点结构下能找到 Drupal 相关文件
- 出现 `scripts/password-hash.sh` 之类 CMS 自带脚本，说明本地已经有可反哺的应用证据

### 本地后渗透信号

- 存在数据库凭据，例如 `dbuser / R0ck3t`
- 存在 Drupal 用户表 `users`
- 存在本地密码哈希生成脚本
- `/etc/passwd`、`SUID` 文件、Web 根目录脚本是后续提权关键线索

## 3. 攻击链拆解

### 阶段 A：目标发现与画像确认

建议软件在以下条件同时满足时，将目标提升为 `web_app` / `cms_candidate`：

- 开放 `80` 或其他 HTTP 端口
- 指纹中包含 `Drupal`、`Apache`、CMS 特征词
- 页面结构、静态资源、目录结构与 Drupal 相符

建议生成的动作：

- 轻量 HTTP 指纹探测
- CMS 指纹确认
- 目录/已知路径枚举
- 将 `target_profile.tags` 增加：
  - `cms:drupal`
  - `web_entry`
  - `db_backed_webapp`

### 阶段 B：Web 漏洞利用

文章中的主链是：

- 识别 Drupal
- 在 Metasploit 中搜索 Drupal 模块
- 选择 `drupalgeddon2` 方向的利用模块
- 运行后拿到普通 Shell

对软件来说，更可复用的规则不是“必须用 msf”，而是：

- 当 `cms:drupal` 成立时，优先提升 Drupal RCE 候选任务权重
- 候选可以来自：
  - 已知 Drupal RCE 模块
  - Web RCE 探测/验证器
  - CMS 版本与漏洞映射

建议软件沉淀的证据：

- `vulnerabilities`：Drupal RCE 候选/验证结果
- `sessions`：是否获得交互或命令执行会话
- `attack_surfaces`：`80/http` 从 `verified` 进入 `exploited`

### 阶段 C：本地证据反哺数据库

文章显示，拿到 Shell 后，通过本地环境发现数据库凭据，并进入 MySQL。

这对软件最重要的启发是：

- 后渗透阶段不能只收集 stdout
- 要把这些证据结构化沉淀：
  - `credentials`
  - `config_paths`
  - `service_artifacts`

应优先抽取：

- 用户名/密码
- 数据库配置路径
- Web 根目录里的 CMS 脚本路径
- 数据库名、表名、用户表线索

建议自动生成的 follow-up：

- `mysql --connect-timeout=5 -h 127.0.0.1 ...`
- 本地数据库登录验证
- 数据库结构枚举
- CMS 用户表检查

### 阶段 D：应用层账户接管

文章中的具体做法是：

- 利用本地脚本生成 Drupal 可接受的密码哈希
- 更新用户表中的口令
- 回到 Web 端登录

对软件的通用抽象应是：

- 当满足以下条件时，进入 `credential_expansion` 或 `app_account_takeover`：
  - 已拿到 Web Shell
  - 已发现数据库凭据
  - 已识别出 CMS 类型
  - 已定位到用户表或认证存储

注意：

- 这里不应该直接硬编码“总是改密码”
- 更合理的是生成候选策略：
  - 读取用户表
  - 识别哈希类型
  - 定位应用自带哈希生成逻辑
  - 评估登录接管是否可行

### 阶段 E：本地提权

文章中给出的主链是：

- 枚举 `/etc/passwd`
- 枚举 SUID
- 发现 `find` 可被利用
- 借助 SUID `find` 获取 root Shell

对软件的通用规则应是：

- 一旦进入 `post` 且已有 Shell，优先生成：
  - 用户枚举
  - SUID 枚举
  - sudo 枚举
  - 可写路径与计划任务枚举
- 若发现高价值提权证据，再进入 `priv_esc_focus`

建议结构化沉淀：

- `artifacts.service_artifacts`：进程、监听、服务信息
- `artifacts.key_material`：密钥与授权文件
- `artifacts.config_paths`：Web/DB/认证配置
- `credentials`：用户、哈希、明文、来源路径
- `findings`：SUID、sudo、内核/服务提权线索

## 4. 适合软件消费的“通用规则”

### 4.1 不是按 IP 优化，而是按画像优化

不要写：

- `if ip == 192.168.x.139: use drupal chain`

应该写：

- `if cms:drupal and http_entry and local_db_signal -> prioritize web-to-db chain`

### 4.2 适合沉淀到 MD 的内容

适合：

- 目标画像信号
- 阶段切换条件
- 证据触发器
- 通用 follow-up 规则
- 不同阶段应优先抽取的 artifact 类型

不适合：

- 单次实验中的 IP
- 截图说明
- 一次性命令回显
- 对单台靶机特定路径的强依赖结论

### 4.3 可直接转成 planner 规则的触发器

#### Web/CMS 触发器

- `service contains drupal`
- `confirmed_http_ports contains 80`
- `config_paths contains settings.php`

#### DB 跟进触发器

- `credentials contains db creds`
- `config_paths contains my.cnf / settings.php`
- `service_artifacts contains mysql listener`

#### 提权触发器

- `session active`
- `artifacts mention /etc/passwd or /etc/shadow`
- `findings mention suid`

## 5. 是否适合让软件直接使用这个 MD？

结论：**可以用，但不能只靠这一篇，更不能把它当“固定攻略”。**

### 适合的使用方式

- 作为 `知识摘要` 或 `RAG 参考片段`
- 作为 `target_profile -> follow-up` 的规则素材
- 作为报告解释中的“推理依据模板”

### 不适合的使用方式

- 直接把整篇博客原文喂给 agent，当成执行 SOP
- 让 agent 机械复现其中命令
- 把某个 exploit 链写死成唯一解

## 6. 我的建议

如果你的目标是提升 pentest agent 的泛化能力，这份 MD 应该这样用：

1. 放进知识库，但只作为“弱指导”
2. 从中提取规则进入 `planner.py`
3. 把文中的证据点转成 `state.py` 可消费字段
4. 在 `agent.py` 中把 `web_app -> db -> credential_reuse -> priv_esc` 做成状态驱动链

## 7. 对你当前项目最有价值的提炼

最值得落地的不是博客里的具体命令，而是下面这些抽象：

- CMS 识别后，应提升 Web exploit 权重
- Shell 成功后，应强制抽取 DB/Web 配置与凭据
- 数据库凭据应驱动本地 DB 登录验证
- 应用账户接管应作为独立 follow-up 类别
- SUID/本地提权线索应进入独立的 post-focus，而不是和远端验证混在一起

## 8. 推荐下一步

如果要让软件真正受益，建议把这份 MD 再拆成两层：

- `docs/knowledge/dc1-drupal-chain.md`
  - 保留人类可读的攻击链说明
- `docs/knowledge/dc1-drupal-rules.md`
  - 只保留结构化触发条件、证据、优先级建议

这样会比“一篇长博客摘要”更适合 agent 使用。
