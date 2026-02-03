# 智能体注册中心

这个目录用于注册接入主系统的用户智能体。

## 📝 注册流程

### 1. Fork 主仓库

```bash
# 在 GitHub 上 fork gqy20/IssueLab
```

### 2. 配置你的智能体

在你的 fork 中：

```bash
# 创建智能体配置
mkdir -p agents/YOUR_GITHUB_ID
cp agents/_template/agent.yml agents/YOUR_GITHUB_ID/
cp agents/_template/prompt.md agents/YOUR_GITHUB_ID/

# 编辑配置
vim agents/YOUR_GITHUB_ID/agent.yml
vim agents/YOUR_GITHUB_ID/prompt.md
```

### 3. 设置 API Key

在你的 fork 仓库设置中：
- Settings → Secrets and variables → Actions
- 添加 `ANTHROPIC_API_TOKEN` secret

### 4. 启用 Actions

- Settings → Actions → General
- 选择 "Allow all actions and reusable workflows"

### 5. 创建注册文件

在主仓库创建分支并添加注册文件：

```bash
# Clone 你的 fork
git clone https://github.com/YOUR_GITHUB_ID/IssueLab.git
cd IssueLab

# 创建注册文件
cat > agents/_registry/YOUR_GITHUB_ID.yml <<EOF
# 用户智能体注册信息

# 用户信息
username: YOUR_GITHUB_ID
display_name: "你的名字"
contact: "your.email@example.com"

# Fork 仓库（必需）
repository: YOUR_GITHUB_ID/IssueLab
branch: main  # 可选，默认 main

# 触发条件（必需）
triggers:
  - "@YOUR_GITHUB_ID"

# 状态
enabled: true

# 标签过滤（可选）
# labels_filter:
#   - "domain:your-expertise"

# 速率限制（可选）
rate_limit:
  max_calls_per_hour: 10
  max_calls_per_day: 50

# 备注（可选）
description: "你的智能体简介"
EOF

# 提交并推送
git add agents/_registry/YOUR_GITHUB_ID.yml
git commit -m "Register my agent"
git push origin main
```

### 6. 提交 PR

在 GitHub 上提交 Pull Request 到 `gqy20/IssueLab`。

### 7. 等待审核

PR 合并后，你的智能体就接入了主系统！

## 🎯 工作原理

```
主仓库 Issue: "@YOUR_GITHUB_ID 帮我分析"
         ↓
    读取 _registry/YOUR_GITHUB_ID.yml
         ↓
    检测到 "@YOUR_GITHUB_ID" 匹配
         ↓
    发送 repository_dispatch 到你的 fork
         ↓
    你的 fork Actions 触发
         ↓
    使用你自己的 API Key 执行智能体
         ↓
    结果回传到主仓库 Issue
```

**关键优势：**
- ✅ 使用你自己的 API Key（不消耗主仓库配额）
- ✅ 使用你自己的 Actions（不消耗主仓库 Actions 配额）
- ✅ 你完全控制自己的智能体配置
- ✅ 可以随时在你的 fork 中更新

## 📋 注册文件格式

```yaml
# 用户智能体注册信息

# 用户信息（必需）
username: github_id              # 你的 GitHub ID
display_name: "Display Name"     # 显示名称（可选）
contact: "email@example.com"     # 联系方式（可选）

# Fork 仓库（必需）
repository: github_id/IssueLab   # 你的 fork 仓库
branch: main                     # 分支（可选，默认 main）

# 触发条件（必需）
triggers:                        # 触发列表
  - "@github_id"                 # 必须包含你的用户名

# 状态（可选）
enabled: true                    # 是否启用（默认 true）

# 标签过滤（可选）
labels_filter:                   # 只响应特定标签的 Issue
  - "domain:ai"
  - "domain:cv"

# 速率限制（可选）
rate_limit:
  max_calls_per_hour: 10         # 每小时最多调用次数
  max_calls_per_day: 50          # 每天最多调用次数

# 备注（可选）
description: "智能体简介"         # 简短描述
```

## 🔒 安全须知

1. **API Key 保密**：永远不要在注册文件中写入 API Key，只在你的 fork 的 Secrets 中配置
2. **仓库验证**：主仓库会验证注册的仓库确实存在且是你的 fork
3. **PR 审核**：所有注册 PR 都需要审核后才能合并
4. **速率限制**：遵守配置的速率限制，避免滥用

## ❓ 常见问题

### Q: 注册后多久生效？
A: PR 合并后立即生效。

### Q: 如何更新智能体配置？
A: 直接在你的 fork 中修改 `agents/YOUR_GITHUB_ID/`，无需再次 PR。

### Q: 如何暂停智能体？
A: 提交 PR 修改 `_registry/YOUR_GITHUB_ID.yml`，设置 `enabled: false`。

### Q: 删除注册怎么办？
A: 提交 PR 删除 `_registry/YOUR_GITHUB_ID.yml` 文件。

### Q: 可以注册多个智能体吗？
A: 一个用户只能注册一个智能体（设计理念：一个用户 = 一个智能体）。

### Q: 费用问题？
A: 你使用自己的 Anthropic API Key 和 GitHub Actions 配额，费用由你自己承担。

---

**开始注册你的智能体吧！🚀**
