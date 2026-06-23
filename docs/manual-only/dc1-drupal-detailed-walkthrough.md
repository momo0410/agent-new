# DC-1 / 192.168.136.139 MODEL PLAYBOOK

目标固定：`192.168.136.139`

用途：供模型在当前目标上优先参考。
不要把它当成通用规则覆盖所有目标。

## PRIORITY

默认优先级：

1. `80/http`
2. `Drupal` 识别与利用
3. `settings.php`
4. `DB credentials`
5. `Drupal users / password reset path`
6. `local privilege escalation`

禁止默认优先：

- SSH brute 早于 Drupal 主线
- RPC 长时间并行抢预算
- 仅凭 research 结果宣布利用成功
- 未拿到 shell/session 就进入 post

## TARGET FACTS TO RECOGNIZE

如果出现以下任一高置信信号，就将目标视为 Drupal/DC-1 类：

- `whatweb` 返回 `MetaGenerator[Drupal 7 ...]`
- 页面中出现 `Drupal 7`
- `nmap`/脚本验证出现 `CVE-2014-3704`
- `searchsploit drupal 7` 命中 Drupalgeddon 相关 exploit
- 页面标题/资源中存在典型 Drupal 特征

一旦命中，默认 focus 为：

- `drupal_exploit_focus`

## REQUIRED CHAIN

默认链路：

- `web_entry`
- `drupal_confirm`
- `drupal_exploit`
- `app_login_or_shell`
- `settings_harvest`
- `db_followup`
- `app_takeover`
- `priv_esc`

## STEP 1: WEB CONFIRM

优先动作：

- `whatweb -v http://192.168.136.139`
- `curl -s http://192.168.136.139/ | grep -i drupal`
- 必要时轻量目录确认

目标：

- 确认 Drupal
- 确认版本范围接近 Drupal 7.x

不要在此阶段默认并行：

- `hydra ssh`
- 大量 RPC follow-up

## STEP 2: EXPLOIT DISCOVERY

允许的研究动作：

- `searchsploit drupal 7`
- `searchsploit -m 34992.py`
- `msfconsole -> search drupal`

注意：

以下都只算 research，不算 exploit success：

- 找到 exploit 名称
- 复制 exploit 文件
- 展示 exploit-db 结果
- 漏洞存在但未执行成功

## STEP 3: DRUPAL EXPLOIT

当已确认 Drupal 7 且存在 `CVE-2014-3704` / Drupalgeddon 路径时，优先尝试：

- `drupal_drupalgeddon2` 路线
- `34992.py` 路线

模型在这一阶段的目标不是“继续研究”，而是：

- 创建用户
- 获得登录能力
- 获得命令执行
- 获得 shell/session

## SUCCESS SIGNALS

以下任一出现，才算 Drupal 主线成功推进：

- 新增可用 Drupal 用户
- 登录 `/user/login` 成功
- 获得可用凭据
- 获得命令执行证据
- 获得 shell / session
- `credentials` / `sessions` / `artifacts.config_paths` 出现新增

## NOT SUCCESS

以下都不算成功：

- `searchsploit` 命中结果
- exploit 文件复制成功
- exploit 执行 completed 但输出为空
- `curl` 返回 200 / HTML 页面
- 只有漏洞存在，没有利用落地证据

## IF EXPLOIT OUTPUT IS EMPTY

若 exploit 执行后：

- `stdout` 为空
- 没有 session
- 没有凭据
- 没有登录成功证据

则执行顺序必须是：

1. 复核 exploit 参数
2. 复核目标 URL / 版本适配
3. 检查 exploit 输出说明
4. 尝试应用层登录验证
5. 继续把 `80` 保持为第一优先面

不要立刻：

- exhausted `80`
- 切到 `post`
- 假设已经有 shell
- 把 SSH brute 提到主线前面

## POST GATE

没有以下任一证据时，禁止进入 post：

- `session`
- `interactive_session_connected`
- 明确 shell / RCE 证据
- 明确后台/应用登录成功证据
- 已验证可复用的有效凭据

在未满足前，禁止：

- `local:` shell 检查
- `whoami`
- `id`
- `hostname`
- 检查 `/tmp/drupal_shell`
- 假设 shell 文件存在

## STEP 4: AFTER SHELL

一旦获得 shell，立刻优先：

- 找 `settings.php`
- 找数据库配置
- 找 Drupal 目录中的脚本
- 读取用户/权限相关信息

优先路径：

- `sites/default/settings.php`
- Drupal 目录中的 `scripts/password-hash.sh`

## STEP 5: DATABASE FOLLOW-UP

如果从 `settings.php` 或配置中拿到 DB 凭据：

- 先登录 MySQL
- `show databases;`
- `use drupal;`
- `show tables;`
- `select * from users;`

目标：

- 确认 Drupal 用户表
- 确认账户/哈希
- 为应用层接管准备条件

## STEP 6: APP TAKEOVER

如果已经定位到 `password-hash.sh`：

- 生成 Drupal 接受的密码哈希
- 更新 `users` 表中的用户密码
- 回到 Web 登录

重点：

- 这一步是“应用层接管”
- 不是单纯数据库浏览

## STEP 7: PRIV ESC

只有在已有 shell 或明确系统访问能力时，才进入本地提权：

- `/etc/passwd`
- `find / -perm -u=s -type f 2>/dev/null`
- 关注 `find` 一类可利用点

目标：

- root shell
- `/root` 访问

## 80 SURFACE PROTECTION

对 `192.168.136.139`：

- `80` 是 protected primary surface
- 只要 Drupal/CVE-2014-3704 主线未被明确证伪，`80` 不应轻易 exhausted
- `80` 的 exploit/login follow-up 优先于 SSH 与 RPC

只有在以下条件大部分成立时，才允许降低 `80`：

- Drupal 主线已尝试多种方式
- exploit 参数已核对
- 应用层登录验证已做过
- 没有 session / credential / artifact 增量
- 有明确失败证据，而不是空输出

## SSH / RPC RULES

默认：

- SSH 只作为低优先级陪衬面
- RPC/55535 只作为辅助验证面

除非：

- Drupal 主线被明确证伪
- 或已拿到凭据需要复用

否则不要让它们抢占主线预算。

## MODEL BEHAVIOR

对当前目标，模型应优先遵守：

- `Drupal first`
- `exploit before brute force`
- `proof before post`
- `settings.php before random lateral ideas`
- `DB follow-up after config harvest`
- `no shell assumption without evidence`

## SOURCE MEMORY

此 playbook 依据公开文章路径整理，用于帮助模型记住该目标的典型链路：

- Drupal 识别
- Drupalgeddon 利用
- `settings.php`
- MySQL 凭据
- `password-hash.sh`
- 本地提权
