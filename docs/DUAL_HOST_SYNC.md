# 双端 Git 同步工作流

本项目同时在 **Windows 主机**（开发）和 **Kali 虚拟机**（执行渗透）两端运行。
通过 GitHub `momo0410/agent-new` 仓库作为单一来源做同步。

## 边界

**同步**：
- 所有源代码 (`src-python/`, `batch_pentest.py`, ...)
- 文档 (`docs/`)
- 内置 skill (`skills/builtin/`, `skills/experimental/`, `skills/exploit-skills/`, `skills/imported/`)
- 测试 (`src-python/tests/`)

**不同步（双端独立）**：
- `reports/R*/` — 渗透批次的报告产物
- `reports/reflection_*.json` — Reflection 阶段输出
- `skills/.experience/` — 运行时累积的 ExperienceStore
- `skills/learned/draft/`、`learned/active/`、`learned/deprecated/` — 运行时生成的 skill
- `skills/.cache/` — embedding 索引缓存
- `.venv/` — Python 虚拟环境
- `*.tar.gz`、`hydra.restore` 等临时文件

这些已在 `.gitignore` 排除。运行时数据双端独立累积；要交换时用 scp / tar zip 一次性传。

## Windows 主机端

```bash
cd /d/agent-new

# 拉取 Kali 端可能推上来的更新
git pull origin master

# 在 Windows 上做代码修改
# ... 编辑 src-python/... ...

# 提交
git add <files>
git commit -m "..."
git push origin master
```

## Kali 端（192.168.136.143）

**首次设置**（仅做一次）：
```bash
ssh root@192.168.136.143
git config --global --add safe.directory /root/agent-new

# 如果 /root/agent-new 是从 tar 解出来的（没有 .git），用下面的方式接入仓库：
cd /root/agent-new
git clone --depth=1 https://github.com/momo0410/agent-new.git /tmp/agent-new-remote
cp -r /tmp/agent-new-remote/.git /root/agent-new/.git
rm -rf /tmp/agent-new-remote
git config user.email "kali-runner@sdit.local"
git config user.name "kali-runner"
git config core.autocrlf input
git config core.eol lf
git checkout HEAD -- .   # 强制工作树等于 HEAD
```

**日常使用**：
```bash
ssh root@192.168.136.143
cd /root/agent-new
git pull origin master --ff-only      # 拉新代码
# ... 跑渗透 ...
```

**在 Kali 端改了代码要 push（罕见）**：
```bash
# Kali 上 push 需要 GitHub Token / SSH key
# 简单做法：改完用 scp 拉回 Windows 端去 commit
scp <修改后的文件> T1367@<windows-ip>:/d/agent-new/...
# 然后在 Windows 端正常 commit push
```

## 跑批量渗透的标准姿势

**Windows 端**：开发 + 推代码
```bash
cd /d/agent-new
git pull
# 改 batch_pentest.py、agent.py 等
git add -A && git commit -m "..." && git push
```

**Kali 端**：拉代码 + 跑渗透
```bash
ssh root@192.168.136.143
cd /root/agent-new && git pull --ff-only
source .venv/bin/activate
SDIT_SSH_HOST=local nohup python3 batch_pentest.py \
  --targets <list> --max-rounds 15 \
  --out-root reports/R<N> > reports/R<N>.log 2>&1 &
```

**回收产物**（渗透完成后）：
```bash
# Kali 端打包
ssh root@192.168.136.143 'cd /root/agent-new && tar czf /tmp/R<N>.tar.gz reports/R<N>/ reports/R<N>.log skills/.experience/ skills/learned/'

# Windows 端拉回
scp root@192.168.136.143:/tmp/R<N>.tar.gz /c/Users/T1367/Desktop/
```

## 验证同步状态

任一端执行：
```bash
git log --oneline -5      # 看 HEAD
git status -s             # 应该是空（所有产物都 ignore 了）
git diff --stat HEAD      # 应该是空
```

如果两端 HEAD 一致，且各自 `git status` 干净，就同步完成。
