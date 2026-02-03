# GitHub Issues + Claude Agent SDK MVP 落地方案

## 文档概述

本文档提供一套完整的 MVP（最小可行产品）落地方案，使用 GitHub Issues 作为交互界面，GitHub Actions 作为执行引擎，基于 **Claude Agent SDK (Python)** 实现自动化评审流程。该方案设计为 1-2 天内可跑通完整闭环，包含 Issue 发起、双评审触发、自动汇总、状态标签管理等核心功能。

**核心差异说明**：
1. 基于 GitHub Actions 而非自建 FastAPI 服务，充分利用 GitHub 原生能力
2. 使用 **Claude Agent SDK** 而非直接调用 Anthropic API，获得完整的 Agent Loop 和工具调用能力
3. 使用 **uv** 管理 Python 环境和依赖，替代传统的 pip + virtualenv
4. 支持 **子代理 (Subagent)** 模式，实现评审流程的模块化和并行化

---

## 一、目标与功能闭环

### 1.1 核心目标

本方案旨在构建一个轻量级但功能完整的 AI 辅助科研评审系统。系统以 GitHub Issues 为唯一交互入口，评审人员或研究者通过在 Issue 或评论中输入特定命令来触发自动化评审流程。系统将自动分配评审角色、收集评审意见、生成共识摘要，并维护整个评审流程的状态标签。这一设计遵循"最小可用"原则，优先保证核心链路稳定可用，再逐步扩展功能边界。

### 1.2 触发命令体系

系统支持两种触发方式：**@mention 触发** 和 **命令触发**。

**@mention 触发**（推荐，并行执行）：
- `@Moderator` 触发分诊流程
- `@ReviewerA` 触发正方评审
- `@ReviewerB` 触发反方评审
- `@Summarizer` 触发总结流程
- 多个 @mention 可**并行触发**，各自独立响应

**命令触发**（顺序执行）：
- `/review` 命令依次触发 Moderator → ReviewerA → ReviewerB
- `/summarize` 命令触发 Summarizer 汇总
- `/quiet` 命令让机器人进入静默模式
- `/triage` 命令仅触发 Moderator 分诊

两种方式可混合使用，@mention 适合自由讨论，命令适合固定流程。

### 1.3 代理角色定义

MVP 阶段共启用五个代理角色，各司其职。Moderator 担任分诊与控场角色，负责检查 Issue 信息完整性、澄清问题需求，并在评审过程中维持讨论秩序。ReviewerA 作为正方评审，从可行性、贡献度和潜在价值角度进行评审，提出改进建议。ReviewerB 作为反方评审，专注于寻找漏洞、反例、潜在不可复现点和隐藏假设。Summarizer 负责汇总共识与分歧，输出清晰的行动项清单。PaperScout 为预留扩展角色，计划后续用于相关论文检索与知识补充。

**标签触发的评审流程**：
1. 用户提交 Issue（自动获得 `state:triage` 标签）
2. 管理员或用户输入 `/triage` → 触发 Moderator 分诊
3. Moderator 建议是否准备就绪
4. 管理员打上 `state:ready-for-review` 标签 → **自动触发**完整评审流程
5. 系统依次执行 Moderator → ReviewerA → ReviewerB
6. 自动添加 `bot:needs-summary` 标签，等待总结

---

## 二、目录结构规范

### 2.1 整体架构

采用 **src layout** 结构，符合 Python 项目最佳实践：

```
issuelab/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── paper.yml
│   │   ├── proposal.yml
│   │   ├── result.yml
│   │   └── question.yml
│   └── workflows/
│       └── orchestrator.yml    # 主工作流
├── src/
│   ├── issuelab/               # 主包
│   │   ├── __init__.py
│   │   ├── __main__.py         # 入口：python -m issuelab
│   │   ├── coordinator.py      # 主协调器
│   │   ├── executor.py         # 并行执行器
│   │   ├── parser.py           # @mention 解析器
│   │   ├── agents/             # 代理模块
│   │   │   ├── __init__.py
│   │   │   ├── moderator.py
│   │   │   ├── reviewer_a.py
│   │   │   ├── reviewer_b.py
│   │   │   └── summarizer.py
│   │   └── tools/              # 工具模块
│   │       ├── __init__.py
│   │       └── github.py
├── prompts/                    # 提示词模板（独立目录）
│   ├── moderator.md
│   ├── reviewer_a.md
│   ├── reviewer_b.md
│   └── summarizer.md
├── docs/                       # 文档
│   └── MVP.md
├── tests/                      # 测试
│   └── __init__.py
├── pyproject.toml              # uv 项目配置
├── uv.lock
└── README.md
```

### 2.2 目录职责说明

`.github/ISSUE_TEMPLATE/` 存放 Issue 模板文件。`.github/workflows/` 存放 GitHub Actions 工作流文件。`src/issuelab/` 是主代码包，采用 **Subagent 模式**：`coordinator.py` 作为主代理负责任务分解，`executor.py` 处理 @mention 并行执行，`parser.py` 解析评论中的触发信号。`src/issuelab/agents/` 存放各评审代理实现。`src/issuelab/tools/` 存放自定义工具。`prompts/` 存放各代理的系统提示词模板。`pyproject.toml` 使用 uv 标准配置。

### 2.3 uv 环境管理

