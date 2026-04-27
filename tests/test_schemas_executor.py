"""Tests for executor.py schema 简化"""

import pytest
from issuelab.agents import executor


class TestExecutorSchemaRemoval:
    """验证 executor.py 中的 schema 注入代码已被清理"""

    def test_no_schema_blocks_in_module(self):
        """executor 模块不应包含 _OUTPUT_SCHEMA_BLOCK_* 常量"""
        # 检查这些常量是否存在于模块中
        assert not hasattr(executor, "_OUTPUT_SCHEMA_BLOCK_MARKDOWN")
        assert not hasattr(executor, "_OUTPUT_SCHEMA_BLOCK_YAML")
        assert not hasattr(executor, "_OUTPUT_SCHEMA_BLOCK_HYBRID")

    def test_no_append_output_schema_function(self):
        """executor 模块不应包含 _append_output_schema 函数"""
        assert not hasattr(executor, "_append_output_schema")

    def test_no_output_templates_cache(self):
        """executor 模块不应包含 _GLOBAL_OUTPUT_TEMPLATES_CACHE"""
        assert not hasattr(executor, "_GLOBAL_OUTPUT_TEMPLATES_CACHE")
        assert not hasattr(executor, "_AGENT_OUTPUT_CONFIG_CACHE")

    def test_no_resolve_output_template_function(self):
        """executor 模块不应包含 _resolve_output_template 函数"""
        assert not hasattr(executor, "_resolve_output_template")
        assert not hasattr(executor, "_build_template_instruction")
        assert not hasattr(executor, "_get_output_preferences")
