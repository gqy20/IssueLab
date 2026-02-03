# 跨仓库触发方案调研

## 需求分析

用户希望：
1. ✅ 用户 fork IssueLab 后，能够接入主系统
2. ✅ 在主仓库（gqy20/IssueLab）的 Issue 中 @username 可以触发该用户的智能体
3. ✅ **使用用户自己的 Actions 和 API Key**（不消耗主仓库资源）
4. ✅ 用户通过 PR 注册到主系统

## 方案对比

### 方案 1：直接 PR 到主仓库 ❌

**实现方式：**
```
agents/
├── gqy20/
├── alice/      # Alice PR 添加
├── bob/        # Bob PR 添加
└── charlie/    # Charlie PR 添加
```

**工作流程：**
1. 用户在主仓库的 `agents/username/` 创建配置
2. 提交 PR 到主仓库
3. 合并后，主仓库的 Actions 识别并执行

**问题：**
- ❌ **使用主仓库的 Actions**（消耗主仓库的 GitHub Actions 配额）
- ❌ **使用主仓库的 API Key**（安全风险，费用问题）
- ❌ 主仓库需要管理所有用户的智能体
- ❌ 用户无法独立管理自己的智能体配置

**结论：不可行**

---

### 方案 2：Repository Dispatch 跨仓库触发 ✅ 推荐

**核心机制：GitHub Repository Dispatch Event**

GitHub 提供了 `repository_dispatch` API，允许一个仓库触发另一个仓库的 Actions。

**架构设计：**

```
主仓库 (gqy20/IssueLab)
├── agents/
│   ├── _registry/          # 注册中心（新增）
│   │   ├── alice.yml       # Alice 的注册信息
│   │   ├── bob.yml         # Bob 的注册信息
│   │   └── charlie.yml     # Charlie 的注册信息
│   └── gqy20/              # 官方示例
│       ├── agent.yml
│       └── prompt.md
└── .github/workflows/
    └── dispatch_agent.yml  # 分发事件到用户仓库
```

**注册文件格式（agents/_registry/alice.yml）：**
```yaml
# 用户注册信息
username: alice
repository: alice/IssueLab    # Alice 的 fork 仓库
triggers:
  - "@alice"
  - "@alice-cv"
enabled: true
labels_filter:                # 可选：只响应特定标签
  - "domain:cv"
```

**工作流程：**

1. **用户注册（通过 PR）**：
   ```bash
   # Alice fork 主仓库后
   cd gqy20-IssueLab-fork

   # 创建注册文件
   cat > agents/_registry/alice.yml <<EOF
   username: alice
   repository: alice/IssueLab
   triggers:
     - "@alice"
   enabled: true
   EOF

   # 提交 PR 到主仓库
   git add agents/_registry/alice.yml
   git commit -m "Register alice's agent"
   git push
   # Create PR on GitHub
   ```

2. **主仓库 Issue 触发**：
   ```
   Issue: "这个功能如何实现？@alice"
   ↓
   主仓库 Actions 触发
   ↓
   读取 agents/_registry/alice.yml
   ↓
   检测到 "@alice" 在 triggers 中
   ↓
   使用 repository_dispatch 向 alice/IssueLab 发送事件
   ```

3. **用户 fork 响应**：
   ```
   alice/IssueLab 收到 repository_dispatch 事件
   ↓
   Alice fork 的 Actions 触发
   ↓
   读取 alice/IssueLab 的 agents/alice/agent.yml
   ↓
   使用 Alice 自己的 ANTHROPIC_API_TOKEN
   ↓
   执行 Alice 的智能体
   ↓
   结果回传到主仓库 Issue（通过评论）
   ```

**主仓库 Workflow（.github/workflows/dispatch_agent.yml）：**

```yaml
name: Dispatch to User Agents

on:
  issues:
    types: [opened, edited]
  issue_comment:
    types: [created]

jobs:
  dispatch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Parse mentions
        id: parse
        run: |
          # 提取 Issue/Comment 中的 @mentions
          python scripts/parse_mentions.py \
            --issue-number ${{ github.event.issue.number }}

      - name: Dispatch to user repos
        run: |
          # 读取注册信息，向匹配的用户仓库发送 repository_dispatch
          python scripts/dispatch_to_users.py \
            --mentions "${{ steps.parse.outputs.mentions }}" \
            --issue-number ${{ github.event.issue.number }}
        env:
          GITHUB_TOKEN: ${{ secrets.DISPATCH_TOKEN }}
```

**用户 fork Workflow（alice/IssueLab/.github/workflows/agent.yml）：**

