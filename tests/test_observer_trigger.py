"""
测试 Observer 自动触发功能

TDD 测试用例：
1. 判断内置agent
2. 触发内置agent（通过label）
3. 触发用户agent（通过dispatch）
4. observe-batch 集成测试
"""

import subprocess
from unittest.mock import Mock, patch


class TestBuiltinAgentDetection:
    """测试内置agent检测"""

    def test_moderator_is_builtin(self):
        """Moderator应该被识别为内置agent"""
        from issuelab.observer_trigger import is_builtin_agent

        assert is_builtin_agent("moderator") is True

    def test_reviewer_a_is_builtin(self):
        """Reviewer_a应该被识别为内置agent"""
        from issuelab.observer_trigger import is_builtin_agent

        assert is_builtin_agent("reviewer_a") is True

    def test_echo_is_builtin(self):
        """Echo应该被识别为内置agent"""
        from issuelab.observer_trigger import is_builtin_agent

        assert is_builtin_agent("echo") is True

    def test_user_agent_is_not_builtin(self):
        """用户agent不应该被识别为内置agent"""
        from issuelab.observer_trigger import is_builtin_agent

        assert is_builtin_agent("gqy22") is False
        assert is_builtin_agent("alice") is False

    def test_empty_string_is_not_builtin(self):
        """空字符串不应该被识别为内置agent"""
        from issuelab.observer_trigger import is_builtin_agent

        assert is_builtin_agent("") is False

    def test_case_insensitive(self):
        """agent名称应该不区分大小写"""
        from issuelab.observer_trigger import is_builtin_agent

        assert is_builtin_agent("Moderator") is True
        assert is_builtin_agent("REVIEWER_A") is True


class TestBuiltinAgentTrigger:
    """测试内置agent触发"""

    @patch("subprocess.run")
    def test_trigger_builtin_agent_adds_label(self, mock_run):
        """触发内置agent应该通过workflow dispatch触发"""
        from issuelab.observer_trigger import trigger_builtin_agent

        mock_run.return_value = Mock(returncode=0)

        trigger_builtin_agent("moderator", 42)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "gh" in call_args
        assert "workflow" in call_args
        assert "run" in call_args
        assert "agent.yml" in call_args
        assert "-f" in call_args
        assert "agent=moderator" in call_args
        assert "issue_number=42" in call_args

    @patch("subprocess.run")
    def test_trigger_builtin_agent_returns_true_on_success(self, mock_run):
        """成功触发应该返回True"""
        from issuelab.observer_trigger import trigger_builtin_agent

        mock_run.return_value = Mock(returncode=0)

        result = trigger_builtin_agent("echo", 1)

        assert result is True

    @patch("subprocess.run")
    def test_trigger_builtin_agent_returns_false_on_failure(self, mock_run):
        """触发失败应该返回False"""
        from issuelab.observer_trigger import trigger_builtin_agent

        mock_run.side_effect = subprocess.CalledProcessError(1, "gh")

        result = trigger_builtin_agent("echo", 1)

        assert result is False

    @patch("subprocess.run")
    def test_trigger_multiple_builtin_agents(self, mock_run):
        """可以触发多个不同的内置agent"""
        from issuelab.observer_trigger import trigger_builtin_agent

        mock_run.return_value = Mock(returncode=0)

        trigger_builtin_agent("moderator", 1)
        trigger_builtin_agent("reviewer_a", 2)
        trigger_builtin_agent("echo", 3)

        assert mock_run.call_count == 3


