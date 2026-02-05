# IssueLab 技术设计文档

> 架构设计、技术实现和关键决策

## 目录

- [1. 系统架构](#1-系统架构)
- [2. 跨仓库触发机制](#2-跨仓库触发机制)
- [3. 动态 Token 生成](#3-动态-token-生成)
- [4. 自动触发系统](#4-自动触发系统)
- [5. 技术决策与权衡](#5-技术决策与权衡)

---

## 1. 系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                   主仓库 (gqy20/IssueLab)                 │
│                                                          │
│  GitHub Issues ←→ Workflows ←→ Agent Registry           │
│      ↓                ↓              ↓                   │
│   用户输入        orchestrator    agents/<user>/         │
│   @mentions      dispatch_agents   [user configs]       │
└──────────────┬──────────────────────────────────────────┘
               │
               │ GitHub App Token + Dispatch
               │
       ┌───────┴────────┬───────────────┐
       ↓                ↓                ↓
┌──────────┐      ┌──────────┐    ┌──────────┐
│ Fork #1  │      │ Fork #2  │    │ Fork #N  │
│ (gqy22)  │      │ (alice)  │    │ (bob)    │
│          │      │          │    │          │
│ Workflow │      │ Workflow │    │ Workflow │
│ ↓        │      │ ↓        │    │ ↓        │
│ Agent    │      │ Agent    │    │ Agent    │
│ ↓        │      │ ↓        │    │ ↓        │
│ API Call │      │ API Call │    │ API Call │
└────┬─────┘      └────┬─────┘    └────┬─────┘
     │                 │               │
     └─────────────────┴───────────────┘
               ↓
        回复到主仓库 Issue
```

### 1.2 核心组件

| 组件 | 位置 | 职责 |
|------|------|------|
| **Issue Templates** | `.github/ISSUE_TEMPLATE/` | 结构化输入 |
| **Orchestrator** | `.github/workflows/orchestrator.yml` | 命令处理、流程控制 |
| **Dispatcher** | `.github/workflows/dispatch_agents.yml` | 跨仓库触发 |
| **Registry** | `agents/<user>/agent.yml` | 用户 agent 注册信息 |
| **User Agent Workflow** | Fork: `.github/workflows/user_agent.yml` | 接收触发、执行 agent |
| **Agent Modules** | `src/issuelab/agents/` | Agent 执行引擎模块化架构 |
| **Dispatch CLI** | `src/issuelab/cli/dispatch.py` | 动态 Token 生成 + Dispatch |

### 1.3 数据流

**完整流程：**

```
用户在主仓库 Issue 评论: "@alice 帮我分析"
    ↓
Orchestrator 检测 @mention
    ↓
调用 `src/issuelab/cli/mentions.py` 解析 → ["alice"]
    ↓
读取 agents/alice/agent.yml
    ↓
dispatch.py 动态生成 GitHub App Token
    ↓
发送 workflow_dispatch 到 alice/IssueLab
    ↓
alice 的 fork 仓库接收触发
    ↓
执行 user_agent.yml workflow
    ↓
读取 agents/alice/agent.yml + prompt.md
    ↓
调用 Claude API（使用 alice 的 ANTHROPIC_AUTH_TOKEN）
    ↓
将结果回复到主仓库 Issue（使用 PAT_TOKEN）
```

---

## 2. 跨仓库触发机制

### 2.1 方案对比

我们评估了多种跨仓库协作方案：

| 方案 | 优势 | 劣势 | 结论 |
|------|------|------|------|
| **PR 到主仓库** | 简单直接 | 消耗主仓库资源、权限风险 | ❌ 不采用 |
| **Webhook 推送** | 实时性好 | 需要服务器、复杂维护 | ❌ 不采用 |
| **GitHub App + Dispatch** | 权限隔离、费用独立、可扩展 | 配置稍复杂 | ✅ **采用** |

### 2.2 技术选型理由

**为什么选择 GitHub App？**

1. **细粒度权限**：只需 Actions Read/Write，无需完整 repo 权限
2. **自动刷新**：Token 自动管理，无需手动续期
3. **多租户支持**：每个 fork 独立安装，权限隔离
4. **审计日志**：App 操作独立记录

**为什么选择 workflow_dispatch？**

Fork 仓库不支持 `repository_dispatch`，必须使用 `workflow_dispatch`。

```yaml
# ✅ Fork 仓库正确配置
on:
  workflow_dispatch:
    inputs:
      issue_number:
        required: true
      issue_title:
        required: true
```

### 2.3 注册机制

**智能体配置文件格式**（`agents/<username>/agent.yml`）：

```yaml
owner: alice                      # 必需：你的 GitHub ID
contact: "alice@example.com"
description: "你的智能体描述（用于协作指南）"

# Fork 仓库信息
repository: alice/IssueLab
branch: main

# Dispatch 模式
dispatch_mode: workflow_dispatch  # 或 repository_dispatch
workflow_file: user_agent.yml

# 触发条件
triggers:
  - "@alice"
  - "@alice-bot"

enabled: true
```

**注册流程：**

1. 用户 fork 项目
2. 创建 `agents/<username>/agent.yml`
3. 提交 PR 到主仓库
4. 主仓库维护者审核并合并
5. 用户安装 GitHub App 到自己的 fork
6. 完成，可以接收触发

---

## 3. 动态 Token 生成

### 3.1 问题背景

传统方案：预生成 Token，硬编码用户名

```yaml
# ❌ 问题：只能访问一个用户
- name: Generate Token
  uses: actions/create-github-app-token@v1
  with:
    app-id: ${{ secrets.APP_ID }}
    private-key: ${{ secrets.PRIVATE_KEY }}
    owner: gqy22  # 硬编码！
```

**限制：**
- 需要预先知道所有用户
- 多用户需要多次调用 action
- 无法动态扩展

### 3.2 我们的解决方案

**动态生成：在 Python 脚本中实现完整认证流程**

```python
for repository in target_repositories:
    # 1. 生成 JWT
    jwt_token = generate_github_app_jwt(app_id, private_key)
    
    # 2. 获取 Installation ID
    installation_id = get_installation_id(repository, jwt_token)
    
    # 3. 生成 Installation Token
    access_token = generate_installation_token(installation_id, jwt_token)
    
    # 4. 触发 workflow
    dispatch_workflow(repository, access_token)
```

### 3.3 JWT 生成

```python
import jwt
from datetime import datetime, timedelta, timezone

def generate_github_app_jwt(app_id: str, private_key: str) -> str:
    """生成 GitHub App JWT token（有效期 10 分钟）"""
    now = datetime.now(timezone.utc)
    payload = {
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")
```

**关键点：**
- JWT 证明"我是这个 GitHub App"
- 有效期 10 分钟（GitHub 限制）
- 使用 App 的 Private Key 签名

### 3.4 获取 Installation ID

```python
def get_installation_id(owner: str, repo: str, app_jwt: str) -> int:
    """查询指定仓库的 Installation ID"""
    url = f"https://api.github.com/repos/{owner}/{repo}/installation"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()["id"]
```

**API：** `GET /repos/{owner}/{repo}/installation`

### 3.5 生成 Installation Token

```python
def generate_installation_token(installation_id: int, app_jwt: str) -> str:
    """为指定 Installation 生成 Access Token"""
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    response = requests.post(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()["token"]
```

**API：** `POST /app/installations/{installation_id}/access_tokens`

**Token 特性：**
- 有效期：1 小时（GitHub 自动管理）
- 权限：仅限该 Installation 授权的权限
- 作用域：仅限该 Installation 的仓库

### 3.6 并发处理

为提高效率，我们并行处理多个 dispatch：

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def dispatch_to_multiple_repos(repositories: list[str]) -> dict:
    """并行 dispatch 到多个仓库"""
    results = {}
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_repo = {
            executor.submit(dispatch_to_repo, repo): repo
            for repo in repositories
        }
        
        for future in as_completed(future_to_repo):
            repo = future_to_repo[future]
            try:
                results[repo] = future.result()
            except Exception as e:
                results[repo] = {"error": str(e)}
    
    return results
```

**性能优化：**
- 5 个 repo：从 ~10s 降到 ~2s
- 10 个 repo：从 ~20s 降到 ~3s

---

## 4. 自动触发系统

### 4.1 问题：Bot 评论不触发 Workflow

GitHub Actions 安全机制：

```
github-actions bot 创建的评论 
    ↓
不触发 issue_comment 事件
    ↓
无法触发其他 workflow
```

**影响：**
- Observer 分析后发评论 → 无法触发其他 agent
- Agent 回复后 → 无法触发后续流程

### 4.2 解决方案：混合触发机制

**内置 Agent：通过 Label 触发**

```yaml
on:
  issues:
    types: [labeled]

jobs:
  run-agent:
    if: github.event.label.name == 'bot:trigger-moderator'
    steps:
      - name: Run Moderator
        run: uv run python -m issuelab agent --agent-name moderator
```

Observer 添加 label → 触发 workflow → 执行 agent

**用户 Agent：通过 Dispatch 触发**

```python
# Observer 调用 dispatch.py
dispatch_to_repo(
    repository="alice/IssueLab",
    workflow_file="user_agent.yml",
    inputs={
        "issue_number": issue_number,
        "trigger_source": "observer"
    }
)
```

Observer 调用 dispatch → 跨仓库触发 → 用户 agent 执行

### 4.3 Observer 架构

```python
class ObserverTrigger:
    """Observer 自动触发 agent 的核心逻辑"""
    
    def auto_trigger_agent(self, agent_name: str, issue_number: int):
        """根据 agent 类型选择触发方式"""
        
        # 1. 查找 agent 配置
        agent_config = self.load_agent_config(agent_name)
        
        # 2. 判断是内置还是用户 agent
        if agent_config.get("type") == "builtin":
            # 内置：添加 label
            self.add_label(issue_number, f"bot:trigger-{agent_name}")
        else:
            # 用户：dispatch
            self.dispatch_to_user_repo(
                repository=agent_config["repository"],
                workflow_file=agent_config["workflow_file"],
                inputs={"issue_number": issue_number}
            )
```

### 4.4 TDD 实现过程

我们使用测试驱动开发实现 Observer 自动触发：

**测试先行：**

```python
def test_observer_trigger_builtin_agent():
    """测试触发内置 agent（通过 label）"""
    trigger = ObserverTrigger()
    trigger.auto_trigger_agent("moderator", issue_number=1)
    
    # 验证：添加了 label
    assert "bot:trigger-moderator" in get_issue_labels(1)

def test_observer_trigger_user_agent():
    """测试触发用户 agent（通过 dispatch）"""
    trigger = ObserverTrigger()
    trigger.auto_trigger_agent("alice", issue_number=1)
    
    # 验证：发送了 dispatch
    assert dispatch_was_called(repository="alice/IssueLab")
```

**实现代码：**

```python
def auto_trigger_agent(self, agent_name: str, issue_number: int):
    """自动触发 agent"""
    agent_config = self.registry.get_agent(agent_name)
    
    if not agent_config or not agent_config.get("enabled"):
        return
    
    if agent_config.get("type") == "builtin":
        self.github.add_label(issue_number, f"bot:trigger-{agent_name}")
    else:
        self.dispatch_to_user_repo(agent_config, issue_number)
```

---

## 5. 技术决策与权衡

### 5.1 为什么选择 GitHub Actions？

| 方案 | 优势 | 劣势 |
|------|------|------|
| **自建服务器** | 完全控制 | 维护成本高、需要服务器 |
| **GitHub Actions** | 免费、无需维护、天然集成 | 有执行时间限制 |

**决策：GitHub Actions** ✅

理由：
- 公开仓库无限制免费
- 无需维护服务器
- 与 GitHub Issues 天然集成
- 用户独立配额，费用隔离

### 5.2 为什么使用 Fork 模式？

| 方案 | 配额消耗 | 隐私性 | API Key 管理 |
|------|---------|--------|-------------|
| **PR 到主仓库** | 主仓库 | ❌ 低 | 主仓库统一管理 |
| **Fork + Dispatch** | 用户自己的 | ✅ 高 | 用户自己管理 |

**决策：Fork + Dispatch** ✅

理由：
- 费用独立：每个用户使用自己的 Actions 配额
- 隐私保护：API Key 在自己的仓库，不暴露给主仓库
- 可扩展性：支持任意数量用户，主仓库无负担

### 5.3 API 限流处理

**GitHub API 限制：**
- 认证请求：5000 次/小时
- 未认证：60 次/小时

**MiniMax API 限制：**
- 根据账户等级不同

**策略：**

1. **速率限制配置**

```yaml
rate_limit:
  max_calls_per_hour: 10
  max_calls_per_day: 50
```

2. **指数退避重试**

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RateLimitError)
)
def call_api():
    response = api.call()
    if response.status_code == 429:
        raise RateLimitError()
    return response
```

3. **并发控制**

```python
# 限制并发数
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(task) for task in tasks]
```

### 5.4 成本优化

**GitHub Actions 成本：**

| 仓库类型 | 免费额度 | 超出后 |
|---------|---------|--------|
| 公开仓库 | 无限制 | 免费 |
| 私有仓库 | 2000 分钟/月 | $0.008/分钟 |

**MiniMax API 成本：**

| 模型 | 输入 | 输出 |
|------|------|------|
| MiniMax-M2.1 | ¥15/MTok | ¥15/MTok |

> 💡 提示：也可使用智谱 GLM Coding Plan，访问 https://open.bigmodel.cn/

**优化策略：**

1. **使用公开仓库**（免费无限制）
2. **限制单次调用 token 数**

```python
max_tokens = 4000  # 限制输出长度
```

3. **缓存常用内容**

```python
# 缓存 Issue 内容，避免重复获取
@lru_cache(maxsize=100)
def get_issue_content(issue_number: int):
    return github.get_issue(issue_number)
```

### 5.5 扩展性设计

**新增 Agent 类型：**

只需：
1. 在 fork 创建新 agent 目录
2. 添加注册文件到主仓库
3. 无需修改核心代码

**自定义触发逻辑：**

```python
# 扩展点：自定义触发条件
class CustomTrigger(BaseTrigger):
    def should_trigger(self, context: dict) -> bool:
        # 自定义逻辑
        return context.get("label") == "need-review"
```

**集成外部服务：**

```python
# 扩展点：自定义工具
class PaperSearchTool(Tool):
    def search(self, query: str) -> list[dict]:
        # 调用 arXiv API、Semantic Scholar 等
        return results
```

### 5.6 性能考量

**关键指标：**

| 操作 | 目标时间 | 当前性能 |
|------|---------|---------|
| 解析 @mentions | < 1s | ~0.5s |
| Token 生成 | < 2s/repo | ~1.5s/repo |
| Dispatch 发送 | < 1s/repo | ~0.8s/repo |
| Agent 执行 | < 30s | ~10-20s |

**优化措施：**

1. **并行处理**：多个 dispatch 并行发送
2. **缓存**：缓存 registry 配置
3. **批量操作**：一次请求处理多个 @mentions
4. **异步执行**：Agent 执行不阻塞主流程

---

## 相关文档

- [项目指南](./PROJECT_GUIDE.md) - 用户和贡献者指南
- [部署配置](./DEPLOYMENT.md) - 系统管理员手册

---

**技术栈：**

- Python 3.12+
- uv (包管理)
- Claude Agent SDK >= 0.1.27
- GitHub Actions
- GitHub App API

最后更新：2026-02-03
