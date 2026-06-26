import asyncio
import json
import re
import base64
from typing import Any, Dict, Optional
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src.services import llm_service

from .core.prompt_rules import (
    PROMPT_GENERATOR_TEMPLATE, 
    DEFAULT_NEGATIVE_PROMPT, 
    QUALITY_TAGS,
    CHARACTER_DETAIL_TAGS,
    CHARACTER_NEGATIVE_TAGS,
    NON_CHARACTER_NEGATIVE_TAGS,
    is_character_prompt,
    get_default_negative_prompt,
    merge_person_tags
)


class ComfyUIDrawInvocation:
    """ComfyUI 麦麦工作流绘图调用上下文。"""

    def __init__(self, plugin):
        self.plugin = plugin
        self.logger = plugin.ctx.logger
        self._exit_stack: Optional[AsyncExitStack] = None
        self._session: Optional[ClientSession] = None

    def _get_config(self, section: str, key: str, default=None):
        """获取配置值"""
        return self.plugin.get_config_value(section, key, default)

    def _is_debug_enabled(self) -> bool:
        return self._get_config("plugin", "debug_log", False)

    def _debug_log(self, msg: str):
        if self._is_debug_enabled():
            self.logger.info(f"[DEBUG] {msg}")

    async def connect(self):
        """连接 ComfyUI MCP 服务器"""
        try:
            host = self._get_config("comfyui", "host", "127.0.0.1")
            port = self._get_config("comfyui", "port", 8188)
            
            self._debug_log(f"连接 ComfyUI MCP: {host}:{port}")
            
            server_params = StdioServerParameters(
                command="npx",
                args=["-y", "comfyui-mcp"],
                env={
                    "COMFYUI_HOST": host,
                    "COMFYUI_PORT": str(port),
                }
            )
            
            self._exit_stack = AsyncExitStack()
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            
            # 列出可用工具
            tools_result = await self._session.list_tools()
            tools = tools_result.tools if hasattr(tools_result, 'tools') else tools_result
            self._debug_log(f"已连接 MCP 服务器，可用工具数: {len(tools)}")
            
            return True
        except Exception as e:
            self.logger.error(f"连接 MCP 服务器失败: {e}")
            return False

    async def disconnect(self):
        """断开 MCP 连接"""
        if self._exit_stack:
            await self._exit_stack.aclose()
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
            self.logger.error(f"调用 MCP 工具失败: {e}")
            return None

    async def generate_image(self, stream_id: str, description: str):
        """生成图片主流程"""
        try:
            # 1. 连接 MCP
            if not await self.connect():
                await self._send_message(stream_id, "❌ 连接 ComfyUI 失败")
                return

            # 2. 获取工作流
            workflow_file = self._get_config("comfyui", "workflow_file", "麦麦工作流.json")
            workflow_result = await self.call_tool("get_workflow", {
                "filename": workflow_file,
                "format": "api"
            })
            
            if not workflow_result:
                await self._send_message(stream_id, "❌ 获取工作流失败")
                return
            
            workflow = self._parse_tool_result(workflow_result)
            if not workflow:
                await self._send_message(stream_id, "❌ 解析工作流失败")
                return
            
            self._debug_log(f"获取工作流成功，节点数: {len(workflow)}")

            # 3. 生成提示词
            positive_prompt, negative_prompt = await self.generate_prompts_with_llm(description)
            
            if not positive_prompt:
                await self._send_message(stream_id, "❌ 提示词生成失败")
                return

            self._debug_log(f"正面提示词: {positive_prompt[:100]}")
            self._debug_log(f"负面提示词: {negative_prompt[:100]}")

            # 发送提示词给用户
            await self._send_message(
                stream_id,
                f"✅ 提示词生成成功\n\n"
                f"【正面提示词】\n{positive_prompt}\n\n"
                f"【负面提示词】\n{negative_prompt}"
            )

            # 4. 修改工作流
            modified_workflow = self.modify_workflow(workflow, positive_prompt, negative_prompt)

            # 5. 提交任务
            enqueue_result = await self.call_tool("enqueue_workflow", {
                "workflow": modified_workflow
            })
            
            if not enqueue_result:
                await self._send_message(stream_id, "❌ 提交任务失败")
                return
            
            prompt_id = self._extract_prompt_id(enqueue_result)
            if not prompt_id:
                await self._send_message(stream_id, "❌ 获取任务 ID 失败")
                return
            
            self._debug_log(f"任务已提交，prompt_id: {prompt_id}")

            # 6. 等待完成
            completed = False
            for i in range(60):
                await asyncio.sleep(5)
                
                status_result = await self.call_tool("get_job_status", {
                    "prompt_id": prompt_id
                })
                
                if status_result:
                    status_data = self._parse_tool_result(status_result)
                    if status_data and status_data.get("done"):
                        self._debug_log("任务完成")
                        completed = True
                        break
                    if status_data and status_data.get("error"):
                        await self._send_message(stream_id, "❌ 图片生成失败")
                        return
                
                self._debug_log(f"等待中... {(i+1)*5}秒")

            if not completed:
                await self._send_message(stream_id, "❌ 图片生成超时")
                return

            # 7. 获取图片
            history_result = await self.call_tool("get_history", {
                "prompt_id": prompt_id
            })
            
            filename = self._extract_filename(history_result)
            if not filename:
                await self._send_message(stream_id, "❌ 获取图片文件名失败")
                return
            
            image_result = await self.call_tool("get_image", {"filename": filename})
            if not image_result:
                await self._send_message(stream_id, "❌ 获取图片失败")
                return
            
            image_base64 = self._extract_image_base64(image_result)
            if image_base64:
                await self.plugin.ctx.send.image(image_base64, stream_id)
                await self._send_message(stream_id, f"图片生成完成！\n描述：{description}")
            else:
                await self._send_message(stream_id, "❌ 解析图片数据失败")

        except Exception as e:
            self.logger.error(f"生成图片失败: {e}")
            await self._send_message(stream_id, "❌ 图片生成失败，请稍后重试")
        finally:
            await self.disconnect()

    def _parse_tool_result(self, result) -> Optional[dict]:
        """解析 MCP 工具返回结果"""
        try:
            if hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'text'):
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
            # get_history 返回的是 Markdown 文本
            if hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'text'):
                        text = item.text
                        # 从 Markdown 中提取文件名: Node 10: images → **MaiMai__00001_.png**
                        match = re.search(r'→\s*\*\*(.+?\.png)\*\*', text)
                        if match:
                            return match.group(1)
                        # 备用: 直接搜索 .png 文件名
                        match = re.search(r'([\w_]+\.png)', text)
                        if match:
                            return match.group(1)
            return None
        except Exception as e:
            self._debug_log(f"提取文件名失败: {e}")
            return None

    def _extract_image_base64(self, result) -> Optional[str]:
        """从图片结果中提取 base64 字符串"""
        try:
            if hasattr(result, 'content'):
                for item in result.content:
                    if hasattr(item, 'type') and item.type == 'image':
                        if hasattr(item, 'data') and item.data:
                            data = item.data
                            # 修复 base64 padding
                            missing_padding = len(data) % 4
                            if missing_padding:
                                data += '=' * (4 - missing_padding)
                            return data
            return None
        except Exception as e:
            self._debug_log(f"提取图片数据失败: {e}")
            return None

    def modify_workflow(self, workflow: dict, positive_prompt: str, negative_prompt: str) -> dict:
        """修改工作流中的提示词"""
        for node_id, node in workflow.items():
            class_type = node.get("class_type", "")
            if class_type == "CLIPTextEncode":
                # 检查连接到 KSampler 的 positive 还是 negative
                for ksampler_id, ksampler in workflow.items():
                    if ksampler.get("class_type") == "KSampler":
                        inputs = ksampler.get("inputs", {})
                        positive_ref = inputs.get("positive", [])
                        negative_ref = inputs.get("negative", [])
                        
                        if isinstance(positive_ref, list) and len(positive_ref) > 0:
                            if str(positive_ref[0]) == node_id:
                                node["inputs"]["text"] = positive_prompt
                        
                        if isinstance(negative_ref, list) and len(negative_ref) > 0:
                            if str(negative_ref[0]) == node_id:
                                node["inputs"]["text"] = negative_prompt
        
        return workflow

    async def generate_prompts_with_llm(self, description: str) -> tuple[str, str]:
        """调用 LLM 生成提示词"""
        try:
            prompt = PROMPT_GENERATOR_TEMPLATE.replace("<<USER_REQUEST>>", description)
            
            model_name = self._get_config("llm", "model_name", "")
            temperature = self._get_config("llm", "temperature", 0.3)
            max_tokens = self._get_config("llm", "max_tokens", 5000)
            
            task_name = self._resolve_task_name(model_name)
            if not task_name:
                return self._generate_default_positive_prompt(description), DEFAULT_NEGATIVE_PROMPT
            
            result = await llm_service.generate(
                llm_service.LLMServiceRequest(
                    task_name=task_name,
                    request_type="comfyui_draw_plugin.prompt_generator",
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            
            if not result.success or not result.completion.response:
                return self._generate_default_positive_prompt(description), DEFAULT_NEGATIVE_PROMPT
            
            return self._parse_llm_response(result.completion.response.strip())
            
        except Exception as e:
            self.logger.error(f"LLM 调用失败: {e}")
            return self._generate_default_positive_prompt(description), DEFAULT_NEGATIVE_PROMPT

    def _resolve_task_name(self, preferred_name: str) -> str:
        try:
            models = llm_service.get_available_models()
            if preferred_name and preferred_name in models:
                return preferred_name
            for candidate in ["planner", "replyer"]:
                if candidate in models:
                    return candidate
            return next(iter(models.keys()), None)
        except:
            return None

    def _parse_llm_response(self, response: str) -> tuple[str, str]:
        try:
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            
            data = json.loads(cleaned)
            if isinstance(data, dict) and "positive" in data:
                pos = data["positive"]
                neg = data.get("negative", [])
                pos_list = list(pos) if isinstance(pos, list) else [str(pos)]
                neg_list = list(neg) if isinstance(neg, list) else ([str(neg)] if neg else [])
                pos_list = self._ensure_quality_tags(pos_list)
                pos_list = merge_person_tags(pos_list)
                if not neg_list:
                    neg_list = DEFAULT_NEGATIVE_PROMPT.split(", ")
                neg_list = self._ensure_negative_tags(pos_list, neg_list)
                return ", ".join(pos_list), ", ".join(neg_list)
        except json.JSONDecodeError:
            pass
        
        # 回退
        lines = [line.strip() for line in response.split("\n") if line.strip()]
        if len(lines) >= 2:
            pos, neg = lines[0], lines[1]
        elif len(lines) == 1:
            pos, neg = lines[0], DEFAULT_NEGATIVE_PROMPT
        else:
            pos = ", ".join(["masterpiece", "best quality", "1girl", "anime style"])
            neg = DEFAULT_NEGATIVE_PROMPT
        
        pos_list = [t.strip() for t in pos.split(",")]
        neg_list = [t.strip() for t in neg.split(",")]
        pos_list = self._ensure_quality_tags(pos_list)
        neg_list = self._ensure_negative_tags(pos_list, neg_list)
        return ", ".join(pos_list), ", ".join(neg_list)

    def _ensure_quality_tags(self, tags: list) -> list:
        """确保标签列表包含必要的质量词和细节词"""
        # 基础质量词
        required = ["masterpiece", "best quality", "ultra-detailed"]
        tags_lower = [t.lower() for t in tags]
        for tag in required:
            if tag not in tags_lower:
                tags.insert(0, tag)
        
        # 检测是否是人物类提示词
        is_character = any(
            kw in " ".join(tags).lower()
            for kw in ["girl", "boy", "woman", "man", "1girl", "1boy", "anime", "selfie", "face"]
        )
        
        # 人物类添加面部细节词
        if is_character:
            tags_lower = [t.lower() for t in tags]
            for tag in CHARACTER_DETAIL_TAGS:
                if tag not in tags_lower:
                    tags.append(tag)
        
        return tags

    def _ensure_negative_tags(self, positive_tags: list, negative_tags: list) -> list:
        is_character = any(
            kw in " ".join(positive_tags).lower() 
            for kw in ["girl", "boy", "woman", "man", "selfie", "face", "1girl", "1boy", "anime"]
        )
        required = CHARACTER_NEGATIVE_TAGS if is_character else NON_CHARACTER_NEGATIVE_TAGS
        negative_lower = [t.lower() for t in negative_tags]
        missing = [tag for tag in required if tag not in negative_lower]
        if missing:
            negative_tags = missing + negative_tags
        return negative_tags

    def _generate_default_positive_prompt(self, description: str) -> str:
        base = ["masterpiece", "best quality", "highly detailed", "ultra-detailed", "8k", "1girl", "beautiful face", "smile", "anime style"]
        if description:
            base.append(description)
        return ", ".join(base)

    async def _send_message(self, stream_id: str, text: str):
        await self.plugin.ctx.send.text(text, stream_id)
