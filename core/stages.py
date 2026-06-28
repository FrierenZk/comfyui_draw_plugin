# -*- coding: utf-8 -*-
"""提示词生成各 Stage 实现：Stage1-3 + 后处理。"""

import asyncio
import json
import re
import time
from typing import TYPE_CHECKING

from src.services import llm_service

from .exceptions import PromptGenerationError
from .prompt_rules import (
    CHARACTER_EXTRACTION_TEMPLATE,
    SCENE_COMPOSITION_TEMPLATE,
    CHARACTER_FEATURE_TEMPLATE,
    CHARACTER_DETAIL_TEMPLATE,
    APPEARANCE_ANALYSIS_TEMPLATE,
    DEFAULT_NEGATIVE_PROMPT,
    merge_person_tags,
    split_prompt_tags,
)

if TYPE_CHECKING:
    from ..sdk_runtime import ComfyUIDrawInvocation


class StagesMixin:
    """Stage 1-3 实现 + 后处理，作为 ComfyUIDrawGenerator 的 mixin 父类。"""
    def _process_direct_prompts(
        self, positive_prompt: str, negative_prompt: str
    ) -> tuple[str, str]:
        """处理直接提示词：质量词、人数合并、补充负面词。"""
        pos_list = split_prompt_tags(positive_prompt)
        neg_list = split_prompt_tags(negative_prompt) if negative_prompt else []

        pos_list = self.inv._ensure_quality_tags(pos_list)
        pos_list = merge_person_tags(pos_list)
        if neg_list:
            neg_list = self.inv._ensure_negative_tags(pos_list, neg_list)
        else:
            neg_list = split_prompt_tags(DEFAULT_NEGATIVE_PROMPT)

        return ", ".join(pos_list), ", ".join(neg_list)

    # ── LLM 提示词生成 ────────────────────────────────────

    async def _generate_prompts_with_llm(self, description: str) -> tuple[str, str]:
        """三阶段 LLM 生成：S1 低温提取角色 → S2 正常温度场景构图 → S3 低温补充角色细节。"""
        try:
            model_name = self.inv._get_config("llm", "model_name", "")
            temperature = self.inv._get_config("llm", "temperature", 0.3)
            s1_max_tokens = self.inv._get_config("llm", "max_tokens_char_extract", 2000)
            s2_max_tokens = self.inv._get_config("llm", "max_tokens_scene", 5000)
            s3_max_tokens = self.inv._get_config("llm", "max_tokens_char_detail", 5000)

            task_name = self._resolve_task_name(model_name)

            if not task_name:
                self.logger.error(
                    f"LLM 提示词生成失败: 模型不可用 model_name={model_name}, "
                    f"用户描述={description[:100]}"
                )
                raise PromptGenerationError(f"模型不可用: {model_name}")

            # ═══ Phase 1: S1 角色 + 服装 + 负面 并发低温提取 (temp=0.1) ═══
            import asyncio as _asyncio
            characters, clothing, neg_supp = await _asyncio.gather(
                self._extract_characters(task_name, description, s1_max_tokens),
                self._extract_clothing(task_name, description, s1_max_tokens),
                self._extract_negatives(task_name, description, 300),
            )
            self.inv._debug_log(f"Stage1 提取: 角色={characters}, 服装={clothing}, 负面补充={neg_supp}")

            # 代码层写死权重，不依赖 LLM
            weighted_chars = [f"({c}:1.05)" for c in characters]
            weighted_clothing = [f"({c}:1.1)" for c in clothing]

            # ═══ Phase 2: 预搜索 ∥ S2a 场景构图 并发 ═══
            # S2a 不依赖 pre_search 的 extra_info，可以并发
            char_task = self._fetch_character_info(task_name, characters) if characters else None
            cloth_task = self._fetch_clothing_info(task_name, clothing) if clothing else None
            s2a_task = self._generate_scene_composition(
                task_name, description, characters, temperature, s2_max_tokens,
                clothing=clothing, weighted_clothing=weighted_clothing,
                weighted_chars=weighted_chars,
            )
            p2_tasks = [t for t in (char_task, cloth_task, s2a_task) if t is not None]
            p2_results = await _asyncio.gather(*p2_tasks)

            # 解包 Phase 2 结果
            char_info = cloth_info = ""
            pos_list = None
            idx = 0
            if char_task:
                char_info = p2_results[idx] or ""; idx += 1
            if cloth_task:
                cloth_info = p2_results[idx] or ""; idx += 1
            if s2a_task:
                pos_list, _ = p2_results[idx]; idx += 1
            extra_info = "\n\n".join(s for s in (char_info, cloth_info) if s)
            self.inv._debug_log(
                f"预搜索: 角色={len(char_info)}chars 服装={len(cloth_info)}chars | "
                f"S2a 场景构图: {len(pos_list)} tags\n"
                f"  char_info: {char_info[:120]}...\n"
                f"  cloth_info: {cloth_info[:120]}..."
            )

            # ═══ Phase 3: S2b 人物特征 ═══
            appearance, clothing_s2b, other = await self._generate_character_features(
                task_name, f"{description}\n\n<search_info>\n{extra_info}\n</search_info>" if extra_info else description,
                characters, s2_max_tokens, with_search=0, clothing=clothing,
                weighted_clothing=weighted_clothing, weighted_chars=weighted_chars,
            )
            self.inv._debug_log(f"Stage2b 外貌={len(appearance)} 服装={len(clothing_s2b)} 其他={len(other)}")

            # ═══ Phase 4: S3a 外观维度分析 → S3b ∥ S3c 并发补充 ═══
            covered_dims = ""
            char_details = []
            cloth_tags = []
            if characters or clothing:
                # S3a 先跑：分析 S2b 已覆盖的 12 个维度（含 6 个服装维度）
                s3_context = f"用户描述: {description}"
                s2b_all = appearance + clothing_s2b + other
                if s2b_all:
                    s3_context += f"\nStage2b 已生成: {', '.join(s2b_all)}"
                covered_dims = await self._analyze_appearance(task_name, s3_context)
                self.inv._debug_log(f"Stage3a 已覆盖维度: {covered_dims}")

                # S3b + S3c 并发，共用 covered_dims
                s3b_task = self._get_cached_char_tags(task_name, characters, covered_dims, extra_info, s3_max_tokens) if characters else None
                s3c_task = self._get_cached_cloth_tags(task_name, clothing, covered_dims, extra_info, s3_max_tokens) if clothing else None
                tasks = [t for t in (s3b_task, s3c_task) if t is not None]
                if tasks:
                    results = await _asyncio.gather(*tasks)
                    r_idx = 0
                    if s3b_task:
                        char_details = results[r_idx]; r_idx += 1
                        if char_details:
                            self.inv._debug_log(f"Stage3b 角色细节补充: {len(char_details)} tags")
                    if s3c_task:
                        cloth_tags = results[r_idx]; r_idx += 1
                        if cloth_tags:
                            self.inv._debug_log(f"Stage3c 服装细节补充: {len(cloth_tags)} tags")

            # 统一组装所有标签
            pos_list = self._assemble_tags(
                pos_list,
                appearance=appearance,
                clothing_s2b=clothing_s2b,
                other=other,
                char_details=char_details,
                cloth_tags=cloth_tags,
                weighted_chars=weighted_chars,
                weighted_clothing=weighted_clothing,
            )

            # 负面提示词：默认 + S1c 提取的上下文补充
            neg_list = split_prompt_tags(DEFAULT_NEGATIVE_PROMPT)
            if neg_supp:
                neg_list = neg_list + [t for t in neg_supp if t not in neg_list]

            return self._finalize_prompts(pos_list, neg_list)

        except PromptGenerationError:
            raise
        except Exception as e:
            self.logger.error(
                f"LLM 提示词生成异常: {type(e).__name__}: {e}, "
                f"用户描述={description[:100]}"
            )
            raise PromptGenerationError(str(e)) from e

    # ── Stage 1: 角色名提取 (temp=0.1) ──

    async def _extract_characters(
        self, task_name: str, description: str, max_tokens: int = 200
    ) -> list[str]:
        """低温提取角色名，注入外部搜索结果辅助验证。"""
        # 搜索角色信息辅助提取
        knowledge = await self._search_knowledge(f"{description} 动漫游戏角色")
        prompt = CHARACTER_EXTRACTION_TEMPLATE.replace("<<USER_REQUEST>>", description)
        if knowledge:
            prompt = prompt.replace(
                "<user_request>",
                f"<knowledge_reference>\n{knowledge[:1000]}\n</knowledge_reference>\n\n<user_request>",
            )

        success, resp = await self._llm_generate(task_name=task_name, prompt=prompt, temperature=0.1, max_tokens=max_tokens, validate=lambda t: self._validate_json_response(t, "characters"), with_search=2)

        if not success or not resp:
            self.logger.warning("Stage1 角色提取失败，跳过")
            return []

        try:
            resp = self._clean_llm_json(resp)
            data = json.loads(resp)
            return data.get("characters", [])
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage1 角色提取解析失败: {e}, 原始响应={resp[:200]}")
            return []

    # ── Stage 1b: 服装提取 (temp=0.1) ──

    async def _extract_clothing(
        self, task_name: str, description: str, max_tokens: int = 200
    ) -> list[str]:
        """低温提取用户明确指定的服装/配饰，注入外部搜索结果辅助验证。"""
        from .prompt_rules import CLOTHING_EXTRACTION_TEMPLATE

        prompt = CLOTHING_EXTRACTION_TEMPLATE.replace("<<USER_REQUEST>>", description)

        success, resp = await self._llm_generate(
            task_name=task_name, prompt=prompt, temperature=0.1,
            max_tokens=max_tokens,
            validate=lambda t: self._validate_json_response(t, "clothing"),
            with_search=2,
        )

        if not success or not resp:
            self.logger.warning("Stage1b 服装提取失败，跳过")
            return []

        try:
            resp = self._clean_llm_json(resp)
            data = json.loads(resp)
            clothing = data.get("clothing", [])
            return clothing if isinstance(clothing, list) else []
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage1b 服装提取解析失败: {e}, 原始响应={resp[:200]}")
            return []

    # ── Stage 1c: 负面标签提取 (temp=0.1) ──

    async def _extract_negatives(
        self, task_name: str, description: str, max_tokens: int = 300
    ) -> list[str]:
        """低温提取用户描述中的上下文负面标签（风格对立、明确排除项）。"""
        from .prompt_rules import NEGATIVE_EXTRACTION_TEMPLATE

        prompt = NEGATIVE_EXTRACTION_TEMPLATE.replace("<<USER_REQUEST>>", description)

        success, resp = await self._llm_generate(
            task_name=task_name, prompt=prompt, temperature=0.1,
            max_tokens=max_tokens,
            validate=lambda t: self._validate_json_response(t, "negative"),
            with_search=0,
        )

        if not success or not resp:
            return []

        try:
            resp = self._clean_llm_json(resp)
            data = json.loads(resp)
            result = data.get("negative", [])
            return result if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    # ── Stage 2: 场景构图 (temp=0.3) ──

    async def _generate_scene_composition(
        self,
        task_name: str,
        description: str,
        characters: list[str],
        temperature: float,
        max_tokens: int,
        knowledge: str = "",
        clothing: list[str] = None,
        weighted_clothing: list[str] = None,
        weighted_chars: list[str] = None,
    ) -> tuple[list[str], list[str]]:
        """正常温度生成场景、构图、光影提示词，可选注入外部搜索结果。"""
        wchars = weighted_chars or [f"({c}:1.05)" for c in characters]
        if characters:
            constraint = (
                "<character_constraint>\n"
                "以下角色已锁定，**必须使用、不可更改**。不要添加角色外观细节（发色、发型、服装等），后续阶段会补充：\n"
                + "\n".join(f"- {c}" for c in wchars)
                + "\n</character_constraint>"
            )
        else:
            constraint = "<character_constraint>无已知角色，按原创人物处理，需自行描写外貌。</character_constraint>"

        wcl = weighted_clothing or clothing or []
        if wcl:
            cloth_constraint = (
                "<clothing_constraint>\n"
                "以下服装/配饰已锁定，**禁止输出任何服装相关标签**，由后续阶段处理：\n"
                + "\n".join(f"- {c}" for c in wcl)
                + "\n</clothing_constraint>"
            )
        else:
            cloth_constraint = "<clothing_constraint>无指定服装/配饰。</clothing_constraint>"

        prompt = SCENE_COMPOSITION_TEMPLATE
        prompt = prompt.replace("<<CHARACTER_CONSTRAINT>>", constraint)
        prompt = prompt.replace("<<CLOTHING_CONSTRAINT>>", cloth_constraint)
        prompt = prompt.replace("<<USER_REQUEST>>", description)
        if knowledge:
            prompt = prompt.replace(
                "<user_request>",
                f"<knowledge_reference>\n{knowledge[:2000]}\n</knowledge_reference>\n\n<user_request>",
            )

        success, resp = await self._llm_generate(task_name=task_name, prompt=prompt, temperature=temperature, max_tokens=max_tokens, validate=lambda t: self._validate_json_response(t, "positive"), with_search=0)

        if not success or not resp:
            self.logger.error("Stage2 场景生成失败")
            raise PromptGenerationError("场景生成失败")

        return self._parse_llm_response(resp)

    # ── Stage 2b: 人物特征 (temp=0.2) ──

    async def _generate_character_features(
        self,
        task_name: str,
        description: str,
        characters: list[str],
        max_tokens: int,
        knowledge: str = "", with_search: bool = True,
        clothing: list[str] = None,
        weighted_clothing: list[str] = None,
        weighted_chars: list[str] = None,
    ) -> tuple[list[str], list[str], list[str]]:
        """低温度提取人物外貌、服装、动作/表情，返回 (appearance, clothing, other)。"""
        wchars = weighted_chars or [f"({c}:1.05)" for c in characters]
        if characters:
            constraint = (
                "<character_constraint>\n"
                "以下角色已锁定，**必须使用、不可更改**：\n"
                + "\n".join(f"- {c}" for c in wchars)
                + "\n</character_constraint>"
            )
        else:
            constraint = "<character_constraint>无已知角色，按原创人物处理。</character_constraint>"

        wcl = weighted_clothing or clothing or []
        if wcl:
            cloth_constraint = (
                "<clothing_constraint>\n"
                "以下服装/配饰已由用户明确指定，**必须原样输出到 clothing 字段，不可丢弃**：\n"
                + "\n".join(f"- {c}" for c in wcl)
                + "\n然后在后面展开为具体标签。\n"
                "</clothing_constraint>"
            )
        else:
            cloth_constraint = "<clothing_constraint>无指定服装/配饰。</clothing_constraint>"

        prompt = CHARACTER_FEATURE_TEMPLATE
        prompt = prompt.replace("<<CHARACTER_CONSTRAINT>>", constraint)
        prompt = prompt.replace("<<CLOTHING_CONSTRAINT>>", cloth_constraint)
        prompt = prompt.replace("<<USER_REQUEST>>", description)
        if knowledge:
            prompt = prompt.replace(
                "<user_request>",
                f"<knowledge_reference>\n{knowledge[:2000]}\n</knowledge_reference>\n\n<user_request>",
            )

        success, resp = await self._llm_generate(task_name=task_name, prompt=prompt, temperature=0.2, max_tokens=max_tokens, validate=lambda t: self._validate_json_response(t, "appearance"), with_search=with_search)

        if not success or not resp:
            self.logger.warning("Stage2b 人物特征生成失败，跳过")
            return [], [], []

        return self._parse_character_features(resp)

    # ── Stage 3a: 外观维度分析 (temp=0.1) ──

    async def _analyze_appearance(
        self, task_name: str, context: str = ""
    ) -> str:
        """分析用户描述+Stage2b输出中已覆盖的外观维度。"""
        prompt = APPEARANCE_ANALYSIS_TEMPLATE.replace("<<USER_REQUEST>>", context)

        s3a_max = self.inv._get_config("llm", "max_tokens_char_extract", 2000)
        success, resp = await self._llm_generate(task_name=task_name, prompt=prompt, temperature=0.1, max_tokens=s3a_max, validate=lambda t: self._validate_json_response(t, "covered"), with_search=0)

        if not success or not resp:
            self.logger.warning("Stage3a 分析失败，跳过")
            return ""

        try:
            resp = self._clean_llm_json(resp)
            data = json.loads(resp)
            covered = data.get("covered", [])
            details = data.get("mentioned_details", "")
            if not covered:
                return f"用户未描述具体外貌。（{details}）" if details else "用户未描述具体外貌。"
            return f"已覆盖：{', '.join(covered)}；详情：{details}"
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage3a 解析失败: {e}")
            return ""

    # ── Stage 3b: 角色细节补充 (temp=0.15) ──

    async def _supplement_character_details(
        self,
        task_name: str,
        characters: list[str],
        covered_dims: str = "",
        extra_info: str = "",
        max_tokens: int = 600,
    ) -> list[str]:
        """补充未覆盖的角色外观细节，复用预搜索结果。"""
        prompt = CHARACTER_DETAIL_TEMPLATE
        if extra_info:
            prompt = prompt.replace("<<CHARACTER_LIST>>",
                f"{extra_info[:2000]}\n\n<<CHARACTER_LIST>>")
        prompt = prompt.replace("<<CHARACTER_LIST>>", "\n".join(f"- {c}" for c in characters))
        prompt = prompt.replace("<<USER_MENTIONED>>", covered_dims)
        # 清理 knowledge_reference 占位符
        prompt = prompt.replace(
            "<knowledge_reference>\n\n</knowledge_reference>\n\n", ""
        ).replace(
            "<knowledge_reference>\n</knowledge_reference>\n\n", ""
        )

        success, resp = await self._llm_generate(task_name=task_name, prompt=prompt, temperature=0.15, max_tokens=max_tokens, validate=lambda t: self._validate_json_response(t, "character_positive"), with_search=0)

        if not success or not resp:
            self.logger.warning("Stage3 角色细节补充失败，跳过")
            return []

        try:
            resp = self._clean_llm_json(resp)
            data = json.loads(resp)
            return data.get("character_positive", [])
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage3 解析失败: {e}")
            return []

    async def _generate_negatives(self, task_name: str, pos_list: list[str], description: str = "") -> list[str]:
        """根据正面提示词上下文，LLM 补充场景相关的负面标签。"""
        ctx = ", ".join(pos_list[:50])
        prompt = (
            f"已有负面标签（无需重复）：{DEFAULT_NEGATIVE_PROMPT}\n"
            f"正面提示词参考：{ctx}\n"
            f"用户原始描述：{description[:200]}\n"
            "仅在正面内容明显涉及以下情况时才添加对应负面标签，否则输出空数组：\n"
            "- 动漫/二次元风格 → 加 realistic, photorealistic, 3d, 3d render\n"
            "- 成人/R18 暗示 → 加 nsfw\n"
            "- 写实风格 → 加 anime, cartoon\n"
            "- **重要：用户原始描述中明确想要的，不要加为负面**\n"
            "- **用户明确说不要/别/勿/no/don't的，提取为英文负面标签**（如'不要猫'→cat,'不要雨'→rain）\n"
            "不要添加质量/解剖/水印类标签（已有）。无必要则输出 {\"negative\": []}"
        )
        success, resp = await self._llm_generate(
            task_name=task_name, prompt=prompt, temperature=0.2, max_tokens=500, with_search=0
        )
        if not success or not resp:
            return []
        resp = self._clean_llm_json(resp)
        try:
            data = json.loads(resp)
            return list(data.get("negative", []))
        except json.JSONDecodeError:
            return []

    _TAGS_CACHE_FILE = "character_tags.json"
    _TAGS_CACHE_TIERS = [3, 7, 30, 90]

    async def _get_cached_char_tags(
        self, task_name: str, characters: list[str], covered_dims: str,
        extra_info: str, max_tokens: int,
    ) -> list[str]:
        """两层缓存：标签 → 语言描述 → LLM 生成。"""
        cache_key = ",".join(sorted(c.lower() for c in characters))
        now = time.time()

        # Layer 1: 标签缓存（最快，跳过 LLM）
        tags_cache = self._load_json_cache(self._TAGS_CACHE_FILE)
        entry = tags_cache.get(cache_key)
        if entry and now - entry.get("ts", 0) < entry.get("ttl", 3) * 86400:
            self.inv._debug_log(f"标签缓存命中({entry.get('ttl')}天): {cache_key[:60]}")
            return entry["data"]

        # Layer 2: 语言描述缓存（跳过 web_search，仍需 LLM）
        if not extra_info:
            char_info = await self._fetch_character_info(task_name, characters)
            extra_info = char_info or ""

        # Layer 3: LLM 生成 + 写入标签缓存
        tags = await self._supplement_character_details(
            task_name, characters, covered_dims, extra_info, max_tokens
        )
        if tags:
            new_ttl = 3
            if entry:
                old_set = set(entry["data"])
                overlap = len(set(tags) & old_set) / max(len(set(tags) | old_set), 1)
                old_tier = self._TAGS_CACHE_TIERS.index(entry.get("ttl", 3))
                new_ttl = self._TAGS_CACHE_TIERS[min(old_tier + 1, 3)] if overlap > 0.5 else 3
            # 仅 Anthropic 路径且未截断才写标签缓存
            if self.inv._get_config("llm", "use_anthropic_api", False) and not getattr(self, "_last_truncated", False):
                tags_cache[cache_key] = {"data": tags, "ts": now, "ttl": new_ttl}
                self._save_json_cache(self._TAGS_CACHE_FILE, tags_cache)
        return tags

    # ── Stage 3c: 服装标签缓存 ──

    _CLOTH_TAGS_CACHE_FILE = "clothing_tags.json"

    async def _get_cached_cloth_tags(
        self, task_name: str, clothing: list[str],
        covered_dims: str, extra_info: str, max_tokens: int,
    ) -> list[str]:
        """服装标签两层缓存：标签 → 语言描述 → LLM 生成。"""
        # 如果 S3a 已判定全部 6 个服装维度已覆盖，直接返回空
        _CLOTHING_DIMS = ("上装", "下装", "腿部", "足部", "头部配饰", "饰品配件")
        if covered_dims and all(d in covered_dims for d in _CLOTHING_DIMS):
            self.inv._debug_log("S3c 服装维度全已覆盖，跳过")
            return []

        cache_key = ",".join(sorted(c.lower() for c in clothing))
        now = time.time()

        # Layer 1: 标签缓存（最快，跳过 LLM）
        tags_cache = self._load_json_cache(self._CLOTH_TAGS_CACHE_FILE)
        entry = tags_cache.get(cache_key)
        if entry and now - entry.get("ts", 0) < entry.get("ttl", 3) * 86400:
            self.inv._debug_log(f"服装标签缓存命中({entry.get('ttl')}天): {cache_key[:60]}")
            return entry["data"]

        # Layer 2: 语言描述缓存（跳过 web_search，仍需 LLM）
        if not extra_info:
            cloth_info = await self._fetch_clothing_info(task_name, clothing)
            extra_info = cloth_info or ""

        # Layer 3: LLM 生成 + 写入标签缓存
        tags = await self._supplement_clothing_details(
            task_name, clothing, covered_dims, extra_info, max_tokens
        )
        if tags:
            new_ttl = 3
            if entry:
                old_set = set(entry["data"])
                overlap = len(set(tags) & old_set) / max(len(set(tags) | old_set), 1)
                old_tier = self._TAGS_CACHE_TIERS.index(entry.get("ttl", 3))
                new_ttl = self._TAGS_CACHE_TIERS[min(old_tier + 1, 3)] if overlap > 0.5 else 3
            # 仅 Anthropic 路径且未截断才写标签缓存
            if self.inv._get_config("llm", "use_anthropic_api", False) and not getattr(self, "_last_truncated", False):
                tags_cache[cache_key] = {"data": tags, "ts": now, "ttl": new_ttl}
                self._save_json_cache(self._CLOTH_TAGS_CACHE_FILE, tags_cache)
        return tags

    async def _supplement_clothing_details(
        self,
        task_name: str,
        clothing: list[str],
        covered_dims: str = "",
        extra_info: str = "",
        max_tokens: int = 600,
    ) -> list[str]:
        """补充服装细节标签，复用预搜索结果和 S3a 覆盖分析。"""
        from .prompt_rules import CLOTHING_DETAIL_TEMPLATE

        prompt = CLOTHING_DETAIL_TEMPLATE
        if extra_info:
            prompt = prompt.replace("<<CLOTHING_LIST>>",
                f"{extra_info[:2000]}\n\n<<CLOTHING_LIST>>")
        prompt = prompt.replace("<<CLOTHING_LIST>>", "\n".join(f"- {c}" for c in clothing))
        prompt = prompt.replace("<<USER_MENTIONED>>", covered_dims or "无覆盖信息")
        # 清理 knowledge_reference 占位符
        prompt = prompt.replace(
            "<knowledge_reference>\n\n</knowledge_reference>\n\n", ""
        ).replace(
            "<knowledge_reference>\n</knowledge_reference>\n\n", ""
        )

        success, resp = await self._llm_generate(
            task_name=task_name, prompt=prompt, temperature=0.15, max_tokens=max_tokens,
            validate=lambda t: self._validate_json_response(t, "clothing_positive"),
            with_search=0,
        )

        if not success or not resp:
            self.logger.warning("Stage3c 服装细节补充失败，跳过")
            return []

        try:
            resp = self._clean_llm_json(resp)
            data = json.loads(resp)
            return data.get("clothing_positive", [])
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage3c 服装解析失败: {e}")
            return []

    # ── 标签组装 ──────────────────────────────────────────

    def _assemble_tags(
        self,
        pos_list: list[str],
        *,
        appearance: list[str] = None,
        clothing_s2b: list[str] = None,
        other: list[str] = None,
        char_details: list[str] = None,
        cloth_tags: list[str] = None,
        weighted_chars: list[str] = None,
        weighted_clothing: list[str] = None,
    ) -> list[str]:
        """统一组装所有 Stage 标签。

        顺序: (anchor) → weighted_chars → appearance → char_details
               → weighted_clothing → clothing_s2b → cloth_tags → other
               → [S2a 剩余: lighting, style, ...]
        anchor 之后的 S2a 标签（构图、光影等）排在最后。
        """
        app = appearance or []
        clt = clothing_s2b or []
        oth = other or []
        chd = char_details or []
        ctg = cloth_tags or []
        wc = weighted_chars or []
        wcl = weighted_clothing or []

        # 锚点
        anchor = next((i for i, t in enumerate(pos_list) if ":" in t and "(" in t), 4)

        # S2a 剩余标签（构图/环境/光影/风格）
        s2a_tail = pos_list[anchor + 1:]

        # 加权角色在角色区块前，加权服装在服装区块前
        after = wc + app + chd + wcl + clt + ctg + oth

        result = pos_list[:anchor + 1] + after + s2a_tail

        self.inv._debug_log(
            f"组装 tags: S2a={len(pos_list)}(锚点后{len(s2a_tail)}) "
            f"S2b 外貌={len(app)} 服装={len(clt)} 其他={len(oth)} | "
            f"加权角色={len(wc)} 加权服装={len(wcl)} | "
            f"S3b 角色补充={len(chd)} S3c 服装补充={len(ctg)} | "
            f"总计={len(result)}"
        )

        return result

    def _finalize_prompts(self, pos_list: list[str], neg_list: list[str]) -> tuple[str, str]:
        """合并提示词后处理：合并人数标签、补负面词。"""
        before = len(pos_list)
        pos_list = self.inv._ensure_quality_tags(list(pos_list))
        pos_list = merge_person_tags(pos_list)
        # 标准化去重：剥离权重括号+比例后比对，保留高权重
        import re as _re
        def _tag_weight(tag: str) -> float:
            m = _re.search(r":(\d+(?:\.\d+)?)\)?$", tag)
            return float(m.group(1)) if m else 1.0

        seen = {}
        for t in pos_list:
            key = _re.sub(r"[\(\)]", "", t)
            key = _re.sub(r":\d+(\.\d+)?", "", key)
            key = key.lower()  # 忽略大小写
            tw = _tag_weight(t); sw = _tag_weight(seen.get(key, ""))
            if key not in seen or tw > sw or (tw == sw and t.startswith("(") and not seen[key].startswith("(")):
                seen[key] = t
        pos_list = list(seen.values())
        # 大小写不敏感去重
        _ns = {}
        for t in neg_list:
            if t.lower() not in _ns:
                _ns[t.lower()] = t
        neg_list = list(_ns.values())
        delta = len(pos_list) - before
        if delta:
            self.inv._debug_log(f"标签合并: {before} → {len(pos_list)} tags ({'新增' if delta > 0 else '删除'} {abs(delta)})")
        neg_list = self.inv._ensure_negative_tags(pos_list, neg_list)

        # 清理转义字符 + 二次去重 + 统计
        pos_list = [t.replace("\\(", "(").replace("\\)", ")") for t in pos_list]
        neg_list = [t.replace("\\(", "(").replace("\\)", ")") for t in neg_list]
        _ps = {}; _ns2 = {}
        for t in pos_list: _ps.setdefault(t.lower(), t)
        for t in neg_list: _ns2.setdefault(t.lower(), t)
        pos_list = list(_ps.values())
        neg_list = list(_ns2.values())
        self.inv._debug_log(f"终: pos={len(pos_list)} tags, neg={len(neg_list)} tags")

        return ", ".join(pos_list), ", ".join(neg_list)

    def _resolve_task_name(self, preferred_name: str) -> str | None:
        try:
            models = llm_service.get_available_models()
            if preferred_name and preferred_name in models:
                return preferred_name
            for candidate in ("planner", "replyer"):
                if candidate in models:
                    return candidate
            return next(iter(models.keys()), None)
        except Exception:
            return None

    def _parse_llm_response(self, response: str) -> tuple[list[str], list[str]]:
        """解析 LLM JSON 响应，返回 positive, negative 标签列表。多级回退。"""
        # 1. 全文 JSON 解析
        text = self._clean_llm_json(response)
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "positive" in data:
                return self._extract_pos_neg(data)
        except json.JSONDecodeError:
            pass

        # 2. 从文本中提取 JSON 块（正则在任意位置匹配 {"positive":...}）
        m = re.search(r'\{"positive"\s*:\s*\[.+?\],\s*"negative"\s*:\s*\[.+?\]\}', text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
                return self._extract_pos_neg(data)
            except json.JSONDecodeError:
                pass

        # 3. 回退：按行解析（第1行=正面，第2行=负面）
        lines = [line.strip() for line in response.split("\n") if line.strip()]
        if len(lines) >= 2:
            return split_prompt_tags(lines[0]), split_prompt_tags(lines[1])
        elif len(lines) == 1:
            return split_prompt_tags(lines[0]), split_prompt_tags(DEFAULT_NEGATIVE_PROMPT)
        else:
            return (
                ["masterpiece", "best quality", "1girl", "anime style"],
                split_prompt_tags(DEFAULT_NEGATIVE_PROMPT),
            )

    def _parse_character_features(self, response: str) -> tuple[list[str], list[str], list[str]]:
        """解析 S2b 结构化响应，返回 (appearance, clothing, other)。兼容旧格式回退。"""
        text = self._clean_llm_json(response)
        # 1. 新格式 {"appearance": [...], "clothing": [...], "other": [...]}
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "appearance" in data:
                return (
                    list(data.get("appearance", [])),
                    list(data.get("clothing", [])),
                    list(data.get("other", [])),
                )
        except json.JSONDecodeError:
            pass

        # 2. 正则提取新格式 JSON 块
        m = re.search(
            r'\{"appearance"\s*:\s*\[.+?\],\s*"clothing"\s*:\s*\[.+?\],\s*"other"\s*:\s*\[.+?\]\}',
            text, re.DOTALL,
        )
        if m:
            try:
                data = json.loads(m.group())
                return (
                    list(data.get("appearance", [])),
                    list(data.get("clothing", [])),
                    list(data.get("other", [])),
                )
            except json.JSONDecodeError:
                pass

        # 3. 回退：老格式 {"positive": [...], "negative": [...]}
        pos_list, _ = self._parse_llm_response(response)
        return pos_list, [], []

    @staticmethod
    def _strip_search_lines(text: str) -> str:
        """去除 LLM 返回中的 [搜索: ...] 行，只留纯净 JSON。"""
        lines = text.strip().split("\n")
        clean = [l for l in lines if not l.strip().startswith("[搜索:")]
        return "\n".join(clean)

    @staticmethod
    def _clean_llm_json(text: str) -> str:
        """清理 LLM 响应：去搜索行 + 去代码块包裹 → 返回纯净 JSON 字符串。"""
        text = StagesMixin._strip_search_lines(text)
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        return text

    @staticmethod
    def _extract_pos_neg(data: dict) -> tuple[list[str], list[str]]:
        pos = data.get("positive", [])
        neg = data.get("negative", [])
        pos_list = list(pos) if isinstance(pos, list) else [str(pos)]
        neg_list = list(neg) if isinstance(neg, list) else ([str(neg)] if neg else [])
        return pos_list, neg_list