```yaml
name: Run Agent

on:
  repository_dispatch:
    types: [issue_mention]  # 接收主仓库的分发事件

jobs:
  run-agent:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.12'

      - name: Run agent
        run: |
          python -m issuelab.sdk_executor \
            --agent-config agents/alice/agent.yml \
            --agent-prompt agents/alice/prompt.md \
            --issue-repo ${{ github.event.client_payload.repo }} \
            --issue-number ${{ github.event.client_payload.issue_number }}
        env:
          ANTHROPIC_API_TOKEN: ${{ secrets.ANTHROPIC_API_TOKEN }}  # Alice 自己的
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**优势：**
- ✅ 用户使用自己的 Actions 配额
- ✅ 用户使用自己的 API Key
- ✅ 主仓库只负责分发，不执行
- ✅ 用户通过 PR 注册（易于管理）
- ✅ 用户可以随时更新自己的智能体
- ✅ 完全去中心化

**限制：**
- ⚠️ 需要主仓库有一个 `DISPATCH_TOKEN`（Fine-grained PAT，用于触发其他仓库）
- ⚠️ 用户 fork 需要启用 Actions
- ⚠️ 首次设置稍复杂

---

### 方案 3：Webhook 方案

**实现方式：**
用户在注册文件中提供 webhook URL，主仓库转发事件。

**问题：**
- ❌ 用户需要部署和维护服务器
- ❌ 复杂度高
- ❌ 不适合普通用户

**结论：不推荐**

---

## 最终推荐方案

**Repository Dispatch（方案 2）**

### 关键组件

1. **注册中心** (`agents/_registry/`)
   - 用户通过 PR 提交注册文件
   - 主仓库审核后合并
   - 轻量级配置（只有触发信息，不包含提示词）

2. **主仓库 Dispatcher**
   - 监听 Issue/Comment 事件
   - 解析 @mentions
   - 向匹配的用户仓库发送 repository_dispatch

3. **用户 fork Agent**
   - 接收 repository_dispatch 事件
   - 执行智能体（使用自己的 API Key）
   - 回传结果到主仓库

### 数据流图

```
主仓库 Issue: "@alice 帮我分析一下"
         ↓
    [Dispatcher]
         ↓
    读取 _registry/alice.yml
         ↓
    检测 "@alice" 匹配
         ↓
    repository_dispatch
         ↓ (跨仓库)
    alice/IssueLab
         ↓
    [Alice's Actions]
         ↓
    使用 Alice 的 API Key
         ↓
    执行智能体
         ↓
    回传评论
         ↓
    主仓库 Issue 显示结果
```

### 用户体验

**Alice 的操作流程：**

1. Fork gqy20/IssueLab
2. 在自己的 fork 中配置 `agents/alice/agent.yml` 和 `prompt.md`
3. 在自己的 fork 设置 `ANTHROPIC_API_TOKEN` secret
4. 创建 `agents/_registry/alice.yml` 注册文件
5. 提交 PR 到主仓库
6. PR 合并后，Alice 的智能体接入完成
7. 在主仓库任何 Issue 中 @alice，就会触发 Alice fork 的 Actions
8. Alice 可以随时在自己的 fork 中更新智能体配置

**用户友好性：**
- ✅ 一次配置，持续使用
- ✅ 用户完全控制自己的智能体
- ✅ 费用和配额独立
- ✅ 隐私和安全（API Key 不泄露）

---

## 技术实现细节

### repository_dispatch API 调用

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $DISPATCH_TOKEN" \
  https://api.github.com/repos/alice/IssueLab/dispatches \
  -d '{
    "event_type": "issue_mention",
    "client_payload": {
      "repo": "gqy20/IssueLab",
      "issue_number": 42,
      "issue_title": "Feature Request",
      "issue_body": "...",
      "mention": "@alice",
      "comment_id": 123456
    }
  }'
```

### 权限要求

**主仓库需要：**
- `DISPATCH_TOKEN`：Fine-grained PAT，权限：
  - `contents: read`
  - `metadata: read`
  - 对目标仓库（alice/IssueLab）：`actions: write`

**用户 fork 需要：**
- `ANTHROPIC_API_TOKEN`：Claude API Key
- `GITHUB_TOKEN`：自动提供，用于回复评论

### 安全考虑

1. **注册审核**：主仓库 PR 需要审核，防止恶意注册
2. **速率限制**：在注册文件中配置 rate_limit
3. **权限最小化**：DISPATCH_TOKEN 只给必要权限
4. **API Key 隔离**：每个用户用自己的 Key

---

## 实现计划

### Phase 1: 基础架构
- [ ] 创建 `agents/_registry/` 目录
- [ ] 实现 `scripts/parse_mentions.py`
- [ ] 实现 `scripts/dispatch_to_users.py`
- [ ] 配置主仓库 Workflow

### Phase 2: 用户接入
- [ ] 编写用户注册指南
- [ ] 提供 fork Workflow 模板
- [ ] 创建示例注册文件

### Phase 3: 测试和文档
- [ ] 测试跨仓库触发
- [ ] 编写完整文档
- [ ] 创建视频教程

---

## 对比表格

| 特性 | 方案1: PR到主仓库 | 方案2: Repository Dispatch | 方案3: Webhook |
|-----|------------------|--------------------------|---------------|
| 用户独立性 | ❌ 低 | ✅ 高 | ✅ 高 |
| API Key 隔离 | ❌ 否 | ✅ 是 | ✅ 是 |
| Actions 配额 | ❌ 消耗主仓库 | ✅ 用户自己 | ✅ 用户自己 |
| 实现复杂度 | ✅ 简单 | ⚠️ 中等 | ❌ 复杂 |
| 用户门槛 | ✅ 低 | ⚠️ 中等 | ❌ 高 |
| 可扩展性 | ❌ 差 | ✅ 好 | ✅ 好 |
| 维护成本 | ❌ 高 | ✅ 低 | ❌ 高 |

## 结论

**推荐使用方案 2：Repository Dispatch**

这是最符合需求的方案：
1. ✅ 用户通过 PR 注册（`agents/_registry/username.yml`）
2. ✅ 在主仓库被 @mention 时触发用户 fork 的 Actions
3. ✅ 用户使用自己的 API Key 和 Actions 配额
4. ✅ 完全去中心化，可扩展

下一步：实现 dispatcher 脚本和注册机制。
