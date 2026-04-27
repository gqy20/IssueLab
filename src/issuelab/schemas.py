"""结构化输出 Schema 注册表

集中管理所有 agent 的输出 schema，支持：
- 标准输出格式
- 多阶段专用格式
- SDK JSON Schema 转换
- Pydantic 模型验证
"""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    """置信度级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================
# 标准输出 Schema
# ============================================================

class StandardOutput(BaseModel):
    """标准输出格式"""
    summary: str = Field(description="1-3 句结论")
    findings: list[str] = Field(default_factory=list, description="2-5 条要点")
    recommendations: list[str] = Field(default_factory=list, description="1-5 条可执行动作")
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM)


# ============================================================
# 论文推荐 Schema
# ============================================================

class PaperRecommendationItem(BaseModel):
    """论文推荐项"""
    index: int = Field(description="论文编号（对应候选列表中的编号）")
    title: str = Field(default="", description="论文标题")
    reason: str = Field(default="", description="推荐理由")
    summary: str = Field(default="", description="论文摘要或亮点")


class ArxivObserverOutput(BaseModel):
    """Arxiv Observer 输出"""
    summary: str = Field(description="一句话总结本次筛选")
    recommended: list[PaperRecommendationItem] = Field(description="推荐论文列表")


class PubmedRecommendationItem(PaperRecommendationItem):
    """PubMed 推荐项（扩展字段）"""
    pmid: str = Field(default="", description="PMID")
    doi: str = Field(default="", description="DOI")
    url: str = Field(default="", description="文献链接")
    journal: str = Field(default="", description="期刊名称")
    pubdate: str = Field(default="", description="发表日期")
    authors: str = Field(default="", description="作者列表")


class PubmedObserverOutput(BaseModel):
    """PubMed Observer 输出"""
    analysis: str = Field(description="本次筛选的分析说明")
    recommended: list[PubmedRecommendationItem] = Field(description="推荐文献列表")


# ============================================================
# 多阶段 Schema
# ============================================================

class EvidenceItem(BaseModel):
    """证据项"""
    claim: str
    source: str
    url: str
    confidence: ConfidenceLevel


class ResearcherStageOutput(BaseModel):
    """Researcher 阶段输出"""
    summary: str
    evidence: list[EvidenceItem] = Field(min_length=1)
    open_questions: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel


class AnalystCandidate(BaseModel):
    """Analyst 阶段的候选方案"""
    id: str
    summary: str
    findings: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class AnalystStageOutput(BaseModel):
    """Analyst 阶段输出"""
    summary: str
    candidates: list[AnalystCandidate] = Field(min_length=1)
    confidence: ConfidenceLevel


class CriticismItem(BaseModel):
    """批评项"""
    candidate_id: str
    issues: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class CriticStageOutput(BaseModel):
    """Critic 阶段输出"""
    summary: str
    criticisms: list[CriticismItem] = Field(default_factory=list)
    confidence: ConfidenceLevel


class VerifiedSource(BaseModel):
    """已验证来源"""
    url: str
    status: str = Field(pattern="^(verified|partially_verified|unverified)$")
    supports: list[str] = Field(default_factory=list)


class VerifierStageOutput(BaseModel):
    """Verifier 阶段输出"""
    summary: str
    verified_sources: list[VerifiedSource] = Field(default_factory=list)
    verification_gaps: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel


class JudgeStageOutput(BaseModel):
    """Judge 阶段输出"""
    summary: str
    decision: str
    rationale: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


# ============================================================
# Schema 注册表
# ============================================================

class SchemaRegistry:
    """集中管理所有 schema，支持 SDK 格式转换"""

    _schemas: ClassVar[dict[str, type[BaseModel]]] = {
        "standard": StandardOutput,
        "researcher": ResearcherStageOutput,
        "analyst": AnalystStageOutput,
        "critic": CriticStageOutput,
        "verifier": VerifierStageOutput,
        "judge": JudgeStageOutput,
        "arxiv_observer": ArxivObserverOutput,
        "pubmed_observer": PubmedObserverOutput,
    }

    @classmethod
    def get_model(cls, name: str) -> type[BaseModel]:
        """获取 schema model 类"""
        if name not in cls._schemas:
            available = list(cls._schemas.keys())
            raise KeyError(f"Unknown schema: {name}. Available: {available}")
        return cls._schemas[name]

    @classmethod
    def get_sdk_format(cls, name: str) -> dict[str, Any]:
        """转换为 SDK output_format 格式"""
        model = cls.get_model(name)
        return {
            "type": "json_schema",
            "schema": model.model_json_schema()
        }

    @classmethod
    def parse(cls, name: str, data: dict) -> BaseModel:
        """解析并验证数据"""
        model = cls.get_model(name)
        return model.model_validate(data)