本项目使用 [uv](https://docs.astral.sh/uv/) 管理 Python 环境和依赖，它是 Rust 编写的超快速包管理器，比 pip 快 10-100 倍。

**安装 uv**：
```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或通过 pip
pip install uv
```

**项目初始化**：
```bash
# 创建项目并自动生成 pyproject.toml
uv init --name issuelab --python 3.11

# 安装依赖
uv sync

# 运行代理
uv run python -m agents
```

**pyproject.toml 配置**：
```toml
[project]
name = "issuelab"
version = "0.1.0"
description = "AI 辅助科研评审系统"
requires-python = ">=3.11"
dependencies = [
    "anthropic-claude-agent-sdk>=0.1.0",
    "gh-cli>=2.0.0",
]

[tool.uv]
package = true
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

---

## 三、标签体系设计

### 3.1 标签分类原则

MVP 阶段标签设计遵循"少而精"原则，仅建立三类必要标签。type 标签标识 Issue 主题类型，state 标签追踪流程状态，bot 标签用于机器人控制。这种分类方式既能满足基本流程管理需求，又不会因标签过多而导致管理混乱。每个标签命名采用 `category:name` 格式，语义清晰，便于脚本处理。

### 3.2 标签详细定义

**type 类别标签**包含四个成员。`type:paper` 用于论文讨论类 Issue，通常包含论文链接、主要贡献和待验证问题。`type:proposal` 用于实验提案类 Issue，描述假设、指标和实验设置。`type:result` 用于结果复盘类 Issue，记录实验结果和结论。`type:question` 用于科研问题类 Issue，提出具体技术问题寻求解答。

**state 类别标签**控制 Issue 在评审流程中的状态。`state:triage` 表示待分诊，是新 Issue 的默认状态，由 Moderator 审核后决定是否进入评审。`state:ready-for-review` 表示准备就绪，打上此标签后自动触发双评审流程。`state:review` 表示正在评审中，双评审代理正在工作。`state:done` 表示评审完成，已产出最终结论。`state:blocked` 表示流程受阻，可能因缺少信息或需要外部资源。`state:archived` 表示已归档，不再接受新评论。

**bot 类别标签**用于机器人行为控制。`bot:needs-summary` 表示该 Issue 需要进行总结操作。`bot:quiet` 表示静默模式，机器人停止对该 Issue 的所有响应。

---

## 四、Issue 模板配置

### 4.1 模板设计理念

Issue 模板是保证数据结构化的关键机制。每个模板都经过精心设计，包含最少的必填字段和必要的可选字段。必填字段确保核心信息不缺失，可选字段降低提交门槛。模板使用 YAML 格式，便于 GitHub 解析和验证。所有模板默认应用 `state:triage` 标签，等待 Moderator 分诊后调整。

### 4.2 论文讨论模板（paper.yml）

```yaml
name: Paper
description: 论文讨论卡片
title: "[Paper] "
labels: ["type:paper", "state:triage"]
body:
  - type: input
    id: link
    attributes:
      label: Paper link / DOI
      description: 论文的 URL 或 DOI 标识符
      placeholder: https://arxiv.org/abs/xxxx 或 10.1145/xxxx
    validations:
      required: true
  - type: textarea
    id: contributions
    attributes:
      label: Key contributions (<=3)
      description: 列举最多三条论文的核心贡献
      placeholder: 1. 首次提出...&#10;2. 设计了...&#10;3. 实现了...
    validations:
      required: true
  - type: textarea
    id: doubts
    attributes:
      label: What to verify / doubt
      description: 你最想让评审关注或复现验证的点
    validations:
      required: false
  - type: textarea
    id: ask
    attributes:
      label: What do you want agents to do?
      description: 明确希望代理执行的任务，如"/review"或具体要求
    validations:
      required: false
```

### 4.3 实验提案模板（proposal.yml）

```yaml
name: Proposal
description: 实验提案
title: "[Proposal] "
labels: ["type:proposal", "state:triage"]
body:
  - type: textarea
    id: hypothesis
    attributes:
      label: Hypothesis
      description: 你想要验证的假设
      placeholder: 我们假设...
    validations:
      required: true
  - type: textarea
    id: metrics
    attributes:
      label: Metrics & success criteria
      description: 评估指标和成功标准
      placeholder: 主要指标：...&#10;成功标准：...
    validations:
      required: true
  - type: textarea
    id: setup
    attributes:
      label: Data / setup
      description: 数据集、实验环境或工具链配置
    validations:
      required: true
  - type: textarea
    id: budget
    attributes:
      label: Budget / constraints
      description: 计算资源、时间或数据量的限制
    validations:
      required: false
```

### 4.4 结果复盘模板（result.yml）

```yaml
name: Result
description: 结果复盘
title: "[Result] "
labels: ["type:result", "state:triage"]
body:
  - type: textarea
    id: setup
    attributes:
      label: Setup (version/params/data)
      description: 实验环境版本、关键参数和使用的数据集
    validations:
      required: true
  - type: textarea
    id: results
    attributes:
      label: Results (tables/links)
      description: 实验结果，可包含表格、图表链接或关键数据
    validations:
      required: true
  - type: textarea
    id: conclusion
    attributes:
      label: Conclusion & limitations
      description: 结论总结和局限性分析
    validations:
      required: true
```

### 4.5 科研问题模板（question.yml）

```yaml
name: Question
description: 科研问题
title: "[Q] "
labels: ["type:question", "state:triage"]
body:
  - type: textarea
    id: context
    attributes:
      label: Context
      description: 问题背景和相关上下文
    validations:
      required: true
  - type: textarea
    id: tried
    attributes:
      label: What you tried
      description: 已尝试的解决方法或思路
    validations:
      required: false
  - type: textarea
    id: expected
    attributes:
      label: Expected output
      description: 期望的输出或解决方案
    validations:
      required: false
```

---

## 五、交互协议规范

### 5.1 命令触发规则

所有命令必须以斜杠开头，后跟命令名称，支持在 Issue 正文中或评论中输入。命令输入后，系统会解析并执行相应流程。需要注意的是，命令匹配采用子串包含方式，因此 `/review` 会在任意位置被检测到。系统建议用户在独立行输入命令以提高可读性，但不做强制要求。

### 5.2 代理回复格式标准

为保证评审意见的一致性和可解析性，所有代理的回复必须遵循统一格式。该格式包含四个必填部分：Claim（主张）部分陈述代理的核心观点和判断；Evidence（证据）部分列出支持或反驳主张的具体证据，必须引用链接、DOI、代码位置或日志，无法提供证据时应明确标注"缺证据"；Uncertainty（不确定性）部分说明代理对自身判断的确定程度，识别潜在盲点；Next actions（后续行动）部分以 Markdown checklist 形式列出建议的下一步操作。

以下为标准回复格式示例：

```markdown
## Claim
该论文提出的方法在长文本摘要任务上取得了显著提升，但复现性存疑。

## Evidence
- 论文报告在 CNN 数据集上 ROUGE-1 提升 /DailyMail2.3 点（https://arxiv.org/abs/xxxx）
- 代码仓库 https://github.com/xxx 已开源，但缺少预训练模型下载链接
- 实验仅报告了 3 次随机种子结果，标准差未公开

## Uncertainty
- 论文未说明计算资源需求，难以评估实际部署成本
- 消融实验缺少对关键超参数的敏感性分析

## Next actions
- [ ] 联系作者获取预训练模型
- [ ] 使用公开代码复现主要实验
- [ ] 增加随机种子数量验证结果稳定性
```

### 5.3 熄火与终止规则

系统提供两种终止自动响应的方式。用户在任意评论中输入 `/quiet` 命令，系统将立即停止对该 Issue 的所有自动响应，并自动添加 `bot:quiet` 标签。管理员也可以手动添加 `bot:quiet` 或 `state:archived` 标签实现相同效果。处于静默状态的 Issue 即使收到新评论也不会触发代理响应，除非标签被手动移除。

### 5.4 Claude Agent SDK 架构设计

本系统采用 **Claude Agent SDK** 构建智能体体系，充分利用其提供的完整 Agent Loop、工具调用能力和子代理模式。

#### 5.4.1 子代理 (Subagent) 模式

Claude Agent SDK 支持创建子代理，实现以下优势：

- **并行化**：可同时启动多个子代理执行不同任务
- **上下文隔离**：每个子代理拥有独立的上下文，避免信息干扰
- **专业化**：可对不同子代理应用不同的系统提示词

```python
from claude_agent_sdk import Subagent

# 主协调器代理
coordinator = Agent(
    name="Coordinator",
    system_prompt="你是评审流程协调器，负责分解任务并调度子代理"
)

# 创建子代理
moderator = Subagent(
    name="Moderator",
    system_prompt=Path("prompts/moderator.md").read_text()
)

reviewer_a = Subagent(
    name="ReviewerA",
    system_prompt=Path("prompts/reviewer_a.md").read_text()
)

reviewer_b = Subagent(
    name="ReviewerB",
    system_prompt=Path("prompts/reviewer_b.md").read_text()
)
```

#### 5.4.2 自定义工具系统

通过 `@tool` 装饰器定义自定义工具，供代理调用：

```python
from claude_agent_sdk import tool

@tool
def get_issue_info(issue_number: int) -> dict:
    """获取 Issue 的完整信息"""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "title,body,labels"],
        capture_output=True, text=True
    )
    return json.loads(result.stdout)

