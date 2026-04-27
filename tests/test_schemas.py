"""Tests for SchemaRegistry - 结构化输出 Schema 管理"""

import pytest
from issuelab.schemas import (
    SchemaRegistry,
    StandardOutput,
    ResearcherStageOutput,
    ConfidenceLevel,
)


class TestSchemaRegistry:
    """SchemaRegistry 核心功能测试"""

    def test_get_model_standard(self):
        """应该能获取 standard schema model"""
        model = SchemaRegistry.get_model("standard")
        assert model is StandardOutput

    def test_get_model_researcher(self):
        """应该能获取 researcher schema model"""
        model = SchemaRegistry.get_model("researcher")
        assert model is ResearcherStageOutput

    def test_get_model_unknown_raises(self):
        """未知 schema name 应该抛出 KeyError"""
        with pytest.raises(KeyError) as exc_info:
            SchemaRegistry.get_model("nonexistent")
        assert "Unknown schema" in str(exc_info.value)

    def test_get_sdk_format_returns_dict(self):
        """get_sdk_format 应该返回 SDK 格式的 dict"""
        result = SchemaRegistry.get_sdk_format("standard")
        assert isinstance(result, dict)
        assert result["type"] == "json_schema"
        assert "schema" in result

    def test_get_sdk_format_has_required_fields(self):
        """SDK format 应该包含必要字段"""
        result = SchemaRegistry.get_sdk_format("standard")
        schema = result["schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "summary" in schema["properties"]
        assert "findings" in schema["properties"]
        assert "recommendations" in schema["properties"]

    def test_parse_valid_data(self):
        """parse 应该能正确解析有效数据"""
        data = {
            "summary": "测试结论",
            "findings": ["发现1", "发现2"],
            "recommendations": ["建议1"],
            "confidence": "high"
        }
        result = SchemaRegistry.parse("standard", data)
        assert isinstance(result, StandardOutput)
        assert result.summary == "测试结论"
        assert result.findings == ["发现1", "发现2"]
        assert result.confidence == ConfidenceLevel.HIGH

    def test_parse_with_defaults(self):
        """parse 应该支持默认值"""
        data = {
            "summary": "简单结论",
            "findings": ["发现1"],
        }
        result = SchemaRegistry.parse("standard", data)
        assert result.confidence == ConfidenceLevel.MEDIUM  # 默认值


class TestResearcherStageOutput:
    """Researcher 阶段 Schema 测试"""

    def test_researcher_schema_validation(self):
        """Researcher schema 应该验证 evidence 非空"""
        data = {
            "summary": "研究完成",
            "evidence": [
                {
                    "claim": "测试声明",
                    "source": "测试来源",
                    "url": "https://example.com",
                    "confidence": "high"
                }
            ],
            "open_questions": [],
            "confidence": "medium"
        }
        result = SchemaRegistry.parse("researcher", data)
        assert isinstance(result, ResearcherStageOutput)
        assert len(result.evidence) == 1
        assert result.evidence[0].url == "https://example.com"

    def test_researcher_schema_missing_evidence_fails(self):
        """Researcher schema 缺少 evidence 应该失败"""
        data = {
            "summary": "研究完成",
            "evidence": [],  # 空列表应该失败
            "confidence": "medium"
        }
        with pytest.raises(Exception):  # Pydantic 验证错误
            SchemaRegistry.parse("researcher", data)


class TestConfidenceLevel:
    """ConfidenceLevel 枚举测试"""

    def test_confidence_values(self):
        """ConfidenceLevel 应该有正确的值"""
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.HIGH.value == "high"

    def test_confidence_is_str_enum(self):
        """ConfidenceLevel 应该是字符串枚举"""
        assert isinstance(ConfidenceLevel.HIGH, str)
        assert ConfidenceLevel.HIGH == "high"
