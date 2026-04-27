"""Tests for SchemaRegistry 与 options.py 集成"""

import pytest
from issuelab.agents.options import create_agent_options, clear_agent_options_cache
from issuelab.schemas import SchemaRegistry


class TestSchemaIntegration:
    """SchemaRegistry 与 Agent Options 集成测试"""

    def setup_method(self):
        """每个测试前清除缓存"""
        clear_agent_options_cache()

    def test_gqy20_agent_has_output_format(self):
        """gqy20 agent 应该配置了 output_format"""
        options = create_agent_options(agent_name="gqy20")
        assert hasattr(options, "output_format")
        assert options.output_format is not None
        assert options.output_format["type"] == "json_schema"
        assert "schema" in options.output_format

    def test_standard_agent_has_output_format(self):
        """标准 agent 应该配置了 output_format"""
        options = create_agent_options(agent_name="summarizer")
        assert hasattr(options, "output_format")
        assert options.output_format is not None
        assert options.output_format["type"] == "json_schema"

    def test_output_format_schema_is_valid(self):
        """output_format 的 schema 应该是有效的"""
        options = create_agent_options(agent_name="gqy20")
        schema = options.output_format["schema"]
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_output_format_matches_registry(self):
        """options.output_format 应该与 SchemaRegistry.get_sdk_format 一致"""
        options = create_agent_options(agent_name="gqy20")
        expected = SchemaRegistry.get_sdk_format("standard")
        assert options.output_format == expected

    def test_schema_name_defaults_to_standard(self):
        """未指定 schema_name 时应默认使用 standard"""
        options = create_agent_options(agent_name="gqy20")
        expected = SchemaRegistry.get_sdk_format("standard")
        assert options.output_format == expected

    def test_schema_name_researcher(self):
        """指定 schema_name='researcher' 时应使用 ResearcherStageOutput schema"""
        options = create_agent_options(agent_name="gqy20", schema_name="researcher")
        expected = SchemaRegistry.get_sdk_format("researcher")
        assert options.output_format == expected
        # 验证 schema title
        assert options.output_format["schema"]["title"] == "ResearcherStageOutput"

    def test_schema_name_judge(self):
        """指定 schema_name='judge' 时应使用 JudgeStageOutput schema"""
        options = create_agent_options(agent_name="gqy20", schema_name="judge")
        expected = SchemaRegistry.get_sdk_format("judge")
        assert options.output_format == expected
        assert options.output_format["schema"]["title"] == "JudgeStageOutput"

    def test_schema_name_critic(self):
        """指定 schema_name='critic' 时应使用 CriticStageOutput schema"""
        options = create_agent_options(agent_name="gqy20", schema_name="critic")
        expected = SchemaRegistry.get_sdk_format("critic")
        assert options.output_format == expected
        assert options.output_format["schema"]["title"] == "CriticStageOutput"

    def test_schema_name_verifier(self):
        """指定 schema_name='verifier' 时应使用 VerifierStageOutput schema"""
        options = create_agent_options(agent_name="gqy20", schema_name="verifier")
        expected = SchemaRegistry.get_sdk_format("verifier")
        assert options.output_format == expected
        assert options.output_format["schema"]["title"] == "VerifierStageOutput"
