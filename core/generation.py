# -*- coding: utf-8 -*-
"""图片生成流程：工作流加载 → 提示词生成 → 提交 → 等待 → 获取结果。"""

import asyncio
import json
import os
from typing import TYPE_CHECKING

from src.services import llm_service

from .prompt_rules import (
    CHARACTER_EXTRACTION_TEMPLATE,
    SCENE_COMPOSITION_TEMPLATE,
    CHARACTER_FEATURE_TEMPLATE,
    CHARACTER_DETAIL_TEMPLATE,
    APPEARANCE_ANALYSIS_TEMPLATE,
    DEFAULT_NEGATIVE_PROMPT,
    CHARACTER_DETAIL_TAGS,
    CHARACTER_NEGATIVE_TAGS,
    NON_CHARACTER_NEGATIVE_TAGS,
    merge_person_tags,
    split_prompt_tags,
)

if TYPE_CHECKING:
    from ..sdk_runtime import ComfyUIDrawInvocation

_IMAGE_CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "cache", "images")
)


# ==================== 异常 ====================

class ComfyUIDrawError(Exception):
    """插件内部错误基类。"""


class ComfyUIConnectionError(ComfyUIDrawError):
    """连接 ComfyUI MCP 服务器失败。"""


class WorkflowLoadError(ComfyUIDrawError):
    """工作流获取或解析失败。"""


class PromptGenerationError(ComfyUIDrawError):
    """LLM 提示词生成失败。"""


class GenerationSubmitError(ComfyUIDrawError):
    """任务提交失败（enqueue 或提取 prompt_id 失败）。"""


class GenerationExecutionError(ComfyUIDrawError):
    """图片生成执行失败（ComfyUI 返回 error）。"""


class GenerationTimeoutError(ComfyUIDrawError):
    """图片生成超时。"""


class ImageRetrievalError(ComfyUIDrawError):
    """图片获取或解析失败。"""


# ==================== 生成器 ====================


