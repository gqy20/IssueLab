# IssueLab 部署配置指南

> 系统管理员和维护者的完整部署手册

## 目录

- [1. 前置要求](#1-前置要求)
- [2. GitHub App 配置](#2-github-app-配置)
- [3. Secrets 配置](#3-secrets-配置)
- [4. Dispatch 系统配置](#4-dispatch-系统配置)
- [5. 开发环境配置](#5-开发环境配置)
- [6. 监控和维护](#6-监控和维护)

---

## 1. 前置要求

### 1.1 系统要求

- Python >= 3.12
- uv (Python 包管理器)
- GitHub 账户（个人或组织）

### 1.2 权限检查清单

- [ ] 有权限创建 GitHub App
- [ ] 有权限在主仓库配置 Secrets
- [ ] 有权限在 fork 仓库配置 Secrets
- [ ] 有 MiniMax API Token

### 1.3 所需服务

| 服务 | 用途 | 获取方式 |
|------|------|----------|
| GitHub App | 跨仓库触发权限 | https://github.com/settings/apps/new |
| MiniMax API | MiniMax 模型调用 | https://platform.minimaxi.com/user-center/basic-information/interface-key |

---

## 2. GitHub App 配置

### 2.1 为什么使用 GitHub App？

| 特性 | PAT | GitHub App |
|------|-----|------------|
| 权限控制 | 全局权限 | 细粒度权限 |
| Token 过期 | 手动管理 | 自动刷新 |
| Fork 支持 | ⚠️ 受限 | ✅ 完整支持 |
| 多用户扩展 | ❌ 需要每个人的 PAT | ✅ 动态生成 Token |

### 2.2 创建 GitHub App

**步骤 1：访问创建页面**

- 个人账户：https://github.com/settings/apps/new
- 组织账户：https://github.com/organizations/YOUR_ORG/settings/apps/new

**步骤 2：基本信息**

```yaml
GitHub App name: IssueLab Dispatcher
Homepage URL: https://github.com/YOUR_USERNAME/IssueLab
Description: Cross-repository agent dispatcher for IssueLab
```

**步骤 3：权限配置**

Repository permissions:

- [x] **Actions: Read and write** ✅ (必需，用于触发 workflow_dispatch)
- [x] **Contents: Read-only** ✅ (必需，读取仓库内容)
- [x] **Metadata: Read-only** ✅ (自动选中，基础元数据)

**步骤 4：Webhook**

- [ ] Active ❌ (取消勾选，我们不使用 webhook)

**步骤 5：安装范围**

- 选择 **Any account** (允许其他用户安装)

**步骤 6：创建**

- 点击 **Create GitHub App**

### 2.3 生成 Private Key

1. 在 App 设置页面找到 "Private keys" 部分
2. 点击 **Generate a private key**
3. 下载 `.pem` 文件并**妥善保存**
4. 记录 **App ID**（在页面顶部）

### 2.4 安装 App

**安装到主仓库：**

1. 在 App 设置页面，点击 **Install App**
2. 选择你的账户
3. 选择 **Only select repositories**
4. 勾选主仓库（如 `gqy20/IssueLab`）
5. 点击 **Install**

**通知用户安装到 fork 仓库：**

每个 fork 用户需要独立安装：
1. 访问 `https://github.com/apps/YOUR_APP_NAME`
2. 点击 **Install**
3. 选择自己的 fork 仓库
4. 点击 **Install**

### 2.5 验证配置

检查 Installation ID：

```bash
# 使用 GitHub CLI
gh api /app/installations --jq '.[] | {account: .account.login, id: .id}'
```

应该看到主仓库和各个 fork 仓库的 Installation ID。

---

## 3. Secrets 配置

### 3.1 主仓库 Secrets

在主仓库 `Settings → Secrets and variables → Actions` 添加：

| Secret 名称 | 必需 | 说明 | 获取方式 |
|------------|------|------|----------|
| `ISSUELAB_APP_ID` | ✅ | GitHub App ID | App 设置页面顶部 |
| `ISSUELAB_APP_PRIVATE_KEY` | ✅ | Private Key 完整内容 | 下载的 .pem 文件内容 |
| `ANTHROPIC_API_TOKEN` | ✅ | MiniMax API Token | https://platform.minimaxi.com/user-center/basic-information/interface-key |
| `ANTHROPIC_BASE_URL` | ⚪ | API Base URL | 默认：https://api.minimaxi.com/anthropic |
| `ANTHROPIC_MODEL` | ⚪ | 模型名称 | 默认：MiniMax-M2.1 |

> 💡 **提示**：也可以使用智谱 GLM Coding Plan，在智谱开放平台（https://open.bigmodel.cn/）申请后，将 API Token 填入 `ANTHROPIC_API_TOKEN`，`ANTHROPIC_BASE_URL` 设为智普 API 地址。

**添加 Private Key 的正确方式：**

```bash
# 复制整个 .pem 文件内容，包括头尾
cat your-app.2024-01-01.private-key.pem | pbcopy
```

粘贴到 Secret 时保持原样：
```
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA...
...完整内容...
-----END RSA PRIVATE KEY-----
```

### 3.2 Fork 仓库 Secrets（用户配置）

每个 fork 用户在自己的仓库 `Settings → Secrets and variables → Actions` 添加：

| Secret 名称 | 必需 | 说明 |
|------------|------|------|
| `ANTHROPIC_API_TOKEN` | ✅ | 用户自己的 API Token（MiniMax 或智谱） |
| `ANTHROPIC_BASE_URL` | ⚪ | 可选，默认 https://api.minimaxi.com/anthropic |
| `ANTHROPIC_MODEL` | ⚪ | 可选，默认 MiniMax-M2.1 |
| `GITHUB_APP_ID` | ✅ | GitHub App ID |
| `GITHUB_APP_PRIVATE_KEY` | ✅ | GitHub App 私钥 |

**GitHub App 配置步骤：**

1. 安装 IssueLab GitHub App 到 fork 仓库
2. 在 App 设置页生成私钥
3. 将 `GITHUB_APP_ID` 与 `GITHUB_APP_PRIVATE_KEY` 添加到 Secrets

### 3.3 安全最佳实践

- ✅ 定期轮换 API Keys
- ✅ 为每个环境使用不同的 Keys
- ✅ 不要在代码或日志中打印 Secrets
- ✅ 使用 GitHub Secrets 而非硬编码
- ✅ 限制 GitHub App 的最小权限

---

## 4. Dispatch 系统配置

### 4.1 Dispatch 模式

IssueLab 支持两种 Dispatch 模式：

| 模式 | 适用场景 | 触发方式 |
|------|---------|---------|
| `repository_dispatch` | 主仓库、非 fork 仓库 | 发送 event_type |
| `workflow_dispatch` | **Fork 仓库（推荐）** | 触发指定 workflow |

### 4.2 注册用户 Agent

在 `agents/<username>/` 创建 agent.yml：

```yaml
# agents/username/agent.yml
owner: username                    # 必需：你的 GitHub ID
display_name: "Your Name"
contact: "your@email.com"

# Fork 仓库信息
repository: username/IssueLab
branch: main

# Dispatch 模式（fork 仓库推荐）
dispatch_mode: workflow_dispatch
workflow_file: user_agent.yml

# 触发条件
triggers:
  - "@username"

enabled: true
type: reviewer
```

### 4.3 Workflow 配置

**Fork 仓库的 workflow 文件** (`.github/workflows/user_agent.yml`):

```yaml
name: User Agent

on:
  workflow_dispatch:
    inputs:
      issue_number:
        required: true
      issue_title:
        required: true
      issue_body:
        required: true
      comment_body:
        required: false
      main_repo:
        required: true

jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      - name: Install uv
        run: pip install uv
      
      - name: Install dependencies
        run: uv sync
      
      - name: Run agent
        env:
          ANTHROPIC_AUTH_TOKEN: ${{ secrets.ANTHROPIC_AUTH_TOKEN }}
          ANTHROPIC_BASE_URL: ${{ secrets.ANTHROPIC_BASE_URL }}
          ANTHROPIC_MODEL: ${{ secrets.ANTHROPIC_MODEL }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          uv run python -m issuelab agent \
            --agent-name $(cat agents/*/agent.yml | grep "^name:" | cut -d' ' -f2) \
            --issue-number ${{ github.event.inputs.issue_number }} \
            --main-repo ${{ github.event.inputs.main_repo }}
```

### 4.4 测试 Dispatch

**测试方式 1：通过主仓库**

在主仓库 Issue 中评论：
```
@username 请帮我分析这个问题
```

**测试方式 2：手动触发**

```bash
# 使用 GitHub CLI
gh workflow run user_agent.yml \
  -R username/IssueLab \
  -f issue_number=123 \
  -f issue_title="Test Issue" \
  -f issue_body="Test content" \
  -f main_repo="gqy20/IssueLab"
```

**验证成功标志：**

- ✅ Fork 仓库的 Actions 被触发
- ✅ Agent 成功回复评论到主仓库
- ✅ 没有权限错误

---

## 5. 开发环境配置

### 5.1 安装 uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# 验证安装
uv --version
```

### 5.2 安装依赖

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/IssueLab.git
cd IssueLab

# 安装所有依赖（包括开发依赖）
uv sync --group dev

# 或仅安装运行时依赖
uv sync
```

项目依赖（`pyproject.toml`）：
```toml
dependencies = [
    "claude-agent-sdk>=0.1.27",
    "pyyaml>=6.0",
    "requests>=2.31.0",
    "pyjwt>=2.8.0",
    "cryptography>=41.0.0",
]

[project.optional-dependencies]
test = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0", "pytest-cov>=7.0.0"]
dev = ["ruff>=0.8.0", "mypy>=1.13.0", "pre-commit>=4.0.0"]
```

### 5.3 配置 Pre-commit Hooks

```bash
# 安装 pre-commit
uv sync --group dev

# 安装 git hooks
uv run pre-commit install

# 手动运行检查
uv run pre-commit run --all-files
```

**Pre-commit 检查项：**
- 代码格式化（ruff format）
- 代码检查（ruff check）
- 类型检查（mypy）
- YAML 语法检查
- 去除尾随空格

### 5.4 本地测试

```bash
# 运行测试
uv run pytest

# 运行特定测试
uv run pytest tests/test_executor.py

# 带覆盖率
uv run pytest --cov=src/issuelab

# 测试单个 agent
uv run python -m issuelab agent --agent-name test --issue-number 1
```

### 5.5 调试技巧

**启用调试日志：**

```bash
export ISSUELAB_LOG_LEVEL=DEBUG
uv run python -m issuelab agent --agent-name test --issue-number 1
```

**本地测试 dispatch 脚本：**

```bash
cd scripts
uv run python dispatch_to_users.py --help
```

---

## 6. 监控和维护

### 6.1 日志下载

所有 workflow 运行都会生成日志 artifact。

**下载方式 1：GitHub 网页界面**

1. 进入仓库 **Actions** 页面
2. 选择运行记录
3. 在 **Artifacts** 区域下载日志文件

**下载方式 2：GitHub CLI**

```bash
# 列出最近的运行
gh run list -R YOUR_USERNAME/IssueLab

# 下载特定运行的 artifacts
gh run download RUN_ID -R YOUR_USERNAME/IssueLab
```

**日志文件命名规则：**

| Workflow | 日志文件名 | 内容 |
|----------|-----------|------|
| orchestrator.yml | `review_<issue>.log` | /review 命令日志 |
| orchestrator.yml | `triage_<issue>.log` | /triage 命令日志 |
| dispatch_agents.yml | `dispatch_<issue>.log` | Dispatch 过程日志 |
| observer.yml | `observer_<run_id>.log` | Observer 扫描日志 |
| user_agent.yml | `user-agent-logs-<issue>-<run_id>` | 用户 agent 执行日志 |

### 6.2 性能监控

**关键指标：**

- API 调用次数（避免超限）
- Workflow 运行时间
- Token 生成成功率
- Agent 响应时间

**查看 API 使用量：**

```bash
# MiniMax API 用量
# 访问：https://platform.minimaxi.com/user-center/basic-information/interface-key
```

**GitHub Actions 配额：**

- 公开仓库：无限制
- 私有仓库：免费账户 2000 分钟/月

### 6.3 常见错误排查

**错误 1：`Invalid API key`**

```
❌ 症状：Agent 运行失败，提示 API key 无效
✅ 解决：检查 ANTHROPIC_API_TOKEN secret 是否正确配置
```

**错误 2：`Resource not accessible by integration`**

```
❌ 症状：无法触发 fork 仓库 workflow
✅ 解决：
  1. 确认 GitHub App 已安装到 fork 仓库
  2. 检查 App 权限包含 Actions: Read and write
  3. 确认使用 workflow_dispatch 模式
```

**错误 3：`Bad credentials`**

```
❌ 症状：无法创建评论或获取 Issue 信息
✅ 解决：
  1. 检查 GitHub App 是否安装并配置 `GITHUB_APP_ID` / `GITHUB_APP_PRIVATE_KEY`
  2. 确认 PAT 包含 repo 和 workflow 权限
  3. 检查 PAT 是否过期
```

**错误 4：`Workflow file not found`**

```
❌ 症状：Dispatch 失败，找不到 workflow 文件
✅ 解决：
  1. 确认 fork 仓库有 .github/workflows/user_agent.yml
  2. 检查 registry 文件的 workflow_file 字段
  3. 确认 workflow 文件有 workflow_dispatch 触发器
```

### 6.4 升级和迁移

**升级 Claude Agent SDK：**

```bash
# 检查当前版本
uv pip list | grep claude-agent-sdk

# 升级到最新版本
uv sync --upgrade-package claude-agent-sdk

# 或指定版本
uv pip install "claude-agent-sdk>=0.1.27"
```

**数据库迁移（如果使用）：**

目前项目不使用数据库，所有状态通过 GitHub Issues 管理。

**配置迁移：**

从旧版本迁移时，注意：
- 旧版 `agents/_registry/*.yml` 已合并到 `agents/<user>/agent.yml`
- 更新 workflow 文件到最新版本
- 检查 secrets 名称是否变更

---

## 相关文档

- [项目指南](./PROJECT_GUIDE.md) - 用户和贡献者指南
- [技术设计](./TECHNICAL_DESIGN.md) - 架构和技术细节

---

最后更新：2026-02-03
