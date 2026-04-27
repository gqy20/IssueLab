"""Tests: observer agents consume structured_output instead of YAML parsing.

TDD Red Phase: 这些测试描述了期望行为（structured_output 优先，YAML fallback）。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestArxivObserverStructuredOutput:
    """ArxivObserver 应该优先使用 structured_output"""

    def setup_method(self):
        from issuelab.agents.options import clear_agent_options_cache
        clear_agent_options_cache()

    @pytest.mark.asyncio
    async def test_run_observer_for_papers_uses_structured_output(self):
        """structured_output 存在时，应直接使用而非 YAML 解析"""
        from issuelab.agents import observer as observer_module
        from issuelab.schemas import ArxivObserverOutput, PaperRecommendationItem

        # 构造 mock structured_output
        structured_data = {
            "summary": "推荐2篇论文",
            "recommended": [
                {"index": 0, "title": "Paper A", "reason": "高度相关", "summary": "摘要A"},
                {"index": 2, "title": "Paper C", "reason": "创新性强", "summary": "摘要C"},
            ],
        }

        mock_result = {
            "response": "这是文本响应（应被忽略）",
            "cost_usd": 0.01,
            "num_turns": 1,
            "structured_output": structured_data,
        }

        papers = [
            {"id": "a1", "title": "Paper A", "summary": "摘要A", "url": "http://arxiv.org/a1", "pdf_url": "", "authors": "", "published": "", "category": ""},
            {"id": "a2", "title": "Paper B", "summary": "摘要B", "url": "http://arxiv.org/a2", "pdf_url": "", "authors": "", "published": "", "category": ""},
            {"id": "a3", "title": "Paper C", "summary": "摘要C", "url": "http://arxiv.org/a3", "pdf_url": "", "authors": "", "published": "", "category": ""},
        ]

        async def fake_run_single_agent(prompt, agent_name, *, stage_name=None, schema_name=None):
            return mock_result

        def fake_discover_agents():
            return {
                "arxiv_observer": {
                    "description": "Arxiv Observer",
                    "prompt": "Test prompt\n__PAPERS_CONTEXT__",
                    "trigger_conditions": [],
                }
            }

        with patch.object(observer_module, "run_single_agent", side_effect=fake_run_single_agent):
            with patch.object(observer_module, "discover_agents", side_effect=fake_discover_agents):
                result = await observer_module.run_observer_for_papers(papers, return_result=True)

        recommended_papers, result_dict = result
        # 验证推荐结果
        assert len(recommended_papers) == 2
        assert recommended_papers[0]["id"] == "a1"
        assert recommended_papers[0]["reason"] == "高度相关"
        assert recommended_papers[1]["id"] == "a3"
        assert recommended_papers[1]["reason"] == "创新性强"
        # 验证 result dict 包含 structured_output
        assert result_dict.get("structured_output") == structured_data

    @pytest.mark.asyncio
    async def test_run_observer_for_papers_fallback_when_no_structured_output(self):
        """structured_output 为 None 时，应 fallback 到 YAML 文本解析"""
        from issuelab.agents import observer as observer_module

        yaml_text = """```yaml
summary: "推荐1篇"
recommended:
  - index: 1
    title: "Paper B"
    reason: "相关"
    summary: "摘要"
```"""

        mock_result = {
            "response": yaml_text,
            "cost_usd": 0.01,
            "num_turns": 1,
            "structured_output": None,
        }

        papers = [
            {"id": "a1", "title": "Paper A", "summary": "摘要A", "url": "http://arxiv.org/a1", "pdf_url": "", "authors": "", "published": "", "category": ""},
            {"id": "a2", "title": "Paper B", "summary": "摘要B", "url": "http://arxiv.org/a2", "pdf_url": "", "authors": "", "published": "", "category": ""},
        ]

        async def fake_run_single_agent(prompt, agent_name, *, stage_name=None, schema_name=None):
            return mock_result

        def fake_discover_agents():
            return {
                "arxiv_observer": {
                    "description": "Arxiv Observer",
                    "prompt": "Test prompt\n__PAPERS_CONTEXT__",
                    "trigger_conditions": [],
                }
            }

        with patch.object(observer_module, "run_single_agent", side_effect=fake_run_single_agent):
            with patch.object(observer_module, "discover_agents", side_effect=fake_discover_agents):
                result = await observer_module.run_observer_for_papers(papers, return_result=True)

        recommended_papers, result_dict = result
        assert len(recommended_papers) == 1
        assert recommended_papers[0]["id"] == "a2"


class TestPubmedObserverStructuredOutput:
    """PubmedObserver 应该优先使用 structured_output"""

    def setup_method(self):
        from issuelab.agents.options import clear_agent_options_cache
        clear_agent_options_cache()

    @pytest.mark.asyncio
    async def test_run_pubmed_observer_for_papers_uses_structured_output(self):
        """structured_output 存在时，应直接使用而非 YAML 解析"""
        from issuelab.agents import observer as observer_module
        from issuelab.schemas import PubmedObserverOutput

        structured_data = {
            "analysis": "筛选出2篇高相关性文献",
            "recommended": [
                {
                    "index": 0,
                    "title": "Paper A",
                    "reason": "高度相关",
                    "summary": "摘要A",
                    "pmid": "12345",
                    "doi": "10.1234/test",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/12345",
                    "journal": "Nature",
                    "authors": "Smith et al.",
                },
            ],
        }

        mock_result = {
            "response": "这是文本响应（应被忽略）",
            "cost_usd": 0.01,
            "num_turns": 1,
            "structured_output": structured_data,
        }

        papers = [
            {"pmid": "12345", "title": "Paper A", "reason": "高度相关", "summary": "摘要A"},
            {"pmid": "67890", "title": "Paper B", "reason": "不相关", "summary": "摘要B"},
        ]

        async def fake_run_single_agent(prompt, agent_name, *, stage_name=None, schema_name=None):
            return mock_result

        def fake_discover_agents():
            return {
                "pubmed_observer": {
                    "description": "Pubmed Observer",
                    "prompt": "Test prompt\n__PAPERS_CONTEXT__",
                    "trigger_conditions": [],
                }
            }

        with patch.object(observer_module, "run_single_agent", side_effect=fake_run_single_agent):
            with patch.object(observer_module, "discover_agents", side_effect=fake_discover_agents):
                result = await observer_module.run_pubmed_observer_for_papers(papers, "test query", return_result=True)

        recommended_papers, result_dict = result
        assert len(recommended_papers) == 1
        assert recommended_papers[0]["pmid"] == "12345"
        assert recommended_papers[0]["reason"] == "高度相关"
        assert recommended_papers[0]["journal"] == "Nature"
        assert result_dict.get("structured_output") == structured_data

    @pytest.mark.asyncio
    async def test_run_pubmed_observer_for_papers_fallback_when_no_structured_output(self):
        """structured_output 为 None 时，应 fallback 到 YAML 文本解析"""
        from issuelab.agents import observer as observer_module

        yaml_text = """```yaml
analysis: "筛选出1篇"
recommended:
  - index: 0
    title: "Paper A"
    reason: "相关"
    summary: "摘要"
    pmid: "12345"
    doi: "10.1234/test"
    journal: "Cell"
    authors: "Doe et al."
```"""

        mock_result = {
            "response": yaml_text,
            "cost_usd": 0.01,
            "num_turns": 1,
            "structured_output": None,
        }

        papers = [
            {"pmid": "12345", "title": "Paper A", "reason": "相关", "summary": "摘要"},
        ]

        async def fake_run_single_agent(prompt, agent_name, *, stage_name=None, schema_name=None):
            return mock_result

        def fake_discover_agents():
            return {
                "pubmed_observer": {
                    "description": "Pubmed Observer",
                    "prompt": "Test prompt\n__PAPERS_CONTEXT__",
                    "trigger_conditions": [],
                }
            }

        with patch.object(observer_module, "run_single_agent", side_effect=fake_run_single_agent):
            with patch.object(observer_module, "discover_agents", side_effect=fake_discover_agents):
                result = await observer_module.run_pubmed_observer_for_papers(papers, "test query", return_result=True)

        recommended_papers, result_dict = result
        assert len(recommended_papers) == 1
        assert recommended_papers[0]["pmid"] == "12345"