class ComfyUIDrawGenerator:
    """图片生成流程编排。依赖 ComfyUIDrawInvocation 提供 MCP 连接和工具方法。"""

    def __init__(self, invocation: "ComfyUIDrawInvocation") -> None:
        self.inv = invocation
        self.logger = invocation.logger

    # ── 公开入口 ──────────────────────────────────────────

    async def generate_image(self, stream_id: str, description: str) -> None:
        """生成图片主流程（LLM 翻译描述 → 提示词）。"""
        try:
            await self.inv.connect()
            workflow = await self._load_workflow()

            positive, negative = await self._generate_prompts_with_llm(description)
            self.inv._debug_log(f"正面提示词: {positive[:100]}")
            self.inv._debug_log(f"负面提示词: {negative[:100]}")

            await self.inv._send_message(
                stream_id,
                f"✅ 提示词生成成功\n\n"
                f"【正面提示词】\n{positive}\n\n"
                f"【负面提示词】\n{negative}",
            )

            prompt_id = await self._enqueue_job(workflow, positive, negative)
            await self._wait_for_completion(prompt_id)
            image_base64 = await self._retrieve_image(prompt_id)

            await self.inv.plugin.ctx.send.image(image_base64, stream_id)
            await self.inv._send_message(stream_id, f"图片生成完成！\n描述：{description}")

        except ComfyUIConnectionError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 连接 ComfyUI 失败")
        except WorkflowLoadError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 获取工作流失败")
        except PromptGenerationError as e:
            self.logger.error(f"提示词生成失败: stream_id={stream_id}, {e}")
            await self.inv._send_message(stream_id, "❌ 提示词生成失败，请稍后重试")
        except GenerationSubmitError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 提交任务失败")
        except GenerationExecutionError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 图片生成失败")
        except GenerationTimeoutError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 图片生成超时")
        except ImageRetrievalError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 获取图片失败")
        except ComfyUIDrawError as e:
            self.logger.error(f"生成图片异常: stream_id={stream_id}, {e}")
            await self.inv._send_message(stream_id, "❌ 图片生成失败，请稍后重试")
        finally:
            await self.inv.disconnect()

    async def generate_image_with_prompts(
        self, stream_id: str, positive_prompt: str, negative_prompt: str
    ) -> None:
        """直接使用提示词生成图片（跳过 LLM）。"""
        try:
            await self.inv.connect()
            workflow = await self._load_workflow()

            positive, negative = self._process_direct_prompts(positive_prompt, negative_prompt)
            self.inv._debug_log(f"正面提示词: {positive[:100]}")
            self.inv._debug_log(f"负面提示词: {negative[:100]}")

            await self.inv._send_message(stream_id, "正在生成图片，请稍候...")

            prompt_id = await self._enqueue_job(workflow, positive, negative)
            await self._wait_for_completion(prompt_id)
            image_base64 = await self._retrieve_image(prompt_id)

            await self.inv.plugin.ctx.send.image(image_base64, stream_id)
            await self.inv._send_message(stream_id, "图片生成完成！")

        except ComfyUIConnectionError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 连接 ComfyUI 失败")
        except WorkflowLoadError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 获取工作流失败")
        except GenerationSubmitError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 提交任务失败")
        except GenerationExecutionError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 图片生成失败")
        except GenerationTimeoutError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 图片生成超时")
        except ImageRetrievalError as e:
            self.logger.error(str(e))
            await self.inv._send_message(stream_id, "❌ 获取图片失败")
        except ComfyUIDrawError as e:
            self.logger.error(f"生成图片异常: stream_id={stream_id}, {e}")
            await self.inv._send_message(stream_id, "❌ 图片生成失败，请稍后重试")
        finally:
            await self.inv.disconnect()

    # ── 流程步骤 ──────────────────────────────────────────

    async def _load_workflow(self) -> dict:
        workflow_file = self.inv._get_config("comfyui", "workflow_file", "麦麦工作流.json")
        result = await self.inv.call_tool("get_workflow", {
            "filename": workflow_file,
            "format": "api",
        })
        if not result:
            raise WorkflowLoadError(f"获取工作流失败: workflow_file={workflow_file}")

        workflow = self.inv._parse_tool_result(result)
        if not workflow:
            raise WorkflowLoadError(f"解析工作流失败: workflow_file={workflow_file}")

        self.inv._debug_log(f"获取工作流成功，节点数: {len(workflow)}")
        return workflow

    async def _enqueue_job(self, workflow: dict, positive: str, negative: str) -> str:
        modified = self.inv.modify_workflow(workflow, positive, negative)
        result = await self.inv.call_tool("enqueue_workflow", {"workflow": modified})
        if not result:
            raise GenerationSubmitError("提交任务失败")

        prompt_id = self.inv._extract_prompt_id(result)
        if not prompt_id:
            raise GenerationSubmitError(f"获取任务 ID 失败: enqueue_result={str(result)[:200]}")

        self.inv._debug_log(f"任务已提交，prompt_id: {prompt_id}")
        return prompt_id

    async def _wait_for_completion(self, prompt_id: str) -> None:
        for i in range(60):
            await asyncio.sleep(5)

            result = await self.inv.call_tool("get_job_status", {"prompt_id": prompt_id})
            if result:
                data = self.inv._parse_tool_result(result)
                if data and data.get("done"):
                    self.inv._debug_log("任务完成")
                    return
                if data and data.get("error"):
                    raise GenerationExecutionError(
                        f"prompt_id={prompt_id}, error={data.get('error')}"
                    )

            self.inv._debug_log(f"等待中... {(i + 1) * 5}秒")

        raise GenerationTimeoutError(f"prompt_id={prompt_id}")

    async def _retrieve_image(self, prompt_id: str) -> str:
        history_result = await self.inv.call_tool("get_history", {"prompt_id": prompt_id})

        filename = self.inv._extract_filename(history_result)
        if not filename:
            raise ImageRetrievalError(f"获取图片文件名失败: prompt_id={prompt_id}")

        os.makedirs(_IMAGE_CACHE_DIR, exist_ok=True)
        save_dir = _IMAGE_CACHE_DIR
        self.inv._debug_log(f"图片缓存: {save_dir}/{filename}")
        image_result = await self.inv.call_tool("get_image", {
            "filename": filename,
            "save_dir": save_dir,
        })
        if not image_result:
            raise ImageRetrievalError(f"获取图片失败: filename={filename}")

        image_base64 = self.inv._extract_image_base64(image_result)
        if not image_base64:
            raise ImageRetrievalError(f"解析图片数据失败: filename={filename}")

        return image_base64

    # ── 提示词处理 ────────────────────────────────────────

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
            s1_max_tokens = self.inv._get_config("llm", "max_tokens_char_extract", 200)
            s2_max_tokens = self.inv._get_config("llm", "max_tokens_scene", 2000)
            s3_max_tokens = self.inv._get_config("llm", "max_tokens_char_detail", 600)

            task_name = self._resolve_task_name(model_name)
            if not task_name:
                self.logger.error(
                    f"LLM 提示词生成失败: 模型不可用 model_name={model_name}, "
                    f"用户描述={description[:100]}"
                )
                raise PromptGenerationError(f"模型不可用: {model_name}")

            # Stage 1: 低温提取角色名 (temp=0.1)
            characters = await self._extract_characters(task_name, description, s1_max_tokens)
            self.inv._debug_log(f"Stage1 角色提取结果: {characters}")

            # Stage 2a: 场景构图 (temp=0.3)
            pos_list, neg_list = await self._generate_scene_composition(
                task_name, description, characters, temperature, s2_max_tokens
            )
            self.inv._debug_log(f"Stage2a 场景构图: {len(pos_list)} tags")

            # Stage 2b: 人物特征 (temp=0.2)
            feat_list, _ = await self._generate_character_features(
                task_name, description, characters, s2_max_tokens
            )
            pos_list = pos_list + feat_list
            self.inv._debug_log(f"Stage2b 人物特征: {len(feat_list)} tags")

            # Stage 3a: 分析用户已描述的外观维度 (temp=0.1)
            covered_dims = ""
            if characters:
                covered_dims = await self._analyze_appearance(task_name, description)
                self.inv._debug_log(f"Stage3a 已覆盖维度: {covered_dims}")

            # Stage 3b: 只补充未覆盖的角色外观细节 (temp=0.15)
            if characters:
                char_details = await self._supplement_character_details(
                    task_name, characters, covered_dims, s3_max_tokens
                )
                if char_details:
                    pos_list = pos_list + char_details
                    self.inv._debug_log(f"Stage3b 角色细节补充: {len(char_details)} tags")

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
        """低温提取角色名，返回 ['character_name (series)', ...]"""
        prompt = CHARACTER_EXTRACTION_TEMPLATE.replace("<<USER_REQUEST>>", description)

        result = await llm_service.generate(
            llm_service.LLMServiceRequest(
                task_name=task_name,
                request_type="comfyui_draw_plugin.character_extractor",
                prompt=prompt,
                temperature=0.1,
                max_tokens=max_tokens,
            )
        )

        if not result.success or not result.completion.response:
            self.logger.warning(f"Stage1 角色提取失败，跳过: success={result.success}")
            return []

        try:
            resp = result.completion.response.strip()
            if resp.startswith("```"):
                lines = resp.split("\n")
                resp = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            data = json.loads(resp)
            return data.get("characters", [])
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage1 角色提取解析失败: {e}, 原始响应={resp[:200]}")
            return []

    # ── Stage 2: 场景构图 (temp=0.3) ──

    async def _generate_scene_composition(
        self,
        task_name: str,
        description: str,
        characters: list[str],
        temperature: float,
        max_tokens: int,
    ) -> tuple[str, str]:
        """正常温度生成场景、构图、光影提示词，不含角色外观细节。"""
        if characters:
            constraint = (
                "<character_constraint>\n"
                "以下角色已锁定，**必须使用、不可更改**。不要添加角色外观细节（发色、发型、服装等），后续阶段会补充：\n"
                + "\n".join(f"- {c}" for c in characters)
                + "\n</character_constraint>"
            )
        else:
            constraint = "<character_constraint>无已知角色，按原创人物处理，需自行描写外貌。</character_constraint>"

        prompt = SCENE_COMPOSITION_TEMPLATE
        prompt = prompt.replace("<<CHARACTER_CONSTRAINT>>", constraint)
        prompt = prompt.replace("<<USER_REQUEST>>", description)

        result = await llm_service.generate(
            llm_service.LLMServiceRequest(
                task_name=task_name,
                request_type="comfyui_draw_plugin.scene_composer",
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )

        if not result.success or not result.completion.response:
            self.logger.error(
                f"Stage2 场景生成失败: success={result.success}"
            )
            raise PromptGenerationError("场景生成失败")

        return self._parse_llm_response(result.completion.response.strip())

    # ── Stage 2b: 人物特征 (temp=0.2) ──

    async def _generate_character_features(
        self,
        task_name: str,
        description: str,
        characters: list[str],
        max_tokens: int,
    ) -> tuple[list[str], list[str]]:
        """低温度提取用户描述中的人物外貌、服装、动作、表情标签。"""
        if characters:
            constraint = (
                "<character_constraint>\n"
                "以下角色已锁定，**必须使用、不可更改**：\n"
                + "\n".join(f"- {c}" for c in characters)
                + "\n</character_constraint>"
            )
        else:
            constraint = "<character_constraint>无已知角色，按原创人物处理。</character_constraint>"

        prompt = CHARACTER_FEATURE_TEMPLATE
        prompt = prompt.replace("<<CHARACTER_CONSTRAINT>>", constraint)
        prompt = prompt.replace("<<USER_REQUEST>>", description)

        result = await llm_service.generate(
            llm_service.LLMServiceRequest(
                task_name=task_name,
                request_type="comfyui_draw_plugin.character_features",
                prompt=prompt,
                temperature=0.2,
                max_tokens=max_tokens,
            )
        )

        if not result.success or not result.completion.response:
            self.logger.warning(f"Stage2b 人物特征生成失败，跳过: success={result.success}")
            return [], []

        return self._parse_llm_response(result.completion.response.strip())

    # ── Stage 3a: 外观维度分析 (temp=0.1) ──

    async def _analyze_appearance(
        self, task_name: str, description: str
    ) -> str:
        """分析用户描述中已覆盖的外观维度，返回 \"已覆盖：发色、发型；详情：蓝色长发\"。"""
        prompt = APPEARANCE_ANALYSIS_TEMPLATE.replace("<<USER_REQUEST>>", description)

        result = await llm_service.generate(
            llm_service.LLMServiceRequest(
                task_name=task_name,
                request_type="comfyui_draw_plugin.appearance_analysis",
                prompt=prompt,
                temperature=0.1,
                max_tokens=200,
            )
        )

        if not result.success or not result.completion.response:
            self.logger.warning(f"Stage3a 分析失败，跳过: success={result.success}")
            return ""

        try:
            resp = result.completion.response.strip()
            if resp.startswith("```"):
                lines = resp.split("\n")
                resp = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
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
        covered_dims: str,
        max_tokens: int = 600,
    ) -> list[str]:
        """低温补充未覆盖的角色外观细节，返回标签列表。"""
        prompt = CHARACTER_DETAIL_TEMPLATE
        prompt = prompt.replace("<<CHARACTER_LIST>>", "\n".join(f"- {c}" for c in characters))
        prompt = prompt.replace("<<USER_MENTIONED>>", covered_dims)

        result = await llm_service.generate(
            llm_service.LLMServiceRequest(
                task_name=task_name,
                request_type="comfyui_draw_plugin.character_detail",
                prompt=prompt,
                temperature=0.15,
                max_tokens=max_tokens,
            )
        )

        if not result.success or not result.completion.response:
            self.logger.warning(f"Stage3 角色细节补充失败，跳过: success={result.success}")
            return []

        try:
            resp = result.completion.response.strip()
            if resp.startswith("```"):
                lines = resp.split("\n")
                resp = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            data = json.loads(resp)
            return data.get("character_positive", [])
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"Stage3 解析失败: {e}")
            return []

    def _finalize_prompts(self, pos_list: list[str], neg_list: list[str]) -> tuple[str, str]:
        """合并提示词后处理：合并人数标签、补负面词。"""
        pos_list = self.inv._ensure_quality_tags(list(pos_list))
        pos_list = merge_person_tags(pos_list)
        pos_list = list(dict.fromkeys(pos_list))
        neg_list = list(dict.fromkeys(neg_list))
        if not neg_list:
            neg_list = split_prompt_tags(DEFAULT_NEGATIVE_PROMPT)
        neg_list = self.inv._ensure_negative_tags(pos_list, neg_list)

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
        """解析 LLM JSON 响应，返回 positive, negative 标签列表。"""
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(
                    lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                )

            data = json.loads(cleaned)
            if isinstance(data, dict) and "positive" in data:
                pos = data["positive"]
                neg = data.get("negative", [])
                pos_list = list(pos) if isinstance(pos, list) else [str(pos)]
                neg_list = list(neg) if isinstance(neg, list) else ([str(neg)] if neg else [])
                return pos_list, neg_list
        except json.JSONDecodeError:
            pass

        # 回退：按行解析
        lines = [line.strip() for line in response.split("\n") if line.strip()]
        if len(lines) >= 2:
            return split_prompt_tags(lines[0]), split_prompt_tags(lines[1])
        elif len(lines) == 1:
            return split_prompt_tags(lines[0]), split_prompt_tags(DEFAULT_NEGATIVE_PROMPT)
        else:
            return ["masterpiece", "best quality", "1girl", "anime style"], split_prompt_tags(DEFAULT_NEGATIVE_PROMPT)
