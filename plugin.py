from typing import Any, ClassVar, Iterable
import re
import asyncio

from maibot_sdk import MaiBotPlugin, PluginConfigBase, Field, Command

from .sdk_runtime import ComfyUIDrawInvocation


# ==================== 命令名常量（模块导入时从 config.toml 读取，与 PluginSection.command_name 默认值一致） ====================

def _get_command_name() -> str:
    import os as _os
    _path = _os.path.join(_os.path.dirname(__file__), "config.toml")
    try:
        with open(_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _m = re.match(r'^\s*command_name\s*=\s*"(.+)"', _line)
                if _m:
                    return _m.group(1)
    except Exception:
        pass
    return "生图"


COMMAND_NAME = _get_command_name()


# ==================== 配置模型 ====================

class PluginSection(PluginConfigBase):
    """插件基础配置"""
    __ui_label__ = "基础设置"

    config_version: str = Field(default="1.1.0", description="配置版本号")
    command_name: str = Field(default=COMMAND_NAME, description="触发命令名（修改后需重启插件）")
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

    model_name: str = Field(default="deepseek-v4-pro", description="模型标识符（Anthropic 直连时用作 model ID）")
    temperature: float = Field(default=0.3, description="LLM 温度；常用 0.2~1.0，越高越发散")
    max_tokens_char_extract: int = Field(default=1500, description="Stage1 角色名提取最大 token")
    max_tokens_scene: int = Field(default=2500, description="Stage2 场景构图最大 token")
    max_tokens_char_detail: int = Field(default=4000, description="Stage3 角色细节补充最大 token")
    # Anthropic SDK 直连
    use_anthropic_api: bool = Field(default=False, description="启用 Anthropic SDK 直连", json_schema_extra={"x-widget": "switch"})
    anthropic_api_key: str = Field(default="", description="Anthropic API Key（留空则读 ANTHROPIC_API_KEY 环境变量）", json_schema_extra={"x-widget": "password"})
    anthropic_base_url: str = Field(default="https://api.deepseek.com/anthropic", description="Anthropic API 端点")
    anthropic_env: list[str] = Field(default_factory=list, description="Anthropic 额外环境变量，格式 KEY=VALUE")


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
        cmd = self._get_cmd()
        self.ctx.logger.info(
            f"ComfyUI 麦麦工作流绘图插件已加载, command_name=/{cmd}"
        )

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

    def _get_cmd(self) -> str:
        """获取当前配置的命令名"""
        return self.get_config_value("plugin", "command_name", COMMAND_NAME)

    # ==================== Command ====================

    @Command(
        COMMAND_NAME,
        description="使用 ComfyUI 麦麦工作流生成图片",
        pattern=rf"^/{COMMAND_NAME}(?=\s|$)"
    )
    async def handle_draw_command(self, **kwargs):
        """处理 /生图 命令"""
        cmd = self._get_cmd()
        stream_id = kwargs.get("stream_id", "")
        text = kwargs.get("text", "").strip()

        content = text
        prefix = f"/{cmd}"
        if content.startswith(prefix):
            content = content[len(prefix):].strip()

        if not content:
            await self.ctx.send.text(f"请提供描述，例如：/{cmd} 一个可爱的女孩", stream_id)
            return False, "缺少描述", 1

        if not self.invocation:
            await self.ctx.send.text("插件未初始化，请稍后再试", stream_id)
            return False, "插件未初始化", 1

        positive, negative = self._parse_direct_prompts(content)
        if positive:
            asyncio.create_task(self._run_draw(stream_id, positive, negative or "", direct=True))
        else:
            asyncio.create_task(self._run_draw(stream_id, content, "", direct=False))
        return True, "图片生成中", 2

    async def _run_draw(self, stream_id: str, positive: str, negative: str, direct: bool):
        """在独立 task 中执行图片生成"""
        invocation = ComfyUIDrawInvocation(self)
        try:
            if direct:
                await invocation.generate_image_with_prompts(stream_id, positive, negative)
            else:
                await invocation.generate_image(stream_id, positive)
        except Exception as e:
            cmd = self._get_cmd()
            self.ctx.logger.error(f"[{cmd}] task 异常: {e}")

    def _parse_direct_prompts(self, content: str) -> tuple:
        """解析 -p 或 /p 正面 -n 或 /n 负面 格式"""
        cleaned = re.sub(r'\s+', ' ', content).strip()
        match = re.search(r'[-/]p\s+(.+?)(?:\s+[-/]n\s+(.+))?$', cleaned)
        if match:
            positive = match.group(1).strip().rstrip(',').strip()
            negative = match.group(2).strip().rstrip(',').strip() if match.group(2) else ""
            return positive, negative
        return None, None

    @Command(
        f"{COMMAND_NAME}帮助",
        description="显示生图插件帮助",
        pattern=rf"^/{COMMAND_NAME}帮助$"
    )
    async def handle_help_command(self, **kwargs):
        """处理 /生图帮助 命令"""
        cmd = self._get_cmd()
        stream_id = kwargs.get("stream_id", "")
        help_text = (
            "ComfyUI 麦麦工作流绘图插件\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "命令：\n"
            f"  /{cmd} <描述> - LLM 解析后生成图片\n"
            f"  /{cmd} -p <正面> -n <负面> - 直接使用提示词\n"
            f"  /{cmd}帮助 - 显示此帮助\n"
            "\n"
            "示例：\n"
            f"  /{cmd} 一个可爱的女孩，蓝色头发\n"
            f"  /{cmd} -p 1girl, blue hair -n low quality\n"
        )
        await self.ctx.send.text(help_text, stream_id)
        return True, "帮助信息已发送", 1


def create_plugin():
    return ComfyUIDrawPlugin()
