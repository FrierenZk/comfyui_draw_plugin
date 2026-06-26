"""ComfyUI 麦麦工作流绘图插件。"""

__all__ = ["ComfyUIDrawPlugin"]


def __getattr__(name: str):
    if name == "ComfyUIDrawPlugin":
        from .plugin import ComfyUIDrawPlugin

        return ComfyUIDrawPlugin
    raise AttributeError(name)
