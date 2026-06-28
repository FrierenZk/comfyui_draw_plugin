# -*- coding: utf-8 -*-
"""测试 sdk_runtime 和 core.generation 模块的纯函数。"""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Mock MaiBot SDK
dummy_maibot_sdk = types.ModuleType("maibot_sdk")


class _DummyMaiBotPlugin:
    pass


dummy_maibot_sdk.MaiBotPlugin = _DummyMaiBotPlugin
dummy_maibot_sdk.Command = lambda *args, **kwargs: lambda func: func
dummy_maibot_sdk.Tool = lambda *args, **kwargs: lambda func: func
dummy_maibot_sdk.HookHandler = lambda *args, **kwargs: lambda func: func
sys.modules["maibot_sdk"] = dummy_maibot_sdk

dummy_llm_service = types.ModuleType("src.services.llm_service")
sys.modules["src.services"] = types.ModuleType("src.services")
sys.modules["src.services.llm_service"] = dummy_llm_service

from comfyui_draw_plugin.sdk_runtime import ComfyUIDrawInvocation


def _create_mock_plugin(**config_kwargs):
    """创建 mock 插件对象，包含 ctx.logger 和 get_config_value。"""
    logger = types.SimpleNamespace(
        info=lambda *args: None,
        error=lambda *args: None,
        warning=lambda *args: None,
    )
    ctx = types.SimpleNamespace(logger=logger)

    def get_config_value(section, key, default=None):
        return config_kwargs.get(f"{section}.{key}", default)

    return types.SimpleNamespace(ctx=ctx, get_config_value=get_config_value)


def _get_generator():
    """获取 ComfyUIDrawGenerator 实例用于测试。"""
    plugin = _create_mock_plugin()
    invocation = ComfyUIDrawInvocation(plugin)
    return invocation._generator


# ==================== _parse_llm_response 测试 ====================


def test_parse_llm_response_positive_negative_format() -> None:
    """应正确解析 JSON 数组格式。"""
    gen = _get_generator()

    response = '{"positive": ["masterpiece", "best quality", "1girl", "smile"], "negative": ["low quality", "blurry", "deformed"]}'

    positive, negative = gen._parse_llm_response(response)

    assert "masterpiece" in positive
    assert "1girl" in positive
    assert "low quality" in negative
    assert "blurry" in negative


def test_parse_llm_response_json_string_format() -> None:
    """应兼容 JSON 字符串格式（字符串值不拆分，保留为单个标签）。"""
    gen = _get_generator()

    response = '{"positive": "masterpiece, best quality, 1girl", "negative": "low quality, blurry"}'

    positive, negative = gen._parse_llm_response(response)

    # 字符串值不被逗号拆分，保留为一个整体
    assert len(positive) == 1
    assert "masterpiece" in positive[0]
    assert "low quality" in negative[0]


def test_parse_llm_response_legacy_format() -> None:
    """应兼容旧的 POSITIVE/NEGATIVE 格式（按行 fallback，不剥离前缀）。"""
    gen = _get_generator()

    response = "POSITIVE: masterpiece, best quality, 1girl, smile\nNEGATIVE: low quality, blurry, deformed"

    positive, negative = gen._parse_llm_response(response)

    # 回退到按行解析，POSITIVE:/NEGATIVE: 前缀保留在第一个标签中
    assert "POSITIVE: masterpiece" in positive
    assert "NEGATIVE: low quality" in negative


def test_parse_llm_response_fallback_to_lines() -> None:
    """无格式时应回退到按行解析。"""
    gen = _get_generator()

    response = "masterpiece, best quality, 1girl, smile\nlow quality, blurry, deformed"

    positive, negative = gen._parse_llm_response(response)

    assert "masterpiece" in positive
    assert "low quality" in negative


# ==================== _ensure_quality_tags 测试 ====================


def test_ensure_quality_tags_adds_missing_tags() -> None:
    """应添加缺失的质量词。"""
    plugin = _create_mock_plugin()
    invocation = ComfyUIDrawInvocation(plugin)
    
    tags = ["1girl", "smile", "beautiful face"]
    result = invocation._ensure_quality_tags(tags)
    
    assert "masterpiece" in result
    assert "best quality" in result
    assert "ultra-detailed" in result
    assert result.index("masterpiece") < result.index("1girl")


def test_ensure_quality_tags_preserves_existing_tags() -> None:
    """不应重复添加已存在的质量词。"""
    plugin = _create_mock_plugin()
    invocation = ComfyUIDrawInvocation(plugin)
    
    tags = ["masterpiece", "best quality", "ultra-detailed", "1girl", "smile"]
    result = invocation._ensure_quality_tags(tags)
    
    assert result.count("masterpiece") == 1
    assert result.count("best quality") == 1
    assert result.count("ultra-detailed") == 1


# ==================== _ensure_negative_tags 测试 ====================


def test_ensure_negative_tags_for_character() -> None:
    """人物类应添加完整的负面标签。"""
    plugin = _create_mock_plugin()
    invocation = ComfyUIDrawInvocation(plugin)
    
    positive = ["1girl", "smile"]
    negative = ["low quality", "blurry"]
    result = invocation._ensure_negative_tags(positive, negative)
    
    assert "bad anatomy" in result
    assert "bad hands" in result
    assert "missing fingers" in result


def test_ensure_negative_tags_for_non_character() -> None:
    """非人物类应添加基础负面标签。"""
    plugin = _create_mock_plugin()
    invocation = ComfyUIDrawInvocation(plugin)
    
    positive = ["cherry blossom tree", "spring"]
    negative = ["low quality", "blurry"]
    result = invocation._ensure_negative_tags(positive, negative)
    
    assert "worst quality" in result
    assert "low quality" in result
    assert "deformed" in result
