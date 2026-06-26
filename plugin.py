from typing import Any, ClassVar, Iterable
import re

from maibot_sdk import MaiBotPlugin, PluginConfigBase, Field, Command

from .sdk_runtime import ComfyUIDrawInvocation


# ==================== 配置模型 ====================

class PluginSection(PluginConfigBase):
    """插件基础配置"""
    __ui_label__ = "基础设置"

    config_version: str = Field(default="1.0.0", description="配置版本号")
    enabled: bool = Field(default=True, description="是否启用插件")
    debug_log: bool = Field(default=False, description="是否启用调试日志")


class ComfyUISection(PluginConfigBase):
    """ComfyUI 连接配置"""
    __ui_label__ = "ComfyUI 设置"

    host: str = Field(
        default="127.0.0.1",
        description="ComfyUI 服务地址"
    )
    port: int = Field(
        default=8188,
        description="ComfyUI 服务端口"
    )
    workflow_file: str = Field(
        default="麦麦工作流.json",
        description="工作流文件名"
    )


class LLMSection(PluginConfigBase):
    """LLM 配置"""
    __ui_label__ = "LLM 设置"

    model_name: str = Field(default="deepseek-v4-pro", description="提示词生成使用的模型标识符")
    temperature: float = Field(default=0.3, description="LLM 温度；常用 0.2~1.0，越高越发散")
    max_tokens: int = Field(default=5000, description="LLM 响应的最大 token")


class ComfyUIDrawPluginConfig(PluginConfigBase):
    """插件完整配置"""
    __ui_label__ = "ComfyUI 麦麦工作流绘图插件"

    plugin: PluginSection = Field(default_factory=PluginSection)
    comfyui: ComfyUISection = Field(default_factory=ComfyUISection)
    llm: LLMSection = Field(default_factory=LLMSection)


# ==================== 插件类 ====================


class ComfyUIDrawPlugin(MaiBotPlugin):
    """通过 MCP 连接 ComfyUI，使用麦麦工作流生成图片的插件。"""

    config_model = ComfyUIDrawPluginConfig

    def __init__(self):
        super().__init__()
        self.invocation = None

    async def on_load(self) -> None:
        """插件加载时初始化"""
        self.invocation = ComfyUIDrawInvocation(self)
        self.ctx.logger.info("ComfyUI 麦麦工作流绘图插件已加载")

    async def on_unload(self) -> None:
        """插件卸载时清理"""
        self.invocation = None
        self.ctx.logger.info("ComfyUI 麦麦工作流绘图插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        """配置热重载回调"""
        self.ctx.logger.info("插件配置已更新: scope=%s, version=%s", scope, version)

    def get_config_value(self, section: str, key: str, default=None):
        """获取配置值，兼容强类型配置和原始字典"""
        try:
            section_obj = getattr(self.config, section, None)
            if section_obj is not None:
                return getattr(section_obj, key, default)
        except RuntimeError:
            pass
        raw = self.get_plugin_config_data()
        return raw.get(section, {}).get(key, default)

    # ==================== Command ====================

    @Command(
        "生图",
        description="使用 ComfyUI 麦麦工作流生成图片",
        pattern=r"^/生图\s*(?P<description>.+)$"
    )
    async def handle_draw_command(self, **kwargs):
        """处理 /生图 命令"""
        stream_id = kwargs.get("stream_id", "")
        matched_groups = kwargs.get("matched_groups", {})
        description = matched_groups.get("description", "").strip()

        if not description:
            await self.ctx.send.text("请提供描述，例如：/生图 一个可爱的女孩", stream_id)
            return False, "缺少描述", 1

        if not self.invocation:
            await self.ctx.send.text("插件未初始化，请稍后再试", stream_id)
            return False, "插件未初始化", 1

        # 直接调用 MCP 工具生成图片
        await self.invocation.generate_image(stream_id, description)
        return True, "图片生成中", 2

    @Command(
        "生图帮助",
        description="显示生图插件帮助",
        pattern=r"^/生图帮助$"
    )
    async def handle_help_command(self, **kwargs):
        """处理 /生图帮助 命令"""
        stream_id = kwargs.get("stream_id", "")
        help_text = (
            "ComfyUI 麦麦工作流绘图插件\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "命令：\n"
            "  /生图 <描述> - 生成图片\n"
            "  /生图帮助 - 显示此帮助\n"
            "\n"
            "示例：\n"
            "  /生图 一个可爱的女孩，蓝色头发，微笑\n"
            "  /生图 樱花树下的少女，动漫风格\n"
        )
        await self.ctx.send.text(help_text, stream_id)
        return True, "帮助信息已发送", 1


def create_plugin():
    return ComfyUIDrawPlugin()
