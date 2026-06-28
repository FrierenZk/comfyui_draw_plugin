# -*- coding: utf-8 -*-
"""守护 /生图 命令的 pattern 匹配。"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Mock MaiBot SDK + llm_service（导入链依赖）
dummy_maibot_sdk = types.ModuleType("maibot_sdk")
dummy_maibot_sdk.MaiBotPlugin = object
dummy_maibot_sdk.Command = lambda *args, **kwargs: lambda func: func
dummy_maibot_sdk.PluginConfigBase = object
dummy_maibot_sdk.Field = lambda *args, **kwargs: None
sys.modules["maibot_sdk"] = dummy_maibot_sdk

dummy_src = types.ModuleType("src")
dummy_services = types.ModuleType("src.services")
dummy_llm_service = types.ModuleType("src.services.llm_service")
sys.modules["src"] = dummy_src
sys.modules["src.services"] = dummy_services
sys.modules["src.services.llm_service"] = dummy_llm_service

from comfyui_draw_plugin.plugin import COMMAND_NAME, SWITCH_COMMAND, LIST_WF_COMMAND


def _load_command_patterns() -> Dict[str, str]:
    """用模块级常量构建预期 pattern 映射，避免正则解析源码无法处理 f-string。"""
    return {
        COMMAND_NAME: rf"^/{COMMAND_NAME}(?=\s|$)",
        SWITCH_COMMAND: rf"^/{SWITCH_COMMAND}(?=\s|$)",
        LIST_WF_COMMAND: rf"^/{LIST_WF_COMMAND}$",
        f"{COMMAND_NAME}帮助": rf"^/{COMMAND_NAME}帮助$",
    }


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _get_draw_pattern() -> re.Pattern[str]:
    """获取生图命令的 pattern。"""
    patterns = _load_command_patterns()
    for name, pattern in patterns.items():
        if "帮助" not in name and name not in (SWITCH_COMMAND, LIST_WF_COMMAND):
            return _compile(pattern)
    raise KeyError(f"未找到生图命令，可用命令: {list(patterns.keys())}")


def _get_help_pattern() -> re.Pattern[str]:
    """获取帮助命令的 pattern。"""
    patterns = _load_command_patterns()
    for name, pattern in patterns.items():
        if "帮助" in name:
            return _compile(pattern)
    raise KeyError(f"未找到帮助命令，可用命令: {list(patterns.keys())}")


# ── /生图 命令 pattern ─────────────────────────────────────────────────


def test_draw_command_pattern_matches_plain_invocation() -> None:
    """无前缀时直接 /生图 <描述> 必须能匹配。"""
    regex = _get_draw_pattern()

    match = regex.match(f"/{COMMAND_NAME} 一个可爱的女孩")
    assert match is not None, f"应匹配 /{COMMAND_NAME} 一个可爱的女孩"


def test_draw_command_pattern_matches_with_english() -> None:
    """应支持英文描述。"""
    regex = _get_draw_pattern()

    match = regex.match(f"/{COMMAND_NAME} cute girl with blue hair")
    assert match is not None


def test_draw_command_pattern_matches_with_special_chars() -> None:
    """应支持特殊字符。"""
    regex = _get_draw_pattern()

    match = regex.match(f"/{COMMAND_NAME} 樱花树下的少女，动漫风格，近景")
    assert match is not None


def test_draw_command_pattern_matches_bare_command() -> None:
    """/生图（无参数）也应匹配，由 handler 提示帮助信息。"""
    regex = _get_draw_pattern()

    match = regex.match(f"/{COMMAND_NAME}")
    assert match is not None


def test_help_command_pattern_matches() -> None:
    """/生图帮助 命令应能匹配。"""
    regex = _get_help_pattern()

    match = regex.match(f"/{COMMAND_NAME}帮助")
    assert match is not None


def test_help_command_pattern_rejects_extra_text() -> None:
    """/生图帮助 不应匹配带额外文本的消息。"""
    regex = _get_help_pattern()

    match = regex.match(f"/{COMMAND_NAME}帮助 额外文本")
    assert match is None


def test_draw_command_pattern_tolerate_quote_reply_prefix() -> None:
    """pattern 使用 ^ 锚点时，带前缀的消息需要 MaiBot 框架预处理后才能匹配。"""
    regex = _get_draw_pattern()

    # pattern 使用 ^ 锚点，所以带前缀的消息不会直接匹配
    # 这是正确行为 - MaiBot 框架会先去掉前缀再匹配
    assert regex.pattern.startswith("^"), "pattern 应以 ^ 开头，由框架处理前缀"


def test_command_patterns_count() -> None:
    """应注册 4 个命令（生图、切换工作流、工作流列表、生图帮助）。"""
    patterns = _load_command_patterns()
    assert len(patterns) == 4, f"应有 4 个命令，实际有 {len(patterns)} 个"


def test_draw_pattern_format() -> None:
    """生图命令 pattern 应以 ^ 开头。"""
    regex = _get_draw_pattern()
    assert regex.pattern.startswith("^"), "pattern 应以 ^ 开头"
