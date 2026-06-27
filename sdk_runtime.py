import asyncio
import json
import re
import base64
from typing import Any, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .core.prompt_rules import (
    CHARACTER_DETAIL_TAGS,
    CHARACTER_NEGATIVE_TAGS,
    NON_CHARACTER_NEGATIVE_TAGS,
)
from .core.generation import (
    ComfyUIConnectionError,
    ComfyUIDrawGenerator,
)


class ComfyUIDrawInvocation:
    """ComfyUI MCP 连接和工具层。生成流程委托给 ComfyUIDrawGenerator。"""

    def __init__(self, plugin):
        self.plugin = plugin
        self.logger = plugin.ctx.logger
        self._exit_stack: Optional[AsyncExitStack] = None
        self._session: Optional[ClientSession] = None
        self._generator = ComfyUIDrawGenerator(self)

    # ── 配置 / 调试 ─────────────────────────────────────────

    def _get_config(self, section: str, key: str, default=None):
        return self.plugin.get_config_value(section, key, default)

    def _is_debug_enabled(self) -> bool:
        return self._get_config("plugin", "debug_log", False)

    def _debug_log(self, msg: str):
        if self._is_debug_enabled():
            self.logger.info(f"[DEBUG] {msg}")

    async def _send_message(self, stream_id: str, text: str):
        await self.plugin.ctx.send.text(text, stream_id)

    # ── MCP 连接 ────────────────────────────────────────────

    async def connect(self):
        """连接 ComfyUI MCP 服务器"""
        host = self._get_config("comfyui", "host", "127.0.0.1")
        port = self._get_config("comfyui", "port", 8188)

        try:
            self._debug_log(f"连接 ComfyUI MCP: {host}:{port}")

            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "comfyui-mcp"],
                env={
                    "COMFYUI_HOST": host,
                    "COMFYUI_PORT": str(port),
                },
            )

            self._exit_stack = AsyncExitStack()
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()

            tools_result = await self._session.list_tools()
            tools = tools_result.tools if hasattr(tools_result, "tools") else tools_result
            self._debug_log(f"已连接 MCP 服务器，可用工具数: {len(tools)}")

        except Exception as e:
            self.logger.error(
                f"连接 MCP 服务器失败: host={host}, port={port}, "
                f"error={type(e).__name__}: {e}"
            )
            raise ComfyUIConnectionError(f"host={host}, port={port}") from e

    async def disconnect(self):
        """断开 MCP 连接"""
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except RuntimeError:
                pass
            finally:
                self._exit_stack = None
                self._session = None

    async def call_tool(self, tool_name: str, arguments: dict) -> Optional[Any]:
        """调用 MCP 工具"""
        if not self._session:
            self.logger.error("MCP 未连接")
            return None

        try:
            self._debug_log(f"调用 MCP 工具: {tool_name}, 参数: {arguments}")
            result = await self._session.call_tool(tool_name, arguments)
            self._debug_log(f"MCP 工具结果: {str(result)[:200]}")
            return result
        except Exception as e:
            self.logger.error(
                f"调用 MCP 工具失败: tool={tool_name}, args={arguments}, "
                f"error={type(e).__name__}: {e}"
            )
            return None

    # ── MCP 结果解析 ────────────────────────────────────────

    def _parse_tool_result(self, result) -> Optional[dict]:
        """解析 MCP 工具返回结果"""
        try:
            if hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "text"):
                        return json.loads(item.text)
            if isinstance(result, dict):
                return result
            return None
        except Exception as e:
            self._debug_log(f"解析工具结果失败: {e}")
            return None

    def _extract_prompt_id(self, result) -> Optional[str]:
        """从提交结果中提取 prompt_id"""
        data = self._parse_tool_result(result)
        if data:
            return data.get("prompt_id")
        return None

    def _extract_filename(self, result) -> Optional[str]:
        """从历史记录中提取图片文件名"""
        try:
            if hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "text"):
                        text = item.text
                        match = re.search(r"→\s*\*\*(.+?\.png)\*\*", text)
                        if match:
                            return match.group(1)
                        match = re.search(r"([\w_]+\.png)", text)
                        if match:
                            return match.group(1)
            return None
        except Exception as e:
            self._debug_log(f"提取文件名失败: {e}")
            return None

    def _extract_image_base64(self, result) -> Optional[str]:
        """从图片结果中提取 base64 字符串"""
        try:
            if hasattr(result, "content"):
                for item in result.content:
                    if hasattr(item, "type") and item.type == "image":
                        if hasattr(item, "data") and item.data:
                            data = item.data
                            missing_padding = len(data) % 4
                            if missing_padding:
                                data += "=" * (4 - missing_padding)
                            return data
            return None
        except Exception as e:
            self._debug_log(f"提取图片数据失败: {e}")
            return None

    # ── 工作流修改 ──────────────────────────────────────────

    def _detect_prompt_nodes_by_code(self, workflow: dict) -> tuple[str | None, str | None]:
        """通过 KSampler 连接关系检测正/负面 CLIPTextEncode 节点 ID。"""
        pos_node = neg_node = None
        for node_id, node in workflow.items():
            if node.get("class_type") == "KSampler":
                inputs = node.get("inputs", {})
                for key, ref in (("positive", "pos_node"), ("negative", "neg_node")):
                    ref_list = inputs.get(key, [])
                    if isinstance(ref_list, list) and ref_list:
                        node_id_str = str(ref_list[0])
                        target = workflow.get(node_id_str, {})
                        if target.get("class_type") == "CLIPTextEncode":
                            if key == "positive":
                                pos_node = node_id_str
                            else:
                                neg_node = node_id_str
        return pos_node, neg_node

    def modify_workflow(
        self,
        workflow: dict,
        positive_prompt: str,
        negative_prompt: str,
        positive_node: str | None = None,
        negative_node: str | None = None,
    ) -> dict:
        """修改工作流中的提示词。传入 node ID 则直接注入；否则自动检测 KSampler 连接。"""
        if positive_node:
            node = workflow.get(positive_node)
            if node and node.get("class_type") == "CLIPTextEncode":
                node["inputs"]["text"] = positive_prompt
        if negative_node:
            node = workflow.get(negative_node)
            if node and node.get("class_type") == "CLIPTextEncode":
                node["inputs"]["text"] = negative_prompt
        if positive_node or negative_node:
            return workflow

        # 回退：自动检测（兼容旧逻辑）
        pos_node, neg_node = self._detect_prompt_nodes_by_code(workflow)
        if pos_node:
            workflow[pos_node]["inputs"]["text"] = positive_prompt
        if neg_node:
            workflow[neg_node]["inputs"]["text"] = negative_prompt
        return workflow

    # ── 提示词工具 ──────────────────────────────────────────

    def _ensure_quality_tags(self, tags: list) -> list:
        """确保标签列表包含必要的质量词和细节词"""
        required = ["masterpiece", "best quality", "ultra-detailed"]
        tags_lower = [t.lower() for t in tags]
        for tag in required:
            if tag not in tags_lower:
                tags.insert(0, tag)

        is_character = any(
            kw in " ".join(tags).lower()
            for kw in [
                "girl", "boy", "woman", "man", "1girl", "1boy",
                "anime", "selfie", "face",
            ]
        )

        if is_character:
            tags_lower = [t.lower() for t in tags]
            for tag in CHARACTER_DETAIL_TAGS:
                if tag not in tags_lower:
                    tags.append(tag)

        return tags

    def _ensure_negative_tags(self, positive_tags: list, negative_tags: list) -> list:
        is_character = any(
            kw in " ".join(positive_tags).lower()
            for kw in [
                "girl", "boy", "woman", "man", "selfie", "face",
                "1girl", "1boy", "anime",
            ]
        )
        required = CHARACTER_NEGATIVE_TAGS if is_character else NON_CHARACTER_NEGATIVE_TAGS
        negative_lower = [t.lower() for t in negative_tags]
        missing = [tag for tag in required if tag not in negative_lower]
        if missing:
            negative_tags = missing + negative_tags
        return negative_tags

    # ── 公开入口（委托给 ComfyUIDrawGenerator） ──────────────

    async def generate_image(self, stream_id: str, description: str) -> None:
        """LLM 翻译描述 → 提示词 → 生成图片。"""
        await self._generator.generate_image(stream_id, description)

    async def generate_image_with_prompts(
        self, stream_id: str, positive_prompt: str, negative_prompt: str
    ) -> None:
        """直接使用提示词生成图片（跳过 LLM）。"""
        await self._generator.generate_image_with_prompts(
            stream_id, positive_prompt, negative_prompt
        )
