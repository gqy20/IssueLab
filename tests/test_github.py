"""测试 GitHub 工具"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from issuelab.tools.github import get_issue_info, post_comment, update_label


def test_get_issue_info():
    """测试获取 Issue 信息"""
    # Mock gh 命令返回
    with patch("issuelab.tools.github.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0, stdout='{"number":1,"title":"测试 Issue","body":"内容","labels":[{"name":"bug"}]}'
        )

        result = get_issue_info(1)

        assert result["number"] == 1
        assert result["title"] == "测试 Issue"
        mock_run.assert_called_once()


def test_post_comment():
    """测试发布评论"""
    with patch("issuelab.tools.github.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = post_comment(1, "测试评论")

        # 新的实现返回 bool
        assert result is True
        mock_run.assert_called_once()


def test_post_comment_limits_mentions(monkeypatch):
    """相关人员区域最多输出 2 个，按出现次数排序"""
    body = """```yaml
summary: "Test"
findings: []
recommendations: []
mentions:
  - arxiv_observer
  - gqy22
  - observer
  - summarizer
  - moderator
confidence: "high"
```"""

    captured = {}

    def fake_run(cmd, capture_output, text, env):
        captured["cmd"] = cmd
        return MagicMock(returncode=0)

    monkeypatch.setattr("issuelab.tools.github.subprocess.run", fake_run)
    monkeypatch.setattr("issuelab.tools.github.os.unlink", lambda _path: None)
    monkeypatch.setattr("issuelab.mention_policy.filter_mentions", lambda mentions, policy=None: (mentions, []))

    result = post_comment(1, body)
    assert result is True

    cmd = captured.get("cmd", [])
    assert "--body-file" in cmd
    body_path = cmd[cmd.index("--body-file") + 1]
    content = Path(body_path).read_text(encoding="utf-8")

    last_line = content.strip().splitlines()[-1]
    assert last_line == "相关人员: @arxiv_observer @gqy22"


def test_update_label():
    """测试更新标签"""
    with patch("issuelab.tools.github.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = update_label(1, "bug", action="add")

        # 新的实现返回 bool
        assert result is True
        mock_run.assert_called_once()