@tool
def post_comment(issue_number: int, body: str) -> str:
    """在 Issue 下发布评论"""
    subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body],
        capture_output=True
    )
    return f"Comment posted to issue #{issue_number}"

@tool
def update_label(issue_number: int, label: str, action: str = "add") -> str:
    """更新 Issue 标签"""
    action_flag = "--add-label" if action == "add" else "--remove-label"
    subprocess.run(
        ["gh", "issue", "edit", str(issue_number), action_flag, label],
        capture_output=True
    )
    return f"Label {label} {action}ed on issue #{issue_number}"
```

#### 5.4.3 @mention 数量限制

为防止 @mention 滥用，系统在多个层面进行限制：

**工作流层限制**：
```yaml
# 同一 Issue 并发运行限制
concurrency:
  group: ${{ github.event.issue.number }}
  cancel-in-progress: true
```

**解析层限制**（agents/parser.py）：
```python
MAX_MENTIONS = 3  # 最多触发 3 个代理

def parse_mentions(comment_body: str) -> list[str]:
    mentions = super().parse_mentions(comment_body)
    return mentions[:MAX_MENTIONS]  # 截断超出的部分
```

**提示词指导**：
```
使用 @mention 时请注意：
- 每次评论建议不超过 3 个 @mention
- 优先使用最相关的代理
- 避免重复 @mention 同一代理
```

**建议的用户体验**：
- 单条评论聚焦一个问题
- 使用 `/review` 触发完整流程
- 使用 @mention 进行针对性讨论

系统支持两种执行模式：

**模式 A：@mention 并行模式**

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Issue 评论                        │
│ "请 @Moderator 分诊，@ReviewerA 评审，@ReviewerB 找问题"    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │    @mention 解析器    │
              │   parse_mentions()    │
              └───────────┬───────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Moderator  │  │ ReviewerA   │  │ ReviewerB   │
│  Subagent   │  │ Subagent    │  │ Subagent    │
│  (并行)     │  │ (并行)      │  │ (并行)      │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       │    ┌───────────┼───────────┐    │
       │    │           │           │    │
       ▼    ▼           ▼           ▼    ▼
   ┌─────────────────────────────────────────┐
   │           GitHub Issue 评论              │
   │   [Agent: Moderator] 分诊结果...        │
   │   [Agent: ReviewerA] 评审意见...        │
   │   [Agent: ReviewerB] 反对意见...        │
   └─────────────────────────────────────────┘
```

**模式 B：/command 顺序模式**

```
┌─────────────────────────────────────────────────────────────┐
│                     GitHub Issue 评论                        │
│ "/review"                                                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │    命令路由器          │
              │   route_command()     │
              └───────────┬───────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │      run_sequential_flow()      │
        │   Mod → RevA → RevB → Summary   │
        └─────────────────┬───────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   GitHub Issue 评论    │
              └───────────────────────┘
```

