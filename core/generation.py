# -*- coding: utf-8 -*-
"""图片生成流程：工作流加载 → 提示词生成 → 提交 → 等待 → 获取结果。"""

import asyncio
import json
import os
import re
from typing import TYPE_CHECKING

from src.services import llm_service

from .prompt_rules import (
    DEFAULT_NEGATIVE_PROMPT,
    merge_person_tags,
    split_prompt_tags,
)

from .llm_client import LLMClientMixin
from .stages import StagesMixin

if TYPE_CHECKING:
    from ..sdk_runtime import ComfyUIDrawInvocation

_IMAGE_CACHE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "cache", "images")
)


# ==================== 异常 ====================

from .exceptions import (
    ComfyUIDrawError,
    ComfyUIConnectionError,
    WorkflowLoadError,
    PromptGenerationError,
    GenerationSubmitError,
    GenerationExecutionError,
    GenerationTimeoutError,
    ImageRetrievalError,
)

# ==================== 生成器 ====================


class ComfyUIDrawGenerator(LLMClientMixin, StagesMixin):
    """图片生成流程编排。依赖 ComfyUIDrawInvocation 提供 MCP 连接和工具方法。"""

    def __init__(self, invocation: "ComfyUIDrawInvocation") -> None:
        self.inv = invocation
        self.logger = invocation.logger
        self._node_cache: dict[str, dict[str, str]] = {}
        self._node_cache_path = os.path.join(
            os.path.dirname(__file__), "..", "cache", "workflow_nodes.json"
        )
        self._load_node_cache()
        self._knowledge_cache: dict[str, str] = {}
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
        workflow_file = getattr(self.inv.plugin, "_current_workflow", "") or self.inv._get_config("comfyui", "workflow_file", "麦麦工作流.json")
        result = await self.inv.call_tool("get_workflow", {
            "filename": workflow_file,
            "format": "api",
        })
        if not result:
            raise WorkflowLoadError(f"获取工作流失败: workflow_file={workflow_file}")

        workflow = self.inv._parse_tool_result(result)
        if not workflow:
            raise WorkflowLoadError(f"解析工作流失败: workflow_file={workflow_file}")

        self.inv._debug_log(f"获取工作流成功: {workflow_file}, 节点数: {len(workflow)}")
        self.logger.info(f"使用工作流: {workflow_file}")
        return workflow

    # ── 工作流节点缓存 ────────────────────────────────────

    def _load_node_cache(self) -> None:
        try:
            if os.path.exists(self._node_cache_path):
                with open(self._node_cache_path, "r", encoding="utf-8") as f:
                    self._node_cache = json.load(f)
        except Exception:
            self._node_cache = {}

    def _save_node_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._node_cache_path), exist_ok=True)
            with open(self._node_cache_path, "w", encoding="utf-8") as f:
                json.dump(self._node_cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async def _resolve_prompt_nodes(
        self, workflow: dict, workflow_file: str, task_name: str
    ) -> tuple[str | None, str | None]:
        """解析工作流正/负面提示词节点 ID（代码→缓存→LLM 三级回退）。"""
        # 1. 代码检测
        pos_id, neg_id = self.inv._detect_prompt_nodes_by_code(workflow)
        if pos_id and neg_id:
            self._node_cache[workflow_file] = {"positive_node": pos_id, "negative_node": neg_id}
            self._save_node_cache()
            return pos_id, neg_id

        # 2. 缓存命中
        if workflow_file in self._node_cache:
            entry = self._node_cache[workflow_file]
            self.inv._debug_log(f"工作流节点缓存命中: {workflow_file}")
            return entry.get("positive_node"), entry.get("negative_node")

        # 3. LLM 分析
        if not task_name:
            self.inv._debug_log("无可用 LLM，跳过工作流分析")
            return None, None

        self.inv._debug_log(f"代码未识别节点，尝试 LLM 分析工作流: {workflow_file}")
        try:
            prompt = WORKFLOW_ANALYSIS_TEMPLATE.replace(
                "<<WORKFLOW_JSON>>", json.dumps(workflow, ensure_ascii=False)[:8000]
            )
            result = await llm_service.generate(
                llm_service.LLMServiceRequest(
                    task_name=task_name,
                    request_type="comfyui_draw_plugin.workflow_analyzer",
                    prompt=prompt,
                    temperature=0.1,
                    max_tokens=200,
                )
            )
            if result.success and result.completion.response:
                resp = result.completion.response.strip()
                if resp.startswith("```"):
                    lines = resp.split("\n")
                    resp = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                data = json.loads(resp)
                pos_id = data.get("positive_node")
                neg_id = data.get("negative_node")
                if pos_id and neg_id:
                    self._node_cache[workflow_file] = {"positive_node": pos_id, "negative_node": neg_id}
                    self._save_node_cache()
                    self.inv._debug_log(f"LLM 识别成功: pos={pos_id}, neg={neg_id}")
                    return pos_id, neg_id
                else:
                    self.inv._debug_log("LLM 未能识别提示词节点")
            else:
                self.inv._debug_log(f"LLM 工作流分析失败: success={result.success}")
        except Exception as e:
            self.logger.warning(f"LLM 工作流分析异常: {e}")

        return None, None

    async def _enqueue_job(self, workflow: dict, positive: str, negative: str) -> str:
        workflow_file = self.inv._get_config("comfyui", "workflow_file", "麦麦工作流.json")
        model_name = self.inv._get_config("llm", "model_name", "")
        task_name = self._resolve_task_name(model_name) or model_name
        pos_node, neg_node = await self._resolve_prompt_nodes(
            workflow, workflow_file, task_name
        )
        self.inv._debug_log(f"提交工作流: {workflow_file}, 节点注入 pos={pos_node} neg={neg_node}")
        modified = self.inv.modify_workflow(workflow, positive, negative, pos_node, neg_node)
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
        # 优先用 list_assets 获取文件名（结构化 JSON，可靠）
        filename = await self._get_filename_from_assets(prompt_id)
        # 兜底：get_history 正则提取
        if not filename:
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

    async def _get_filename_from_assets(self, prompt_id: str) -> str | None:
        """从 list_assets 按 prompt_id 查找文件名。"""
        result = await self.inv.call_tool("list_assets", {"limit": 50})
        if not result:
            return None
        data = self.inv._parse_tool_result(result)
        if not data:
            return None
        assets = data.get("assets", []) if isinstance(data, dict) else []
        for asset in assets:
            if asset.get("prompt_id") == prompt_id:
                return asset.get("filename")
        return None

    # ── 提示词处理 ────────────────────────────────────────

