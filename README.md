# ComfyUI 麦麦工作流绘图插件

通过 MCP 直接连接 ComfyUI，使用麦麦工作流生成图片的 MaiBot 插件。

## 功能

- `/生图 <描述>` - 使用 ComfyUI 生成图片（支持自然语言描述）
- `/生图 -p <正面提示词> -n <负面提示词>` - 直接使用提示词生成（跳过 LLM）
- `/生图帮助` - 显示帮助信息
- LLM 自动将中文描述转换为英文提示词
- 自动识别工作流节点（正面/负面提示词、输出节点）
- 自动为人物类图片添加面部细节词
- 自动合并重复的 1girl/1boy 标签

## 安装

1. 复制 `comfyui_draw_plugin` 目录到 MaiBot 的 `plugins/` 目录
2. 确保 ComfyUI 服务正在运行
3. 确保 `npx` 可用（用于启动 MCP 服务器）
4. 启动 MaiBot，插件会自动加载

## 配置

配置文件 `config.toml` 会在首次启动时自动生成，可通过 MaiBot WebUI 编辑。

```toml
[plugin]
config_version = "1.0.2"
command_name = "生图"  # 触发命令名（修改后需重启插件）
enabled = true
debug_log = false  # 调试日志开关

[comfyui]
host = "127.0.0.1"       # ComfyUI 服务地址
port = 8188              # ComfyUI 服务端口
workflow_file = "麦麦工作流.json"  # 工作流文件名

[llm]
model_name = "deepseek-v4-pro"  # 提示词生成使用的模型标识符
temperature = 0.3               # LLM 温度
max_tokens = 5000               # LLM 响应的最大 token
```

## 使用方法

```
# LLM 解析模式（自动翻译中文描述）
/生图 一个可爱的女孩，蓝色头发，微笑
/生图 樱花树下的少女，动漫风格
/生图 恰斯卡  # 原神角色，会自动补充角色特征

# 直接提示词模式（跳过 LLM，适用于已知提示词）
/生图 -p 1girl, blue hair, smile -n low quality, blurry
/生图 -p masterpiece, 1girl, cherry blossoms, anime style

/生图帮助
```
# LLM 解析模式（自动翻译中文描述）
/生图 一个可爱的女孩，蓝色头发，微笑
/生图 樱花树下的少女，动漫风格
/生图 恰斯卡  # 原神角色，会自动补充角色特征
/生图 两个女孩在喝咖啡  # 多人场景

# 直接提示词模式（跳过 LLM，适用于已知提示词）
/生图 /p 1girl, blue hair, smile, school uniform /n low quality, blurry
/生图 /p masterpiece, 1girl, cherry blossoms, anime style
/生图直接 /p 1girl, long hair, looking at viewer /n deformed, ugly

/生图帮助
```

## 工作原理

1. 用户输入中文描述
2. LLM 将描述转换为英文提示词（JSON 格式）
3. 通过 MCP 获取麦麦工作流
4. 自动识别工作流中的正/负面提示词节点
5. 修改提示词并提交到 ComfyUI
6. 等待生成完成并获取图片
7. 发送图片给用户

## 提示词规则

- 已知角色：使用 `character_name (series)` 格式，自动增加权重
- 人物类：自动添加 `detailed face, detailed eyes, beautiful detailed hair`
- 质量词：自动确保包含 `masterpiece, best quality, ultra-detailed`
- 多人场景：自动合并重复的 `1girl`/`1boy` 为 `2girls`/`3girls`

## 依赖

- MaiBot SDK 2.0+
- ComfyUI 服务
- `mcp` Python SDK（MaiBot 自带）
- `npx`（用于启动 comfyui-mcp）

## 注意事项

1. 确保 ComfyUI 服务正在运行
2. 确保 `麦麦工作流.json` 工作流文件存在于 ComfyUI 的 workflows 目录
3. 生成时间约 20-30 秒，取决于 GPU 性能
4. 启用 `debug_log` 可查看详细的生成过程日志
