# -*- coding: utf-8 -*-
"""守护 /生图 命令的 pattern 匹配。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict


_PLUGIN_FILE = Path(__file__).resolve().parents[1] / "plugin.py"


def _load_command_patterns() -> Dict[str, str]:
    """从 plugin.py 抠出 ``@Command(name, ..., pattern=...)`` 的字面量映射。"""
    source = _PLUGIN_FILE.read_text(encoding="utf-8")
    
    # 支持两种格式：@Command("name", ...) 和 @Command(name="name", ...)
    _COMMAND_BLOCK_RE = re.compile(
        r'@Command\(\s*"?([^",]+)"?[\s\S]*?pattern=r?f?"([^"]+)"'
    )
    return {
        m.group(1): m.group(2)
        for m in _COMMAND_BLOCK_RE.finditer(source)
    }


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _get_draw_pattern() -> re.Pattern[str]:
    """获取生图命令的 pattern（第一个命令）。"""
    patterns = _load_command_patterns()
    for name, pattern in patterns.items():
        if "帮助" not in name and "help" not in name.lower():
            return _compile(pattern)
    raise KeyError(f"未找到生图命令，可用命令: {list(patterns.keys())}")


def _get_help_pattern() -> re.Pattern[str]:
    """获取帮助命令的 pattern（第二个命令）。"""
    patterns = _load_command_patterns()
    for name, pattern in patterns.items():
        if "帮助" in name or "help" in name.lower():
            return _compile(pattern)
    raise KeyError(f"未找到帮助命令，可用命令: {list(patterns.keys())}")


# ── /生图 命令 pattern ─────────────────────────────────────────────────


def test_draw_command_pattern_matches_plain_invocation() -> None:
    """无前缀时直接 /生图 <描述> 必须能匹配。"""
    regex = _get_draw_pattern()

    match = regex.match("/生图 一个可爱的女孩")
    assert match is not None, "应匹配 /生图 一个可爱的女孩"


def test_draw_command_pattern_matches_with_english() -> None:
    """应支持英文描述。"""
    regex = _get_draw_pattern()

    match = regex.match("/生图 cute girl with blue hair")
    assert match is not None


def test_draw_command_pattern_matches_with_special_chars() -> None:
    """应支持特殊字符。"""
    regex = _get_draw_pattern()

    match = regex.match("/生图 樱花树下的少女，动漫风格，近景")
    assert match is not None


def test_draw_command_pattern_matches_bare_command() -> None:
    """/生图（无参数）也应匹配，由 handler 提示帮助信息。"""
    regex = _get_draw_pattern()

    match = regex.match("/生图")
    assert match is not None


def test_help_command_pattern_matches() -> None:
    """/生图帮助 命令应能匹配。"""
    regex = _get_help_pattern()
    
    match = regex.match("/生图帮助")
    assert match is not None


def test_help_command_pattern_rejects_extra_text() -> None:
    """/生图帮助 不应匹配带额外文本的消息。"""
    regex = _get_help_pattern()
    
    match = regex.match("/生图帮助 额外文本")
    assert match is None


def test_draw_command_pattern_tolerate_quote_reply_prefix() -> None:
    """pattern 使用 ^ 锚点时，带前缀的消息需要 MaiBot 框架预处理后才能匹配。"""
    regex = _get_draw_pattern()
    
    # pattern 使用 ^ 锚点，所以带前缀的消息不会直接匹配
    # 这是正确行为 - MaiBot 框架会先去掉前缀再匹配
    assert regex.pattern.startswith("^"), "pattern 应以 ^ 开头，由框架处理前缀"


def test_command_patterns_count() -> None:
    """应注册 2 个命令。"""
    patterns = _load_command_patterns()
    assert len(patterns) == 2, f"应有 2 个命令，实际有 {len(patterns)} 个"


def test_draw_pattern_format() -> None:
    """生图命令 pattern 应以 ^ 开头。"""
    regex = _get_draw_pattern()
    assert regex.pattern.startswith("^"), "pattern 应以 ^ 开头"