---

## 六、系统架构设计

### 6.1 整体架构概览

系统基于 GitHub Actions 构建，充分利用 GitHub 原生能力实现轻量级架构。整体架构分为四个层次：

**触发层**支持两种触发方式：
- `issue_comment` 事件：监听评论中的 `@mention` 和 `/命令`
- `issues` 事件：监听标签变更，支持 `state:ready-for-review` 标签自动触发评审

**解析层**解析评论内容，提取触发信号：
- `@mention` 解析：如 `@ReviewerA` → 触发 ReviewerA
- `/command` 解析：如 `/review` → 触发完整评审流程

**执行层**支持两种执行模式：
- **并行模式**（@mention）：多个代理同时执行，各自独立响应
- **顺序模式**（/command）：按预设流程依次执行（Mod → RevA → RevB）

**状态层**通过 Issue 标签管理流程状态，实现状态流转自动化。

这种设计无需自建服务器，所有计算在 GitHub Actions 运行器中完成。

### 6.2 技术选型说明

- **环境管理**：使用 uv 管理 Python 环境和依赖，比 pip 快 10-100 倍
- **执行引擎**：GitHub Actions + Claude Agent SDK
- **GitHub 操作**：使用 `gh` CLI 和自定义工具封装
- **状态管理**：直接使用 GitHub Labels，无需额外数据库
- **并发控制**：使用 GitHub Actions `concurrency` 机制

### 6.3 幂等与并发机制

并发控制通过 `concurrency` 关键字实现，确保同一 Issue 不会并发执行多个工作流运行：

```yaml
concurrency:
  group: ${{ github.event.issue.number }}
  cancel-in-progress: true
```

这种机制天然实现了事件去重和幂等控制，无需额外的数据库存储。工作流级别的 `if` 条件用于过滤命令类型，确保只有包含 `/review`、`/summarize`、`/quiet` 的评论才会执行实际逻辑。

---

## 七、核心代码实现

### 7.1 GitHub Actions 工作流（.github/workflows/orchestrator.yml）

```yaml
name: Issue Orchestrator

# 支持三种触发方式：@mention、/command、标签变更
on:
  issue_comment:
    types: [created, edited]
  issues:
    types: [labeled]

# 并发控制：同一 Issue 不会并发运行
concurrency:
  group: ${{ github.event.issue.number }}
  cancel-in-progress: true

jobs:
  # ========== 标签触发：state:ready-for-review ==========
  auto-trigger-review:
    if: github.event_name == 'issues' &&
        github.event.action == 'labeled' &&
        github.event.label.name == 'state:ready-for-review'
    runs-on: ubuntu-latest
    permissions:
      issues: write
      contents: read

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync

      - name: Run full review process
        run: |
          echo "=== 标签触发评审开始 ==="
          gh issue edit ${{ github.event.issue.number }} \
            --add-label "state:review" \
            --remove-label "state:ready-for-review" \
            --repo ${{ github.repository }}

          echo "Running Coordinator with Subagents..."
          uv run python -m agents review --issue ${{ github.event.issue.number }}

          echo "=== 评审完成 ==="
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_TOKEN: ${{ secrets.ANTHROPIC_API_TOKEN }}

  # ========== @mention 触发（并行执行） ==========
  process-mention:
    if: github.event_name == 'issue_comment' &&
        contains(github.event.comment.body, '@')
    runs-on: ubuntu-latest
    permissions:
      issues: write
      contents: read

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync

      - name: Parse @mentions
        id: parse
        run: |
          COMMENT="${{ github.event.comment.body }}"
          # 提取 @mention 并转为小写
          MENTIONS=$(echo "$COMMENT" | grep -o '@[a-zA-Z_]*' | sed 's/@//' | tr '[:upper:]' '[:lower:]' | tr '\n' ' ')
          echo "mentions=$MENTIONS" >> $GITHUB_OUTPUT
          echo "解析到 mentions: $MENTIONS"

      - name: Run parallel agents
        if: steps.parse.outputs.mentions != ''
        run: |
          echo "=== 并行执行代理 ==="
          uv run python -m agents execute \
            --issue ${{ github.event.issue.number }} \
            --agents "${{ steps.parse.outputs.mentions }}"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_TOKEN: ${{ secrets.ANTHROPIC_API_TOKEN }}

  # ========== /command 触发（顺序执行） ==========
  process-command:
    if: github.event_name == 'issue_comment' &&
        (contains(github.event.comment.body, '/review') ||
         contains(github.event.comment.body, '/summarize') ||
         contains(github.event.comment.body, '/quiet') ||
         contains(github.event.comment.body, '/triage')) &&
        !contains(github.event.comment.body, '@')  # 排除 @mention
    runs-on: ubuntu-latest
    permissions:
      issues: write
      contents: read

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v4

      - name: Set up Python
        run: uv python install 3.11

      - name: Install dependencies
        run: uv sync

      - name: Extract command
        id: extract
        run: |
          COMMENT="${{ github.event.comment.body }}"
          if echo "$COMMENT" | grep -q '/review'; then
            echo "command=/review" >> $GITHUB_OUTPUT
          elif echo "$COMMENT" | grep -q '/summarize'; then
            echo "command=/summarize" >> $GITHUB_OUTPUT
          elif echo "$COMMENT" | grep -q '/quiet'; then
            echo "command=/quiet" >> $GITHUB_OUTPUT
          elif echo "$COMMENT" | grep -q '/triage'; then
            echo "command=/triage" >> $GITHUB_OUTPUT
          fi

      # 处理 /quiet 命令
      - name: Handle quiet command
        if: steps.extract.outputs.command == '/quiet'
        run: |
          gh issue edit ${{ github.event.issue.number }} \
            --add-label "bot:quiet" \
            --repo ${{ github.repository }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      # 处理 /triage 命令：仅运行 Moderator 分诊
      - name: Handle triage command
        if: steps.extract.outputs.command == '/triage'
        run: |
          uv run python -m agents triage --issue ${{ github.event.issue.number }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_TOKEN: ${{ secrets.ANTHROPIC_API_TOKEN }}

      # 处理 /review 命令：运行 Moderator → ReviewerA → ReviewerB
      - name: Run review process
        if: steps.extract.outputs.command == '/review'
        run: |
          echo "=== /review 命令触发评审 ==="
          gh issue edit ${{ github.event.issue.number }} \
            --add-label "state:review" \
            --repo ${{ github.repository }}

          uv run python -m agents review --issue ${{ github.event.issue.number }}

          echo "标记需要总结..."
          gh issue edit ${{ github.event.issue.number }} \
            --add-label "bot:needs-summary" \
            --repo ${{ github.repository }}

          echo "=== 评审完成 ==="
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_TOKEN: ${{ secrets.ANTHROPIC_API_TOKEN }}

      # 处理 /summarize 命令
      - name: Run summarizer
        if: steps.extract.outputs.command == '/summarize'
        run: |
          python -m agents.summarizer
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          ANTHROPIC_API_TOKEN: ${{ secrets.ANTHROPIC_API_TOKEN }}
```

