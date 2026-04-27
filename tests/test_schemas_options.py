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
