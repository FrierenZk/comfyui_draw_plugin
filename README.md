# ComfyUI 麦麦工作流绘图插件

通过 MCP 连接 ComfyUI，使用五阶段 LLM 管线将中文描述转换为高质量英文 SD 提示词并生成图片的 MaiBot 插件。

## 功能

- `/生图 <描述>` — LLM 自动将中文描述转换为英文提示词，智能识别角色/服装/场景
- `/生图 -p <正面> -n <负面>` — 直接使用提示词生成（跳过 LLM 解析）
- `/切换工作流 <名称>` — 切换当前对话的工作流（仅影响当前对话，不干扰其他对话）
- `/工作流列表` — 查看当前及备选工作流
- `/生图帮助` — 显示帮助信息

### 提示词生成能力

- **角色识别**：自动识别已知动漫/游戏角色，输出 `(character_name (series):1.05)` 格式
- **服装提取**：识别用户指定的服装/配饰（丝袜、帽子、JK制服等），自动加权 `(tag:1.1)`
- **场景推导**：根据描述合情合理推导构图、环境、光影，用户描述优先
- **风格识别**：支持动漫/3D渲染/写实/油画等多种风格
- **负面标签**：自动生成语境负面词（风格对立、用户明确排除项）
- **多人场景**：自动合并 `1girl`/`1boy` 为 `2girls`/`3girls`
- **缓存加速**：分级过期缓存（3→7→30→90天），减少重复搜索
- **并发优化**：S1三提取并行、预搜索与场景构图并行、S3角色与服装补充并行

## 安装

1. 复制 `comfyui_draw_plugin` 目录到 MaiBot 的 `plugins/` 目录
2. 确保 ComfyUI 服务正在运行
3. 确保 `npx` 可用（用于启动 comfyui-mcp）
4. 启动 MaiBot，插件会自动加载

## 配置

配置文件 `config.toml` 会在首次启动时自动生成，可通过 MaiBot WebUI 编辑。

```toml
[plugin]
config_version = "1.1.2"
command_name = "生图"                 # 触发命令名
switch_workflow_command = "切换工作流"
list_workflow_command = "工作流列表"
enabled = true
debug_log = false                     # 调试日志（包含各阶段 LLM 输出）

[comfyui]
host = "127.0.0.1"                   # ComfyUI 服务地址
port = 8188                          # ComfyUI 服务端口
workflow_file = "麦麦工作流.json"     # 默认工作流
optional_workflows = []              # 备选工作流列表
generation_timeout = 300             # 生图超时秒数（每 5 秒轮询）

[llm]
model_name = "deepseek-v4-pro"       # 模型标识符
temperature = 0.3                    # S2 阶段温度（S1/S3 固定 0.1/0.15）
max_tokens_char_extract = 2000       # S1 角色/服装提取
max_tokens_scene = 5000              # S2 场景构图/人物特征
max_tokens_char_detail = 5000        # S3 细节补充
# Anthropic SDK 直连（可选，不配则走 MaiBot 旧 API）
use_anthropic_api = false
anthropic_api_key = ""
anthropic_base_url = "https://api.deepseek.com/anthropic"
```

## 使用方法

```
# LLM 解析模式
/生图 一个可爱的女孩，蓝色头发，微笑
/生图 初音未来穿丝袜在咖啡厅喝咖啡
/生图 樱花树下的少女，动漫风格
/生图 桑多涅喝茶，3D渲染，增强丝袜质感

# 直接提示词模式
/生图 -p 1girl, blue hair, smile -n low quality, blurry
/生图 -p masterpiece, 1girl, cherry blossoms, anime style

# 工作流切换
/切换工作流 麦麦工作流2
/工作流列表
/生图帮助
```

## 提示词规则

- 角色：使用 `(character_name (series):1.05)` 格式，自动加权
- 服装：用户指定的服装标签自动加权 `(tag:1.1)`，展开的细节标签不加权
- 质量词：自动确保包含 `masterpiece, best quality, ultra-detailed`
- 负面词：系统默认负面 + LLM 上下文补充（风格对立、排除项）
- 景别：角色为主默认近景（cowboy shot），用户指定景别优先

## 依赖

- MaiBot SDK 2.0+
- ComfyUI 服务
- `npx`（comfyui-mcp）
- Anthropic SDK（可选，直连时使用）

## 工作流支持

插件通过 MCP 读取 ComfyUI 工作流，自动识别正/负面 CLIPTextEncode 节点（代码→缓存→LLM 三级回退），兼容多种工作流结构。