### 7.2 自定义工具集（agents/tools/__init__.py）

```python
"""GitHub 操作工具集，供 Claude Agent 调用"""
import subprocess
import json
import os


def get_issue_info(issue_number: int) -> dict:
    """获取 Issue 的完整信息"""
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "title,body,labels,comments"],
        capture_output=True, text=True,
        env={**os.environ, "GH_TOKEN": os.environ.get("GITHUB_TOKEN", "")}
    )
    if result.returncode != 0:
        return {"error": result.stderr}
    return json.loads(result.stdout)


def post_comment(issue_number: int, body: str) -> str:
    """在 Issue 下发布评论"""
    result = subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body],
        capture_output=True, text=True,
        env={**os.environ, "GH_TOKEN": os.environ.get("GITHUB_TOKEN", "")}
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return f"Comment posted to issue #{issue_number}"


def update_label(issue_number: int, label: str, action: str = "add") -> str:
    """更新 Issue 标签"""
    action_flag = "--add-label" if action == "add" else "--remove-label"
    result = subprocess.run(
        ["gh", "issue", "edit", str(issue_number), action_flag, label],
        capture_output=True, text=True,
        env={**os.environ, "GH_TOKEN": os.environ.get("GITHUB_TOKEN", "")}
    )
    if result.returncode != 0:
        return f"Error: {result.stderr}"
    return f"Label '{label}' {action}ed on issue #{issue_number}"
```

### 7.3 协调器主代理（agents/coordinator.py）

```python
"""主协调器：使用 Claude Agent SDK 的 Subagent 模式调度评审流程"""
from pathlib import Path
import os
from claude_agent_sdk import Agent, Subagent


def create_coordinator() -> Agent:
    """创建协调器主代理"""
    # prompts 目录在项目根目录 (src/issuelab/ -> src/ -> project_root/prompts)
    PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

    # 定义子代理
    moderator = Subagent(
        name="Moderator",
        system_prompt=(PROMPTS_DIR / "moderator.md").read_text()
    )

    reviewer_a = Subagent(
        name="ReviewerA",
        system_prompt=(PROMPTS_DIR / "reviewer_a.md").read_text()
    )

    reviewer_b = Subagent(
        name="ReviewerB",
        system_prompt=(PROMPTS_DIR / "reviewer_b.md").read_text()
    )

    # 主协调器
    coordinator = Agent(
        name="Coordinator",
        system_prompt="""你是科研评审系统的协调器。

你的职责：
1. 接收评审任务，解析 Issue 信息
2. 依次调度 Moderator、ReviewerA、ReviewerB 进行评审
3. 汇总评审结果并发布到 GitHub Issue
4. 更新状态标签

请按顺序执行评审流程，并在每个步骤后发布评论。
""",
        tools=[get_issue_info, post_comment, update_label]
    )

    return coordinator


async def run_review_process(issue_number: int):
    """运行完整评审流程"""
    coordinator = create_coordinator()

    # 获取 Issue 信息
    issue_info = get_issue_info(issue_number)

    # 执行评审流程
    result = await coordinator.run(
        f"""请对 Issue #{issue_number} 进行评审。

Issue 标题: {issue_info.get('title', '')}
Issue 正文: {issue_info.get('body', '')}
当前标签: {[l['name'] for l in issue_info.get('labels', [])]}

请依次执行：
1. 调用 Moderator 进行分诊检查
2. 调用 ReviewerA 进行正方评审
3. 调用 ReviewerB 进行反方评审
4. 发布评审结果总结
5. 添加 'bot:needs-summary' 标签
"""
    )

    return result
```

### 7.4 子代理实现示例（agents/moderator.py）

```python
"""Moderator 子代理 - 分诊与控场"""
from pathlib import Path
import os
from claude_agent_sdk import Subagent, tool


@tool
def check_issue_completeness(issue_body: str) -> dict:
    """检查 Issue 信息是否完整"""
    required_fields = []
    optional_fields = []

    if len(issue_body.strip()) < 50:
        required_fields.append("Issue 内容过于简短，请补充详细信息")

    # 检查是否包含链接、代码等关键信息
    if "http" not in issue_body.lower():
        required_fields.append("缺少链接或参考链接")

    return {
        "is_complete": len(required_fields) == 0,
        "required_actions": required_fields,
        "optional_suggestions": optional_fields
    }


def create_moderator_subagent() -> Subagent:
    """创建 Moderator 子代理"""
    return Subagent(
        name="Moderator",
        system_prompt=Path(__file__).parent.parent / "prompts" / "moderator.md",
        tools=[check_issue_completeness]
    )
```

### 7.5 子代理配置文件（agents/__init__.py）

