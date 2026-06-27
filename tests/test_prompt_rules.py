# -*- coding: utf-8 -*-
"""测试提示词规则模块。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from comfyui_draw_plugin.core.prompt_rules import (
    CHARACTER_EXTRACTION_TEMPLATE,
    SCENE_COMPOSITION_TEMPLATE,
    CHARACTER_DETAIL_TEMPLATE,
    DEFAULT_NEGATIVE_PROMPT,
    QUALITY_TAGS,
    CHARACTER_NEGATIVE_TAGS,
    NON_CHARACTER_NEGATIVE_TAGS,
    CHARACTER_KEYWORDS,
    is_character_prompt,
    get_default_negative_prompt,
)


# ==================== 模板测试 ====================


def test_character_extraction_template_contains_placeholder() -> None:
    """Stage1 模板应包含 <<USER_REQUEST>> 占位符。"""
    assert "<<USER_REQUEST>>" in CHARACTER_EXTRACTION_TEMPLATE


def test_scene_composition_template_contains_placeholders() -> None:
    """Stage2 模板应包含占位符。"""
    assert "<<USER_REQUEST>>" in SCENE_COMPOSITION_TEMPLATE
    assert "<<CHARACTER_CONSTRAINT>>" in SCENE_COMPOSITION_TEMPLATE


def test_character_detail_template_contains_placeholders() -> None:
    """Stage3 模板应包含占位符。"""
    assert "<<CHARACTER_LIST>>" in CHARACTER_DETAIL_TEMPLATE
    assert "<<USER_MENTIONED>>" in CHARACTER_DETAIL_TEMPLATE


def test_stage_templates_are_non_empty() -> None:
    """三个阶段的模板均非空。"""
    assert len(CHARACTER_EXTRACTION_TEMPLATE) > 0
    assert len(SCENE_COMPOSITION_TEMPLATE) > 0
    assert len(CHARACTER_DETAIL_TEMPLATE) > 0


# ==================== 默认提示词测试 ====================


def test_quality_tags_contains_required_tags() -> None:
    """质量词应包含必要的标签。"""
    assert "masterpiece" in QUALITY_TAGS
    assert "best quality" in QUALITY_TAGS
    assert "absurdres" in QUALITY_TAGS
    assert "newest" in QUALITY_TAGS


def test_default_negative_prompt_contains_basic_tags() -> None:
    """默认负面提示词应包含基础标签。"""
    assert "worst quality" in DEFAULT_NEGATIVE_PROMPT
    assert "blurry" in DEFAULT_NEGATIVE_PROMPT
    assert "deformed" in DEFAULT_NEGATIVE_PROMPT
    assert "nsfw" in DEFAULT_NEGATIVE_PROMPT


# ==================== 人物类关键词检测测试 ====================


def test_is_character_prompt_detects_girl() -> None:
    """应检测到 'girl' 关键词。"""
    assert is_character_prompt("solo, 1girl, smile") is True


def test_is_character_prompt_detects_boy() -> None:
    """应检测到 'boy' 关键词。"""
    assert is_character_prompt("solo, 1boy, standing") is True


def test_is_character_prompt_detects_selfie() -> None:
    """应检测到 'selfie' 关键词。"""
    assert is_character_prompt("selfie, looking at viewer") is True


def test_is_character_prompt_detects_face() -> None:
    """应检测到 'face' 关键词。"""
    assert is_character_prompt("beautiful face, smile") is True


def test_is_character_prompt_detects_anime() -> None:
    """应检测到 'anime' 关键词。"""
    assert is_character_prompt("anime style, cute") is True


def test_is_character_prompt_detects_known_characters() -> None:
    """应检测到已知角色名。"""
    assert is_character_prompt("hatsune miku (vocaloid)") is True
    assert is_character_prompt("saber (fate)") is True
    assert is_character_prompt("rem (re zero)") is True


def test_is_character_prompt_detects_chinese_keywords() -> None:
    """应检测到中文关键词。"""
    assert is_character_prompt("女孩, 微笑") is True
    assert is_character_prompt("自拍") is True
    assert is_character_prompt("校服") is True


def test_is_character_prompt_returns_false_for_landscape() -> None:
    """风景类提示词应返回 False。"""
    assert is_character_prompt("cherry blossom tree, spring, sunset") is False


def test_is_character_prompt_returns_false_for_objects() -> None:
    """物品类提示词应返回 False。"""
    assert is_character_prompt("car, red, fast, highway") is False


def test_is_character_prompt_returns_false_for_empty() -> None:
    """空提示词应返回 False。"""
    assert is_character_prompt("") is False


# ==================== 负面提示词生成测试 ====================


def test_get_default_negative_prompt_for_character() -> None:
    """人物类应返回完整的负面提示词。"""
    negative = get_default_negative_prompt(is_character=True)
    
    # 应包含所有人物类标签
    for tag in CHARACTER_NEGATIVE_TAGS:
        assert tag in negative, f"人物类负面提示词应包含: {tag}"


def test_get_default_negative_prompt_for_non_character() -> None:
    """非人物类应返回基础负面提示词。"""
    negative = get_default_negative_prompt(is_character=False)
    
    # 应包含所有非人物类标签
    for tag in NON_CHARACTER_NEGATIVE_TAGS:
        assert tag in negative, f"非人物类负面提示词应包含: {tag}"


def test_character_negative_tags_more_than_non_character() -> None:
    """人物类负面标签应多于非人物类。"""
    assert len(CHARACTER_NEGATIVE_TAGS) > len(NON_CHARACTER_NEGATIVE_TAGS)


def test_character_negative_tags_contain_anatomy_tags() -> None:
    """人物类负面标签应包含解剖学相关标签。"""
    assert "bad anatomy" in CHARACTER_NEGATIVE_TAGS
    assert "bad hands" in CHARACTER_NEGATIVE_TAGS
    assert "missing fingers" in CHARACTER_NEGATIVE_TAGS
    assert "extra limbs" in CHARACTER_NEGATIVE_TAGS


def test_character_negative_tags_contain_face_tags() -> None:
    """人物类负面标签应包含面部相关标签。"""
    assert "bad face" in CHARACTER_NEGATIVE_TAGS
    assert "poorly drawn face" in CHARACTER_NEGATIVE_TAGS
    assert "fused face" in CHARACTER_NEGATIVE_TAGS
    assert "cross-eyed" in CHARACTER_NEGATIVE_TAGS


# ==================== 关键词列表测试 ====================


def test_character_keywords_not_empty() -> None:
    """人物类关键词列表不应为空。"""
    assert len(CHARACTER_KEYWORDS) > 0


def test_character_keywords_contains_english_keywords() -> None:
    """应包含英文关键词。"""
    assert "girl" in CHARACTER_KEYWORDS
    assert "boy" in CHARACTER_KEYWORDS
    assert "woman" in CHARACTER_KEYWORDS
    assert "man" in CHARACTER_KEYWORDS


def test_character_keywords_contains_chinese_keywords() -> None:
    """应包含中文关键词。"""
    assert "女孩" in CHARACTER_KEYWORDS
    assert "男孩" in CHARACTER_KEYWORDS
    assert "自拍" in CHARACTER_KEYWORDS
