"""配置管理 - 统一的环境变量和配置管理"""

import os
from pathlib import Path


class Config:
    """全局配置管理器"""

    # Anthropic API 配置
    @staticmethod
    def get_anthropic_api_key() -> str:
        """获取 Anthropic API Key

        优先级: ANTHROPIC_API_TOKEN > ANTHROPIC_AUTH_TOKEN
        """
        return os.environ.get("ANTHROPIC_API_TOKEN") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")

    @staticmethod
    def get_anthropic_base_url() -> str:
        """获取 Anthropic API Base URL"""
        return os.environ.get("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    @staticmethod
    def get_anthropic_model() -> str:
        """获取 Anthropic Model"""
        return os.environ.get("ANTHROPIC_MODEL", "MiniMax-M2.1")

    @staticmethod
    def get_anthropic_env() -> dict:
        """获取完整的 Anthropic 环境变量字典

        Returns:
            包含所有 Anthropic 配置的环境变量字典
        """
        env = {}

        api_key = Config.get_anthropic_api_key()
        if api_key:
            # 统一使用 ANTHROPIC_API_TOKEN
            env["ANTHROPIC_API_TOKEN"] = api_key

        base_url = Config.get_anthropic_base_url()
        if base_url:
            env["ANTHROPIC_BASE_URL"] = base_url

        model = Config.get_anthropic_model()
        if model:
            env["ANTHROPIC_MODEL"] = model

        return env

    # GitHub 配置
    @staticmethod
    def get_github_token() -> str:
        """获取 GitHub Token

        优先级: GH_TOKEN > GITHUB_TOKEN
        """
        return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")

    @staticmethod
    def prepare_github_env() -> dict:
        """准备带有 GitHub Token 的环境变量字典

        Returns:
            环境变量字典，确保包含 GH_TOKEN
        """
        env = os.environ.copy()
        token = Config.get_github_token()
        if token:
            env["GH_TOKEN"] = token
        return env

    # MCP 配置
    @staticmethod
    def get_arxiv_storage_path() -> str:
        """获取 ArXiv MCP 存储路径"""
        default_path = str(Path.home() / ".arxiv-mcp-server" / "papers")
        return os.environ.get("ARXIV_STORAGE_PATH", default_path)

    @staticmethod
    def is_arxiv_mcp_enabled() -> bool:
        """检查是否启用 ArXiv MCP"""
        return os.environ.get("ENABLE_ARXIV_MCP", "true").lower() == "true"

    @staticmethod
    def is_github_mcp_enabled() -> bool:
        """检查是否启用 GitHub MCP"""
        return os.environ.get("ENABLE_GITHUB_MCP", "true").lower() == "true"

    # 日志配置
    @staticmethod
    def get_log_level() -> str:
        """获取日志级别"""
        return os.environ.get("LOG_LEVEL", "INFO")

    @staticmethod
    def get_log_file() -> Path | None:
        """获取日志文件路径"""
        log_file = os.environ.get("LOG_FILE")
        return Path(log_file) if log_file else None


# 便捷函数（向后兼容）
def get_github_token() -> str:
    """便捷函数：获取 GitHub Token"""
    return Config.get_github_token()


def prepare_github_env() -> dict:
    """便捷函数：准备 GitHub 环境变量"""
    return Config.prepare_github_env()


def get_anthropic_env() -> dict:
    """便捷函数：获取 Anthropic 环境变量"""
    return Config.get_anthropic_env()