```python
"""子代理工厂模块"""
from pathlib import Path
from claude_agent_sdk import Subagent


def create_subagent(name: str) -> Subagent:
    """根据名称创建对应的子代理"""
    prompts = {
        "moderator": "moderator.md",
        "reviewer_a": "reviewer_a.md",
        "reviewer_b": "reviewer_b.md",
        "summarizer": "summarizer.md",
    }

    if name not in prompts:
        raise ValueError(f"Unknown subagent: {name}")

    return Subagent(
        name=name.capitalize(),
        system_prompt=(PROMPTS_DIR / prompts[name]).read_text()
    )
```

### 7.6 主入口文件（src/issuelab/__main__.py）

```python
"""主入口：支持多种子命令"""
import asyncio
import argparse
import os
from issuelab.executor import run_parallel_agents
from issuelab.coordinator import run_review_process


async def main():
    parser = argparse.ArgumentParser(description="Issue Lab Agent")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # @mention 并行执行
    execute_parser = subparsers.add_parser("execute", help="Execute agents in parallel")
    execute_parser.add_argument("--issue", type=int, required=True)
    execute_parser.add_argument("--agents", type=str, required=True, help="Space-separated agent names")

    # 顺序评审流程
    review_parser = subparsers.add_parser("review", help="Run sequential review flow")
    review_parser.add_argument("--issue", type=int, required=True)

    # 分诊流程
    triage_parser = subparsers.add_parser("triage", help="Run triage flow")
    triage_parser.add_argument("--issue", type=int, required=True)

    args = parser.parse_args()

    if args.command == "execute":
        agents = args.agents.split()
        await run_parallel_agents(args.issue, agents)
    elif args.command == "review":
        await run_review_process(args.issue)
    elif args.command == "triage":
        print(f"Running triage for issue #{args.issue}...")
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
```

### 7.7 @mention 解析器（agents/parser.py）

```python
"""@mention 解析器：从评论中提取代理名称"""
import re


# 代理名称映射表
AGENT_ALIASES = {
    # Moderator 变体
    "moderator": "moderator",
    "mod": "moderator",
    # ReviewerA 变体
    "reviewer": "reviewer_a",
    "reviewera": "reviewer_a",
    "reviewer_a": "reviewer_a",
    "reva": "reviewer_a",
    # ReviewerB 变体
    "reviewerb": "reviewer_b",
    "reviewer_b": "reviewer_b",
    "revb": "reviewer_b",
    # Summarizer 变体
    "summarizer": "summarizer",
    "summary": "summarizer",
}


def parse_mentions(comment_body: str) -> list[str]:
    """
    从评论中解析 @mention

    Args:
        comment_body: 评论正文

    Returns:
        去重后的代理名称列表
    """
    # 提取 @mention
    pattern = r'@([a-zA-Z_]+)'
    raw_mentions = re.findall(pattern, comment_body, re.IGNORECASE)

    # 映射到标准名称
    agents = []
    for m in raw_mentions:
        normalized = m.lower()
        if normalized in AGENT_ALIASES:
            agents.append(AGENT_ALIASES[normalized])

    # 去重，保持顺序
    seen = set()
    unique_agents = []
    for a in agents:
        if a not in seen:
            seen.add(a)
            unique_agents.append(a)

    return unique_agents


def has_mentions(comment_body: str) -> bool:
    """检查评论是否包含 @mention"""
    return bool(re.search(r'@[a-zA-Z_]+', comment_body))


def has_commands(comment_body: str) -> bool:
    """检查评论是否包含 /command"""
    return bool(re.search(r'/[a-zA-Z_]+', comment_body))
```

### 7.8 并行执行器（agents/executor.py）

```python
"""并行执行器：同时运行多个代理"""
import asyncio
import os
from pathlib import Path
from claude_agent_sdk import Subagent


def load_prompt(agent_name: str) -> str:
    """加载代理提示词"""
    prompts = {
        "moderator": "moderator.md",
        "reviewer_a": "reviewer_a.md",
        "reviewer_b": "reviewer_b.md",
        "summarizer": "summarizer.md",
    }
    # prompts 目录在项目根目录
    PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
    prompt_path = PROMPTS_DIR / prompts.get(agent_name, "")
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


async def run_agent(issue_number: int, agent_name: str, context: str) -> str:
    """运行单个代理"""
    agent = Subagent(
        name=agent_name.capitalize(),
        system_prompt=load_prompt(agent_name)
    )

    prompt = f"""请对 GitHub Issue #{issue_number} 执行以下任务：

{context}

请以 [Agent: {agent_name}] 为前缀发布你的回复。"""

    try:
        result = await agent.run(prompt)
        return result
    except Exception as e:
        return f"[Error] {agent_name} failed: {e}"


async def run_parallel_agents(issue_number: int, agents: list[str]):
    """
    并行运行多个代理

    Args:
        issue_number: Issue 编号
        agents: 代理名称列表
    """
    # 获取 Issue 上下文
    context = _get_issue_context(issue_number)

    # 并行执行
    tasks = [run_agent(issue_number, agent, context) for agent in agents]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 打印结果
    for i, result in enumerate(results):
        print(f"\n=== {agents[i]} result ===")
        if isinstance(result, Exception):
            print(f"Error: {result}")
        else:
            print(result)


def _get_issue_context(issue_number: int) -> str:
    """获取 Issue 上下文"""
    import subprocess
    result = subprocess.run(
        ["gh", "issue", "view", str(issue_number), "--json", "title,body,comments"],
        capture_output=True, text=True,
        env={**os.environ, "GH_TOKEN": os.environ.get("GITHUB_TOKEN", "")}
    )
    return result.stdout
```

### 7.9 代理调度器

基于 Claude Agent SDK 的 Subagent 模式，调度器逻辑内嵌在 `coordinator.py` 中：

