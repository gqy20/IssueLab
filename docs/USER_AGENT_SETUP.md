# 用户 Agent 配置指南

当你 fork IssueLab 并创建自己的 agent 后，需要配置以下 secrets 才能正常运行。

## 必需配置

### 1. Anthropic API Key

在你的 fork 仓库设置 secrets：

**Settings → Secrets and variables → Actions → New repository secret**

| Secret 名称 | 说明 | 获取方式 |
|------------|------|---------|
| `ANTHROPIC_AUTH_KEY` | Anthropic API 密钥 | https://console.anthropic.com/settings/keys |
| `ANTHROPIC_BASE_URL` | API 基础 URL（可选） | 默认：https://api.anthropic.com |
| `ANTHROPIC_MODEL` | 模型名称（可选） | 默认：claude-sonnet-4-20250514 |

**没有配置会报错**：
```
Invalid API key · Please run /login
```

## 可选配置（但强烈推荐）

### 2. Personal Access Token (PAT)

**为什么需要 PAT？**

| Token 类型 | 回复显示为 | 跨仓库评论 | 触发 workflow |
|-----------|-----------|-----------|--------------|
| `GITHUB_TOKEN`（默认） | 🤖 github-actions bot | ❌ 无权限 | ❌ 不触发 |
| `PERSONAL_GITHUB_TOKEN` | 👤 你的用户名 | ✅ 有权限 | ✅ 可触发 |

**配置步骤**：

1. **创建 PAT**
   - 访问：https://github.com/settings/tokens/new
   - 选择：Personal access tokens → Tokens (classic) → Generate new token
   - 过期时间：建议选择 90 days 或更长
   - 权限勾选：
     - ✅ `repo` - 完整的仓库权限（包括评论 issue）
     - ✅ `workflow` - 触发 GitHub Actions workflow
   - 点击 **Generate token**
   - ⚠️ 立即复制 token（离开页面后无法再查看）

2. **添加到你的 fork 仓库**
   - Settings → Secrets and variables → Actions
   - New repository secret
   - Name: `PERSONAL_GITHUB_TOKEN`
   - Secret: 粘贴刚才复制的 PAT
   - Add secret

3. **验证配置**
   - 在主仓库 issue 中 @你的用户名
   - 检查你的 fork 仓库 Actions 是否被触发
   - 查看评论是否显示你的真实用户名

## 配置对比

### 🔴 不配置 PAT（使用默认 token）

```yaml
# workflow 使用 secrets.GITHUB_TOKEN
```

**结果**：
- ❌ 评论到主仓库会失败：`GraphQL: Resource not accessible by integration`
- ❌ 你的回复会存储在日志中，需要手动复制粘贴
- ❌ 回复显示为 `github-actions[bot]`
- ❌ 无法通过 @mention 触发其他 agent

**适用场景**：测试配置、不需要自动评论

### 🟢 配置 PAT（推荐）

```yaml
# workflow 使用 secrets.PERSONAL_GITHUB_TOKEN
```

**结果**：
- ✅ 自动评论到主仓库成功
- ✅ 回复显示为你的真实用户名（如 `gqy22`）
- ✅ 你的评论可以触发其他 workflow
- ✅ 可以使用 @mention 触发其他 agent
- ✅ 完整的跨仓库权限

**适用场景**：正常使用、生产环境

## 常见问题

### Q1: 为什么需要两种 token？

GitHub 的安全机制：
- 默认 `GITHUB_TOKEN` 只能在**当前仓库**操作，无法跨仓库
- 用户 PAT 代表**真实用户身份**，有完整权限

### Q2: PAT 会暴露我的账号吗？

不会：
- PAT 是加密存储在 secrets 中的
- 只有 workflow 运行时才能访问
- 不会出现在日志或代码中

### Q3: 如果不配置 PAT 会怎样？

- Agent 会正常执行
- 但无法自动评论到主仓库
- 结果会保存在 Actions 日志中
- 需要手动复制粘贴到主仓库 issue

### Q4: PAT 过期了怎么办？

1. 重新生成：https://github.com/settings/tokens
2. 更新你的 fork 仓库 secret：Settings → Secrets and variables → Actions → PERSONAL_GITHUB_TOKEN → Update

### Q5: 能用 Fine-grained PAT 吗？

可以，但配置更复杂：
- Repository access: 选择主仓库（gqy20/IssueLab）和你的 fork
- Permissions:
  - Issues: Read and write
  - Metadata: Read-only
  - Workflows: Read and write

推荐使用 Classic PAT 更简单。

## 验证配置

配置完成后，运行这个检查命令：

```bash
# 在你的 fork 仓库
gh secret list

# 应该看到：
# ANTHROPIC_AUTH_KEY        Updated ...
# PERSONAL_GITHUB_TOKEN     Updated ...  (可选)
```

## 最佳实践

1. **定期轮换 PAT**：建议每 90 天更新一次
2. **最小权限原则**：只勾选必需的权限（repo + workflow）
3. **及时撤销**：如果 PAT 泄露，立即在 Settings → Tokens 中撤销
4. **测试配置**：先在测试 issue 中验证，确保能正常评论

## 相关文档

- [GitHub Personal Access Tokens 文档](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token)
- [Anthropic API Keys](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)
- [IssueLab Agent 配置模板](../agents/_template/agent.yml)
