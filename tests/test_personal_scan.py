"""测试个人Agent扫描功能"""

from unittest.mock import Mock, patch


class TestAnalyzeIssueInterest:
    """测试issue兴趣度分析"""

    def test_match_single_keyword(self):
        """匹配单个关键词"""
        from issuelab.personal_scan import analyze_issue_interest

        agent_config = {"interests": ["machine learning", "AI"]}

        result = analyze_issue_interest(
            agent_name="test",
            issue_number=1,
            issue_title="Machine Learning Paper",
            issue_body="This is about ML",
            agent_config=agent_config,
        )

        assert result["interested"] is True
        assert result["priority"] > 0
        assert "machine learning" in result["reason"].lower()

    def test_match_multiple_keywords(self):
        """匹配多个关键词"""
        from issuelab.personal_scan import analyze_issue_interest

        agent_config = {"interests": ["AI", "deep learning", "neural network"]}

        result = analyze_issue_interest(
            agent_name="test",
            issue_number=1,
            issue_title="Deep Learning and Neural Networks",
            issue_body="AI research",
            agent_config=agent_config,
        )

        assert result["interested"] is True
        assert result["priority"] >= 2  # 至少匹配2个关键词

    def test_no_match(self):
        """没有匹配的关键词"""
        from issuelab.personal_scan import analyze_issue_interest

        agent_config = {"interests": ["blockchain", "crypto"]}

        result = analyze_issue_interest(
            agent_name="test",
            issue_number=1,
            issue_title="Machine Learning Paper",
            issue_body="About neural networks",
            agent_config=agent_config,
        )

        assert result["interested"] is False
        assert result["priority"] == 0

    def test_case_insensitive(self):
        """不区分大小写"""
        from issuelab.personal_scan import analyze_issue_interest

        agent_config = {"interests": ["MachinE LeaRning"]}

        result = analyze_issue_interest(
            agent_name="test",
            issue_number=1,
            issue_title="machine learning paper",
            issue_body="MACHINE LEARNING",
            agent_config=agent_config,
        )

        assert result["interested"] is True


class TestSelectTopIssues:
    """测试选择top issues"""

    def test_select_top_by_priority(self):
        """按优先级选择top issues"""
        from issuelab.personal_scan import select_top_issues

        candidates = [
            {"issue_number": 1, "interested": True, "priority": 5},
            {"issue_number": 2, "interested": True, "priority": 8},
            {"issue_number": 3, "interested": True, "priority": 3},
        ]

        result = select_top_issues(candidates, max_count=2)

        assert len(result) == 2
        assert result[0]["issue_number"] == 2  # 最高优先级
        assert result[1]["issue_number"] == 1

    def test_only_select_interested(self):
        """只选择感兴趣的issues"""
        from issuelab.personal_scan import select_top_issues

        candidates = [
            {"issue_number": 1, "interested": True, "priority": 5},
            {"issue_number": 2, "interested": False, "priority": 10},
            {"issue_number": 3, "interested": True, "priority": 3},
        ]

        result = select_top_issues(candidates, max_count=5)

        assert len(result) == 2  # 只有2个interested=True
        assert all(c["interested"] for c in result)

    def test_respect_max_count(self):
        """尊重max_count限制"""
        from issuelab.personal_scan import select_top_issues

        candidates = [{"issue_number": i, "interested": True, "priority": i} for i in range(10)]

        result = select_top_issues(candidates, max_count=3)

        assert len(result) == 3


class TestGetIssueContent:
    """测试获取issue内容"""

    @patch("subprocess.run")
    def test_get_issue_content_success(self, mock_run):
        """成功获取issue内容"""
        from issuelab.personal_scan import get_issue_content

        mock_run.return_value = Mock(
            returncode=0, stdout='{"title": "Test", "body": "Content", "labels": [], "comments": []}'
        )

        result = get_issue_content(1, "owner/repo")

        assert result is not None
        assert result["title"] == "Test"
        assert result["body"] == "Content"

    @patch("subprocess.run")
    def test_get_issue_content_failure(self, mock_run):
        """获取issue内容失败"""
        from issuelab.personal_scan import get_issue_content

        mock_run.side_effect = Exception("API error")

        result = get_issue_content(1, "owner/repo")

        assert result is None


class TestCheckAlreadyCommented:
    """测试检查是否已评论"""

    @patch("subprocess.run")
    def test_already_commented(self, mock_run):
        """已经评论过"""
        from issuelab.personal_scan import check_already_commented

        mock_run.return_value = Mock(returncode=0, stdout="123456\n")

        result = check_already_commented(1, "owner/repo", "testuser")

        assert result is True

    @patch("subprocess.run")
    def test_not_commented(self, mock_run):
        """未评论过"""
        from issuelab.personal_scan import check_already_commented

        mock_run.return_value = Mock(returncode=0, stdout="")

        result = check_already_commented(1, "owner/repo", "testuser")

        assert result is False

    @patch("subprocess.run")
    def test_check_error_defaults_to_false(self, mock_run):
        """检查失败默认返回False"""
        from issuelab.personal_scan import check_already_commented

        mock_run.side_effect = Exception("API error")

        result = check_already_commented(1, "owner/repo", "testuser")

        assert result is False


class TestLlmSelectIssues:
    """测试 LLM 选择流程复用执行器封装"""

    @patch("issuelab.personal_scan.run_single_agent_text")
    def test_llm_select_issues_uses_executor_wrapper(self, mock_run):
        from issuelab.personal_scan import llm_select_issues_async

        async def fake_runner(prompt: str, agent_name: str | None = None):
            return (
                '{"selected_issues":[1],"selections":[{"issue_number":1,"priority":9,"reason":"ok"}],"reasoning":"r"}'
            )

        mock_run.side_effect = fake_runner

        result = __import__("asyncio").run(
            llm_select_issues_async(
                agent_config={"description": "test"},
                issues_data=[{"number": 1, "title": "t", "body": "b"}],
                max_replies=1,
                agent_name="tester",
            )
        )

        assert result["selected_issues"] == [1]
        assert mock_run.called