```python
# coordinator.py 中的调度逻辑
async def run_review_process(issue_number: int):
    coordinator = create_coordinator()

    # 协调器自动调度子代理
    result = await coordinator.run(
        f"请对 Issue #{issue_number} 进行评审，依次执行 Moderator → ReviewerA → ReviewerB"
    )
    return result
```

工作流 YAML 简化为：

```yaml
# @mention 并行执行
- name: Run parallel agents
  run: uv run python -m agents execute --issue ${{ issue }} --agents "moderator reviewer_a"

# /command 顺序执行
- name: Run review flow
  run: uv run python -m agents review --issue ${{ issue }}
```

### 7.5 GitHub CLI 操作封装

使用 `gh` CLI 直接操作 GitHub 资源，无需封装：

```bash
# 发布评论
gh issue comment <issue_number> --body "<markdown>"

# 添加标签
gh issue edit <issue_number> --add-label "state:review"

# 查看 Issue 信息
gh issue view <issue_number> --json title,body,labels
```

### 7.6 标签管理

利用 `gh issue edit` 命令管理状态标签：

```yaml
# 评审开始时
gh issue edit ${{ github.event.issue.number }} --add-label "state:review"

# 评审结束时
gh issue edit ${{ github.event.issue.number }} \
  --remove-label "state:review" \
  --add-label "state:done"
```

工作流集成了 Webhook 接收、事件解析、代理调度和 GitHub API 调用等所有核心功能。`concurrency` 机制确保同一 Issue 不会并发执行。

---

## 八、提示词模板

### 8.1 Moderator 提示词

```md
你是科研讨论的Moderator。你的职责：
1) 检查issue信息是否充分（是否有链接/DOI、实验设置、指标）。不足则提出最多3个澄清问题，并建议贴 state:triage。
2) 当触发 /review 时，宣布评审流程、提醒格式与证据要求，避免跑题。
3) 永远不要编造引用。没有证据就写"缺证据"。

输出必须使用以下结构：
## Claim
## Evidence
## Uncertainty
## Next actions
```

### 8.2 ReviewerA 提示词

```md
你是ReviewerA（正方/支持者）。目标是从可行性、贡献、潜在价值角度评审，并提出改进建议。
要求：
- 不要编造引用或结果。
- 若缺乏证据，明确指出"缺证据"并建议补充什么。

输出结构：
## Claim
## Evidence
## Uncertainty
## Next actions
```

### 8.3 ReviewerB 提示词

```md
你是ReviewerB（反方/挑刺者）。目标是找漏洞、反例、不可复现点、隐藏假设、评测缺陷。
要求：
- 不要人身攻击，聚焦论证与证据。
- 不要编造引用或结果。
- 给出具体的"如何证伪/如何补实验"。

输出结构同上。
```

### 8.4 Summarizer 提示词

```md
你是Summarizer。读取整个issue和评论后，产出：
- 共识（有哪些点大家一致）
- 分歧（争论点是什么、为什么）
- 关键缺口（缺少哪些证据/实验）
- 可执行行动项（checkbox）

输出结构：
## Claim
## Evidence
## Uncertainty
## Next actions
```

---

## 九、部署指南

### 9.1 环境准备

部署前需要准备以下环境变量和权限。`GITHUB_TOKEN` 是 GitHub Personal Access Token，在 GitHub Actions 中默认使用 `secrets.GITHUB_TOKEN`，需要具备 issues:read、issues:write 和 contents:read 权限。`ANTHROPIC_API_TOKEN` 是 Anthropic API 密钥，需要配置为 GitHub Secret，用于调用 Claude 模型。

### 9.2 GitHub 仓库配置

**第一步：创建 Secret**

在仓库 Settings → Secrets and variables → Actions 中添加：
- `ANTHROPIC_API_TOKEN`: 你的 Anthropic API 密钥

**第二步：启用 Actions**

确保仓库的 Actions 功能已启用（公开仓库默认启用，私有仓库可能需要配置）。

**第三步：推送工作流文件**

将 `.github/workflows/orchestrator.yml` 推送到仓库主分支，GitHub Actions 会自动识别并启用工作流。

### 9.3 本地测试（使用 uv）

```bash
# 安装 uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 初始化项目（如果从零开始）
uv init --name issuelab --python 3.11

# 同步依赖
uv sync

# 设置环境变量并运行
export ISSUE_NUMBER=1
export GITHUB_TOKEN=your_token
export ANTHROPIC_API_TOKEN=your_key

uv run python -m agents
```

### 9.4 pyproject.toml 配置

项目使用 uv 标准配置，替代传统的 requirements.txt：

