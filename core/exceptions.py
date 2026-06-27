# -*- coding: utf-8 -*-
"""异常类定义。"""

class ComfyUIDrawError(Exception):
    """插件内部错误基类。"""

class ComfyUIConnectionError(ComfyUIDrawError):
    """连接 ComfyUI MCP 服务器失败。"""

class WorkflowLoadError(ComfyUIDrawError):
    """工作流获取或解析失败。"""

class PromptGenerationError(ComfyUIDrawError):
    """LLM 提示词生成失败。"""

class GenerationSubmitError(ComfyUIDrawError):
    """任务提交失败。"""

class GenerationExecutionError(ComfyUIDrawError):
    """图片生成执行失败。"""

class GenerationTimeoutError(ComfyUIDrawError):
    """图片生成超时。"""

class ImageRetrievalError(ComfyUIDrawError):
    """图片获取或解析失败。"""