class TestUserAgentTrigger:
    """测试用户agent触发"""

    @patch("issuelab.cli.dispatch.main")
    def test_trigger_user_agent_calls_dispatch(self, mock_dispatch, monkeypatch):
        """触发用户agent应该调用dispatch系统"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.return_value = 0

        result = trigger_user_agent(
            username="gqy22", issue_number=42, issue_title="Test Issue", issue_body="Test body"
        )

        mock_dispatch.assert_called_once()
        assert result is True

    @patch("issuelab.cli.dispatch.main")
    def test_trigger_user_agent_with_correct_params(self, mock_dispatch, monkeypatch):
        """触发用户agent应该传递正确的参数"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.return_value = 0

        trigger_user_agent(username="alice", issue_number=123, issue_title="Bug Report", issue_body="Description")

        # 验证dispatch被正确调用
        mock_dispatch.assert_called_once()

    @patch("issuelab.cli.dispatch.main")
    def test_trigger_user_agent_returns_false_on_failure(self, mock_dispatch, monkeypatch):
        """dispatch失败应该返回False"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.return_value = 1  # 失败

        result = trigger_user_agent(username="gqy22", issue_number=1, issue_title="Test", issue_body="Body")

        assert result is False

    @patch("issuelab.cli.dispatch.main")
    def test_trigger_user_agent_handles_exception(self, mock_dispatch, monkeypatch):
        """dispatch异常应该被处理并返回False"""
        from issuelab.observer_trigger import trigger_user_agent

        monkeypatch.setenv("GITHUB_REPOSITORY", "test/repo")
        mock_dispatch.side_effect = Exception("Dispatch error")

        result = trigger_user_agent(username="gqy22", issue_number=1, issue_title="Test", issue_body="Body")

        assert result is False


class TestObserverAutoTrigger:
    """测试Observer自动触发集成"""

    @patch("issuelab.observer_trigger.trigger_builtin_agent")
    @patch("issuelab.observer_trigger.is_builtin_agent")
    def test_auto_trigger_builtin_agent(self, mock_is_builtin, mock_trigger_builtin):
        """Observer判断需要触发内置agent时应该添加label"""
        from issuelab.observer_trigger import auto_trigger_agent

        mock_is_builtin.return_value = True
        mock_trigger_builtin.return_value = True

        result = auto_trigger_agent(
            agent_name="moderator", issue_number=1, issue_title="Test", issue_body="Body"
        )

        mock_trigger_builtin.assert_called_once_with("moderator", 1)
        assert result is True

    @patch("issuelab.observer_trigger.trigger_user_agent")
    @patch("issuelab.observer_trigger.is_builtin_agent")
    def test_auto_trigger_user_agent(self, mock_is_builtin, mock_trigger_user):
        """Observer判断需要触发用户agent时应该调用dispatch"""
        from issuelab.observer_trigger import auto_trigger_agent

        mock_is_builtin.return_value = False
        mock_trigger_user.return_value = True

        result = auto_trigger_agent(agent_name="gqy22", issue_number=1, issue_title="Test", issue_body="Body")

        # trigger_user_agent使用位置参数，不是关键字参数
        mock_trigger_user.assert_called_once_with("gqy22", 1, "Test", "Body")
        assert result is True

    @patch("issuelab.observer_trigger.trigger_builtin_agent")
    @patch("issuelab.observer_trigger.is_builtin_agent")
    def test_auto_trigger_returns_false_on_failure(self, mock_is_builtin, mock_trigger_builtin):
        """触发失败应该返回False"""
        from issuelab.observer_trigger import auto_trigger_agent

        mock_is_builtin.return_value = True
        mock_trigger_builtin.return_value = False

        result = auto_trigger_agent(agent_name="echo", issue_number=1, issue_title="Test", issue_body="Body")

        assert result is False


class TestObserveBatchIntegration:
    """测试observe-batch命令的自动触发功能"""

    @patch("issuelab.observer_trigger.auto_trigger_agent")
    def test_observe_batch_triggers_on_should_trigger_true(self, mock_auto_trigger):
        """observe-batch结果为should_trigger=True时应该自动触发"""
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

    @patch("issuelab.observer_trigger.auto_trigger_agent")
    def test_observe_batch_skips_when_should_trigger_false(self, mock_auto_trigger):
        """observe-batch结果为should_trigger=False时不应该触发"""
        from issuelab.observer_trigger import process_observer_results

        results = [{"issue_number": 1, "should_trigger": False, "reason": "Not ready"}]

        issue_data = {1: {"title": "Test", "body": "Body"}}

        triggered = process_observer_results(results, issue_data, auto_trigger=True)

        assert triggered == 0
        mock_auto_trigger.assert_not_called()

    @patch("issuelab.observer_trigger.auto_trigger_agent")
    def test_observe_batch_handles_multiple_issues(self, mock_auto_trigger):
        """observe-batch应该能处理多个issues的触发"""
        from issuelab.observer_trigger import process_observer_results

        mock_auto_trigger.return_value = True

        results = [
            {"issue_number": 1, "should_trigger": True, "agent": "moderator", "reason": "Reason 1"},
            {"issue_number": 2, "should_trigger": False, "reason": "Not ready"},
            {"issue_number": 3, "should_trigger": True, "agent": "gqy22", "reason": "Reason 3"},
        ]

        issue_data = {1: {"title": "Test1", "body": "Body1"}, 3: {"title": "Test3", "body": "Body3"}}

        triggered = process_observer_results(results, issue_data, auto_trigger=True)

        assert triggered == 2
        assert mock_auto_trigger.call_count == 2
