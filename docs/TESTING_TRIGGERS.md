# IssueLab 触发逻辑测试文档

本文档说明如何测试 IssueLab 项目的各个触发机制。

## 目录

- [测试环境准备](#测试环境准备)
- [@Mention 触发测试](#mention-触发测试)
- [/Command 触发测试](#command-触发测试)
- [Label 触发测试](#label-触发测试)
- [Observer 自动触发测试](#observer-自动触发测试)
- [Agent 发现机制测试](#agent-发现机制测试)
- [CLI 命令测试](#cli-命令测试)
- [集成测试](#集成测试)

---

## 测试环境准备

### 1. 安装依赖

```bash
uv sync
```

### 2. 设置环境变量

```bash
export GITHUB_APP_ID="your_app_id"
export GITHUB_APP_PRIVATE_KEY="your_app_private_key"
export GITHUB_TOKEN="your_github_token"  # 可选：用于本地 gh CLI
export ANTHROPIC_API_KEY="your_anthropic_api_key"
```

### 3. 运行基础测试

```bash
# 运行所有测试
uv run pytest tests/ -v

# 运行特定模块测试
uv run pytest tests/test_parser.py -v          # @mention 解析测试
uv run pytest tests/test_observer_trigger.py -v  # Observer 触发测试
uv run pytest tests/test_cli.py -v              # CLI 命令测试
```

---

## @Mention 触发测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| 解析器 | `src/issuelab/parser.py` | 解析 @mention 真名 |
| 测试 | `tests/test_parser.py` | @mention 解析测试 |

### 测试用例

#### 1. 测试内置 Agent 真名解析

```python
# 测试文件: tests/test_parser.py

def test_parse_single_mention():
    """测试解析单个 @mention"""
    result = parse_agent_mentions("@moderator 请审核")
    assert result == ["moderator"]

def test_parse_multiple_mentions():
    """测试解析多个 @mention"""
    result = parse_agent_mentions("@moderator 审核，@reviewer_a 评审")
    assert result == ["moderator", "reviewer_a"]

def test_parse_name_mappings():
    """测试真名映射"""
    assert AGENT_NAMES["moderator"] == "moderator"
    assert AGENT_NAMES["reviewer_a"] == "reviewer_a"
    assert AGENT_NAMES["reviewer_b"] == "reviewer_b"
```

#### 2. 运行解析器测试

```bash
uv run pytest tests/test_parser.py -v
```

#### 3. 手动测试命令行

```bash
# 解析 @mention
uv run python -c "
from issuelab.parser import parse_agent_mentions

tests = [
    '@moderator 请审核',
    '@reviewer_a 和 @reviewer_b 评审',
    '@moderator @reviewer_a @summarizer',
    '@MODERATOR 测试大写',
]

for t in tests:
    result = parse_agent_mentions(t)
    print(f'{t!r} -> {result}')
"
```

### 真名触发

系统仅支持内置 Agent 真名触发，例如：
- `@moderator`
- `@reviewer_a`
- `@reviewer_b`
- `@summarizer`
| `reviewer` / `reviewera` / `reva` | `reviewer_a` |
| `reviewerb` / `reviewer_b` / `revb` | `reviewer_b` |
| `summary` | `summarizer` |

---

## /Command 触发测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| GitHub Actions | `.github/workflows/orchestrator.yml` | 命令检测 Job |
| 解析器 | `orchestrator.yml` 中的 bash 脚本 | 命令提取逻辑 |

### 支持的命令

| 命令 | 功能 | 触发条件 |
|------|------|---------|
| `/review` | 运行完整评审流程 | Issue 评论中包含 `/review` 且不包含 `@` |
| `/quiet` | 使机器人安静 | 添加 `bot:quiet` 标签 |
| `/close` | 请求关闭 Issue | 添加 `bot:pending-close` 标签 |
| `/confirm-close` | 确认关闭 Issue | 移除 pending 标签并关闭 |

### 测试命令解析

```bash
# 在 orchestrator.yml 中测试命令检测逻辑
COMMENT="/review 请评审这篇论文"

if echo "$COMMENT" | grep -q '/confirm-close'; then
    echo "command=/confirm-close"
elif echo "$COMMENT" | grep -q '/review'; then
    echo "command=/review"
elif echo "$COMMENT" | grep -q '/quiet'; then
    echo "command=/quiet"
elif echo "$COMMENT" | grep -q '/close'; then
    echo "command=/close"
fi
```

### 手动测试 CLI 命令

```bash
# 测试 review 命令
uv run python -m issuelab review --issue 1 --post

# 测试 execute 命令
uv run python -m issuelab execute --issue 1 --agents "moderator,reviewer_a" --post
```

---

## Label 触发测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| 自动触发 | `src/issuelab/observer_trigger.py` | Label 触发逻辑 |
| 测试 | `tests/test_observer_trigger.py` | Observer 触发测试 |

### 触发标签

| 标签 | 触发条件 | 动作 |
|------|---------|------|
| `state:ready-for-review` | Issues 事件，action=labeled | 运行完整评审流程 |
| `bot:trigger-{agent}` | Issues 事件，action=labeled | 执行指定 agent |

### 测试用例

#### 1. 测试内置 Agent 识别

```python
# tests/test_observer_trigger.py

def test_moderator_is_builtin():
    """Moderator 应该被识别为内置 agent"""
    from issuelab.observer_trigger import is_builtin_agent
    assert is_builtin_agent("moderator") is True

def test_user_agent_is_not_builtin():
    """用户 agent 不应该被识别为内置 agent"""
    from issuelab.observer_trigger import is_builtin_agent
    assert is_builtin_agent("gqy22") is False
```

#### 2. 测试 Label 触发

```python
@patch("subprocess.run")
def test_trigger_builtin_agent_adds_label(mock_run):
    """触发内置 agent 应该添加 label"""
    from issuelab.observer_trigger import trigger_builtin_agent

    mock_run.return_value = Mock(returncode=0)
    trigger_builtin_agent("moderator", 42)

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert "bot:trigger-moderator" in call_args
```

#### 3. 运行 Observer 触发测试

```bash
uv run pytest tests/test_observer_trigger.py -v
```

### 手动测试 Label 触发

```bash
# 模拟添加触发标签
gh issue edit 1 --add-label "bot:trigger-moderator"

# 查看当前标签
gh issue view 1 --json labels

# 测试 ready-for-review 标签
gh issue edit 1 --add-label "state:ready-for-review"
```

---

## Observer 自动触发测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| Observer 执行 | `src/issuelab/agents/observer.py` | Observer Agent 执行 |
| 自动触发 | `src/issuelab/observer_trigger.py` | 自动触发逻辑 |

### 测试用例

#### 1. 测试 Observer 执行

```bash
# 单个 Issue 分析
uv run python -m issuelab observe --issue 1 --post

# 批量分析
uv run python -m issuelab observe-batch --issues "1,2,3" --auto-trigger
```

#### 2. 测试自动触发集成

```python
# tests/test_observer_trigger.py

@patch("issuelab.observer_trigger.trigger_builtin_agent")
@patch("issuelab.observer_trigger.is_builtin_agent")
def test_auto_trigger_builtin_agent(mock_is_builtin, mock_trigger_builtin):
    """Observer 判断需要触发内置 agent 时应该添加 label"""
    from issuelab.observer_trigger import auto_trigger_agent

    mock_is_builtin.return_value = True
    mock_trigger_builtin.return_value = True

    result = auto_trigger_agent(
        agent_name="moderator", issue_number=1, issue_title="Test", issue_body="Body"
    )

    mock_trigger_builtin.assert_called_once_with("moderator", 1)
    assert result is True
```

#### 3. 测试批量处理

```python
@patch("issuelab.observer_trigger.auto_trigger_agent")
def test_observe_batch_triggers_on_should_trigger_true(mock_auto_trigger):
    """observe-batch 结果为 should_trigger=True 时应该自动触发"""
    from issuelab.observer_trigger import process_observer_results

    mock_auto_trigger.return_value = True

    results = [
        {
            "issue_number": 1,
            "should_trigger": True,
            "agent": "moderator",
            "reason": "New paper needs review",
        }
    ]

    issue_data = {1: {"title": "Test", "body": "Body"}}
    triggered = process_observer_results(results, issue_data, auto_trigger=True)

    assert triggered == 1
    mock_auto_trigger.assert_called_once()
```

---

## Agent 发现机制测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| Agent 发现 | `src/issuelab/agents/discovery.py` | discover_agents() |
| 测试 | `tests/test_agents.py` | Agent 相关测试 |

### 测试用例

#### 1. 测试 Agent 发现

```python
def test_discover_agents():
    """测试动态发现 Agent"""
    from issuelab.agents.discovery import discover_agents

    agents = discover_agents()

    # 验证内置 agent 存在
    assert "moderator" in agents
    assert "reviewer_a" in agents
    assert "reviewer_b" in agents
    assert "summarizer" in agents

    # 验证元数据完整
    for name, config in agents.items():
        assert "prompt" in config
        assert "description" in config
```

#### 2. 测试 Agent 矩阵生成

```python
def test_get_agent_matrix_markdown():
    """测试生成 Agent 矩阵"""
    from issuelab.agents.discovery import get_agent_matrix_markdown

    matrix = get_agent_matrix_markdown()

    # 验证格式
    assert "|" in matrix  # Markdown 表格
    assert "moderator" in matrix
    assert "reviewer_a" in matrix
```

#### 3. 运行 Agent 测试

```bash
uv run pytest tests/test_agents.py -v
```

### 手动测试 Agent 发现

```bash
# 列出所有可用 Agent
uv run python -m issuelab list-agents
```

---

## CLI 命令测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| 主入口 | `src/issuelab/__main__.py` | CLI 子命令 |
| 测试 | `tests/test_cli.py` | CLI 测试 |

### CLI 命令列表

| 命令 | 功能 | 示例 |
|------|------|------|
| `execute` | 并行执行 agents | `execute --issue 1 --agents "mod,reviewer"` |
| `review` | 顺序评审流程 | `review --issue 1 --post` |
| `observe` | Observer 分析 | `observe --issue 1` |
| `observe-batch` | 批量分析 | `observe-batch --issues "1,2,3"` |
| `list-agents` | 列出 agents | `list-agents` |

### 测试用例

#### 1. 测试 agents 参数解析

```python
# tests/test_main.py

def test_parse_agents_comma():
    """测试逗号分隔格式"""
    from issuelab.__main__ import parse_agents_arg

    assert parse_agents_arg("echo,test") == ["echo", "test"]

def test_parse_agents_space():
    """测试空格分隔格式"""
    from issuelab.__main__ import parse_agents_arg

    assert parse_agents_arg("echo test") == ["echo", "test"]

def test_parse_agents_json():
    """测试 JSON 数组格式"""
    from issuelab.__main__ import parse_agents_arg

    assert parse_agents_arg('["echo", "test"]') == ["echo", "test"]
```

#### 2. 运行 CLI 测试

```bash
uv run pytest tests/test_cli.py -v
```

---

## 集成测试

### 测试范围

| 模块 | 文件 | 说明 |
|------|------|------|
| 完整流程 | `tests/test_integration.py` | 集成测试 |
| 响应处理 | `tests/test_response_processor.py` | 响应后处理 |

### 测试场景

#### 1. 完整评审流程

```bash
# 触发完整评审
gh issue comment 1 --body "@moderator 请审核"

# 或使用 /review 命令
gh issue comment 1 --body "/review"
```

#### 2. 手动执行集成测试

```bash
# 测试 review 流程
uv run python -m issuelab review --issue 1 --post

# 预期结果：
# 1. 执行 moderator
# 2. 执行 reviewer_a
# 3. 执行 reviewer_b
# 4. 执行 summarizer
# 5. 每个 agent 的结果发布到 Issue
```

#### 3. 测试响应处理

```python
# tests/test_response_processor.py

def test_process_agent_response_mentions():
    """测试处理响应中的 @mentions"""
    from issuelab.response_processor import process_agent_response

    result = process_agent_response(
        agent_name="moderator",
        response="建议 @reviewer_a 进行详细评审",
        issue_number=1,
        issue_title="Test",
        issue_body="Body",
        auto_dispatch=True,
    )

    assert "reviewer_a" in result["mentions"]
```

---

## GitHub Actions 测试

### 工作流文件

| 工作流 | 触发条件 | 测试方法 |
|--------|---------|---------|
| `orchestrator.yml` | Issue 评论/标签事件 | 手动触发 Issue 事件 |
| `dispatch_agents.yml` | 用户 @mention | 手动 @mention 用户 |

### 测试步骤

#### 1. 测试 @Mention 触发

```bash
# 在 Issue 下评论触发
gh issue comment 1 --body "@moderator 请审核"

# 查看 Actions 运行
gh run list --workflow=orchestrator.yml
```

#### 2. 测试 /Command 触发

```bash
# 触发 /review 命令
gh issue comment 1 --body "/review"

# 查看 Actions 运行
gh run list --workflow=orchestrator.yml
```

#### 3. 测试 Label 触发

```bash
# 添加触发标签
gh issue edit 1 --add-label "state:ready-for-review"

# 查看 Actions 运行
gh run list --workflow=orchestrator.yml
```

---

## 常见问题

### 1. 测试失败：找不到模块

```bash
# 确保在项目根目录运行
cd /path/to/IssueLab
uv run pytest tests/test_parser.py -v
```

### 2. GitHub Actions 测试失败

```bash
# 检查 token 权限
gh auth status

# 查看 Actions 日志
gh run view <run_id> --log
```

### 3. Agent 执行超时

```bash
# 使用 quick 场景
uv run python -m issuelab execute --issue 1 --agents "echo" --scene quick
```

---

## 快速测试清单

### 基础测试

```bash
# 1. 运行所有单元测试
uv run pytest tests/ -v --tb=short

# 2. 检查代码风格
uv run ruff check src/ tests/

# 3. 类型检查
uv run mypy src/issuelab --ignore-missing-imports
```

### 触发逻辑专项测试

```bash
# @mention 解析
uv run pytest tests/test_parser.py -v

# Observer 触发
uv run pytest tests/test_observer_trigger.py -v

# CLI 命令
uv run pytest tests/test_cli.py -v

# Agent 发现
uv run pytest tests/test_agents.py -v
```

---

## 参考资源

- [CLAUDE.md](../CLAUDE.md) - 项目架构说明
- [orchestrator.yml](../.github/workflows/orchestrator.yml) - GitHub Actions 工作流
- [Agent Modules](src/issuelab/agents/) - Agent 执行引擎模块化架构
- [Parser](src/issuelab/parser.py) - @mention 解析器