```toml
[project]
name = "issuelab"
version = "0.1.0"
description = "AI 辅助科研评审系统"
requires-python = ">=3.11"
dependencies = [
    "anthropic-claude-agent-sdk>=0.1.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## 十、Claude Agent SDK 接入说明

### 10.1 核心概念

Claude Agent SDK 提供以下核心能力：

- **Agent**: 主代理类，包含系统提示词、工具集和执行循环
- **Subagent**: 子代理，支持并行执行和上下文隔离
- **@tool 装饰器**: 定义自定义工具供代理调用
- **Agent Loop**: 自动处理工具调用和响应生成

### 10.2 接入点定位

所有代理的 SDK 调用集中在 `agents/coordinator.py` 的 `create_coordinator()` 函数中，参考 7.3 节代码示例。

### 10.2 SDK 调用最佳实践

MVP 阶段建议使用 Subagent 模式：
- **Coordinator** 作为主代理负责任务分解和结果汇总
- **Moderator、ReviewerA、ReviewerB** 作为子代理并行或顺序执行
- **自定义工具**封装 GitHub API 操作，供代理调用

后续扩展时，可根据需要为特定代理添加工具调用能力，如让 ReviewerB 具备代码执行能力以验证论文中的实验结果。

---

## 十一、扩展路径规划

### 11.1 短期扩展方向

MVP 稳定运行后，可按以下优先级进行功能扩展。首先实现更多代理角色，如 `/reproduce` 命令触发复现代理，`/search` 命令触发文献检索代理。其次为现有代理添加工具能力，让 Moderator 可以主动请求补充信息，让 ReviewerB 可以运行代码验证实验结果。最后完善限流策略，增加基于 IP 的限流和基于用户的配额管理。

### 11.2 长期演进方向

从长期视角，系统可向三个方向演进。第一个方向是知识积累，建立论文、评审意见和实验结果的向量数据库，支持跨 Issue 检索和引用。第二个方向是流程自动化，实现完整的科研工作流，从论文调研、实验设计、结果复现到论文写作的全流程 AI 辅助。第三个方向是多模态支持，支持图表分析、代码审查和数据可视化等场景。

---

## 十二、验证清单

在正式投入使用前，请按以下步骤验证系统功能：

### 基础验证
第一步，创建所有必要的 GitHub Labels（type、state、bot 四类共 12 个标签，确认包含 `state:ready-for-review`）。第二步，提交 Issue Forms 模板文件并验证 GitHub 是否正确解析。第三步，提交 `.github/workflows/orchestrator.yml` 并在 Actions 面板确认工作流已启用。第四步，配置 `ANTHROPIC_API_TOKEN` Secret。

### @mention 并行触发验证（推荐）
第五步，创建一个测试 Issue，填写必要信息后在评论中输入 `@Moderator 请分诊，@ReviewerA 请评审，@ReviewerB 请找问题`。第六步，在 Actions 面板观察工作流运行状态，验证是否并行触发三个代理。第七步，检查三个代理是否几乎同时发布独立评论，验证并行执行效果。

### /command 顺序触发验证
第八步，创建新 Issue，输入 `/review`。第九步，验证是否按顺序执行（Moderator → ReviewerA → ReviewerB）。第十步，输入 `/summarize`，验证 Summarizer 是否正确汇总。第十一步，输入 `/quiet`，验证机器人是否停止响应。

### 标签触发验证（主动触发）
第十二步，创建新 Issue，手动添加 `state:ready-for-review` 标签。第十三步，观察 Actions 是否自动触发完整评审流程。第十四步，验证状态标签自动变更（`state:ready-for-review` 被移除，`state:review` 被添加）。

### 并发控制验证
第十五步，在工作流运行时再次添加 `state:ready-for-review` 标签，验证第二个运行被自动取消。

完成以上验证后，系统即可投入正式使用。

---

## 附录：完整目录结构

```
issuelab/
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── paper.yml
│   │   ├── proposal.yml
│   │   ├── result.yml
│   │   └── question.yml
│   └── workflows/
│       └── orchestrator.yml    # 主工作流（支持 @mention、/command、标签触发）
├── src/
│   └── issuelab/               # 主包
│       ├── __init__.py
│       ├── __main__.py         # 主入口（支持 execute/review/triage 子命令）
│       ├── coordinator.py      # 协调器主代理（顺序执行）
│       ├── executor.py         # 并行执行器（@mention 模式）
│       ├── parser.py           # @mention 解析器
│       ├── agents/             # 代理模块
│       │   ├── __init__.py
│       │   ├── moderator.py
│       │   ├── reviewer_a.py
│       │   ├── reviewer_b.py
│       │   └── summarizer.py
│       └── tools/              # 工具模块
│           ├── __init__.py
│           └── github.py
├── prompts/                    # 提示词模板
│   ├── moderator.md
│   ├── reviewer_a.md
│   ├── reviewer_b.md
│   └── summarizer.md
├── docs/
│   └── MVP.md
├── tests/
│   └── __init__.py
├── pyproject.toml              # uv 项目配置
├── uv.lock
└── README.md
```

## 附录：pyproject.toml 完整配置

```toml
[project]
name = "issuelab"
version = "0.1.0"
description = "AI 辅助科研评审系统"
requires-python = ">=3.11"
dependencies = [
    "anthropic-claude-agent-sdk>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.4.0",
]

[tool.uv]
package = true

[tool.ruff]
line-length = 100
target-version = "py311"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## 附录：agents/__init__.py

```python
"""子代理工厂模块"""
from pathlib import Path
from claude_agent_sdk import Subagent


def load_prompt(agent_name: str) -> str:
    """加载代理提示词"""
    prompts = {
        "moderator": "moderator.md",
        "reviewer_a": "reviewer_a.md",
        "reviewer_b": "reviewer_b.md",
        "summarizer": "summarizer.md",
    }
    # prompts 目录在项目根目录
    PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"
    prompt_path = PROMPTS_DIR / prompts.get(agent_name, "")
    if prompt_path.exists():
        return prompt_path.read_text()
    return ""


def create_subagent(name: str) -> Subagent:
    """根据名称创建对应的子代理"""
    prompts = {
        "moderator": "moderator.md",
        "reviewer_a": "reviewer_a.md",
        "reviewer_b": "reviewer_b.md",
        "summarizer": "summarizer.md",
    }

    if name not in prompts:
        raise ValueError(f"Unknown subagent: {name}")

    return Subagent(
        name=name.capitalize(),
        system_prompt=load_prompt(name)
    )


# 代理别名映射表（用于 @mention 解析）
AGENT_ALIASES = {
    "moderator": "moderator",
    "mod": "moderator",
    "reviewer": "reviewer_a",
    "reviewera": "reviewer_a",
    "reviewer_a": "reviewer_a",
    "reva": "reviewer_a",
    "reviewerb": "reviewer_b",
    "reviewer_b": "reviewer_b",
    "revb": "reviewer_b",
    "summarizer": "summarizer",
    "summary": "summarizer",
}


def normalize_agent_name(name: str) -> str:
    """标准化代理名称"""
    return AGENT_ALIASES.get(name.lower(), name)
```
