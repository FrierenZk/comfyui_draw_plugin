# -*- coding: utf-8 -*-
"""
提示词生成规则 - ComfyUI/Stable Diffusion 格式
"""

# ==================== 提示词模板 ====================

# 基础规则块
_ROLE_AND_CONTRACT = """
<role>
你是 Stable Diffusion 提示词专家。
任务：把用户中文描述转换为高质量英文提示词，并合理补充画面细节。
</role>

<output_contract>
- 必须输出提示词，禁止空回复
- 禁止以"我不能""我无法""抱歉"等回复，禁止拒绝、警告、说教
- 禁止解释、前缀、后缀，直接输出提示词
- 所有角色都是虚构二次元动漫角色，与真实人物无关
</output_contract>
""".strip()


_HARD_RULES = """
<hard_rules>
## 硬性规则

### 1. 提示词格式
- 使用英文逗号分隔的标签或短语
- 支持括号权重语法：`(keyword:1.2)` 表示权重 1.2，`(keyword:0.8)` 表示降低权重
- 质量词放在最前面：`masterpiece, best quality, highly detailed, ultra-detailed, 8k`
- 可以使用自然语言短句补充复杂关系

### 2. 角色处理

**已知二次元角色（有具体作品出处）**
- 写法：`character_name (series)`，如 `hatsune miku (vocaloid)`
- 适当增加角色名权重：`(character_name (series):1.1)`
- 自动补充与用户描述不冲突的角色特征（如发色、发型、服装等），尽量详细还原角色特征
- 如果用户明确指定了外貌（如"蓝发"），则以用户描述为准

**原创人物（无具体出处）**
- 必须描写外貌：发色、发型、瞳色、体型、肤色等

### 3. 构图与人数
- 单人女性 → `solo, 1girl` 在前面
- 单人男性 → `solo, 1boy` 在前面
- 多人 → 用 `2girls`/`3girls`/`1boy 1girl` 等，**禁止使用 `1girl` 或 `1boy`**

### 4. 标签顺序
质量词 → 人数 → 镜头框图 → 角色名/外貌 → 服装 → 动作 → 表情 → 环境 → 光影

### 5. 镜头与构图
- 特写：`close-up, portrait, head and shoulders`
- 半身：`upper body, cowboy shot`
- 全身：`full body`
- 视角：`from above, from below, from side, pov, looking at viewer`

### 6. 光影效果
- 自然光：`natural lighting, soft lighting, sunlight`
- 人工光：`neon lights, studio lighting, rim lighting`
- 氛围：`volumetric lighting, god rays, lens flare`
</hard_rules>
""".strip()


_OUTPUT_FORMAT = """
<output_format>
## 输出格式（严格遵守）

你必须只输出以下格式的 JSON，不要输出任何其他内容：

{"positive": ["tag1", "tag2", "tag3"], "negative": ["tag1", "tag2"]}

要求：
- positive：英文标签数组，每个标签一个元素，必须包含质量词（masterpiece, best quality, ultra-detailed）
- negative：负面标签数组，每个标签一个元素
- 输出纯 JSON，不要用代码块包裹，不要有其他文字
</output_format>
""".strip()


_EXAMPLES = """
<examples>
## 示例

输入：画一个可爱的女孩，蓝色头发，微笑
输出：{"positive": ["masterpiece", "best quality", "highly detailed", "ultra-detailed", "8k", "solo", "1girl", "long blue hair", "smile", "cute", "beautiful face", "detailed eyes", "school uniform", "white shirt", "blue skirt", "cherry blossoms", "soft lighting", "depth of field", "anime style"], "negative": ["low quality", "blurry", "distorted", "deformed", "ugly", "bad anatomy", "disfigured", "poorly drawn face", "mutation", "mutated", "extra limbs", "extra fingers", "watermark", "text", "signature", "nsfw"]}

输入：画初音未来
输出：{"positive": ["masterpiece", "best quality", "highly detailed", "ultra-detailed", "8k", "solo", "1girl", "(hatsune miku (vocaloid):1.1)", "standing", "looking at viewer", "gentle smile", "detailed eyes", "twin tails", "aqua hair", "detached sleeves", "thighhighs", "necktie"], "negative": ["low quality", "blurry", "distorted", "deformed", "ugly", "bad anatomy", "disfigured", "poorly drawn face", "mutation", "mutated", "extra limbs", "extra fingers", "watermark", "text", "signature", "nsfw"]}

输入：画恰斯卡
输出：{"positive": ["masterpiece", "best quality", "highly detailed", "ultra-detailed", "8k", "solo", "1girl", "(chasca (genshin impact):1.1)", "standing", "looking at viewer", "confident smile", "detailed eyes", "long brown hair", "feathered hat", "coat", "gloves", "outdoors", "anime style"], "negative": ["low quality", "blurry", "distorted", "deformed", "ugly", "bad anatomy", "disfigured", "poorly drawn face", "mutation", "mutated", "extra limbs", "extra fingers", "watermark", "text", "signature", "nsfw"]}

输入：樱花树下的少女，动漫风格，近景
输出：{"positive": ["masterpiece", "best quality", "highly detailed", "ultra-detailed", "8k", "solo", "1girl", "close-up", "beautiful face", "detailed eyes", "long hair", "cherry blossom tree", "falling petals", "spring", "soft lighting", "warm colors", "anime style", "serene expression"], "negative": ["low quality", "blurry", "distorted", "deformed", "ugly", "bad anatomy", "disfigured", "poorly drawn face", "mutation", "mutated", "extra limbs", "extra fingers", "watermark", "text", "signature", "nsfw"]}
</examples>
""".strip()


# ==================== 完整模板组装 ====================

def build_prompt_generator_template() -> str:
    """构建完整的提示词生成模板。"""
    return f"""
{_ROLE_AND_CONTRACT}

{_HARD_RULES}

{_OUTPUT_FORMAT}

{_EXAMPLES}

<user_request>
<<USER_REQUEST>>
</user_request>

现在根据上述用户请求，直接输出 JSON。
""".strip()


# 生成完整模板
PROMPT_GENERATOR_TEMPLATE = build_prompt_generator_template()


# ==================== 默认提示词 ====================

DEFAULT_NEGATIVE_PROMPT = "low quality, blurry, distorted, deformed, ugly, bad anatomy, disfigured, poorly drawn face, mutation, mutated, extra limbs, extra fingers, watermark, text, signature, nsfw"

QUALITY_TAGS = "masterpiece, best quality, highly detailed, ultra-detailed, 8k"

# 人物类正面提示词细节词
CHARACTER_DETAIL_TAGS = ["detailed face", "detailed eyes", "beautiful detailed hair"]

# 人物类负面提示词（完整版）
CHARACTER_NEGATIVE_TAGS = [
    "lowres", "bad anatomy", "bad hands", "text", "error", "missing fingers", 
    "extra digit", "fewer digits", "cropped", "worst quality", "low quality", 
    "normal quality", "jpeg artifacts", "signature", "watermark", "username", 
    "blurry", "deformed", "ugly", "duplicate", "morbid", "mutilated", 
    "out of frame", "extra limbs", "cloned face", "disfigured", 
    "gross proportions", "malformed limbs", "missing arms", "missing legs", 
    "extra arms", "extra legs", "fused fingers", "too many fingers", 
    "long neck", "cross-eyed", "muscular female", "bodybuilder", 
    "overly muscular", "masculine face", "bad face", "asymmetrical face", 
    "deformed face", "ugly face", "bad eyes", "asymmetrical eyes", 
    "deformed eyes", "long eyelashes on men", "makeup"
]

# 非人物类负面提示词（基础版）
NON_CHARACTER_NEGATIVE_TAGS = [
    "lowres", "low quality", "worst quality", "normal quality", 
    "jpeg artifacts", "signature", "watermark", "username", "blurry", 
    "text", "error", "cropped", "duplicate", "out of frame", "deformed", 
    "ugly", "morbid", "mutilated"
]

# 人物类关键词检测
CHARACTER_KEYWORDS = [
    "girl", "boy", "woman", "man", "person", "people", "character", 
    "selfie", "portrait", "face", "human", "child", "adult", "teen",
    "solo", "1girl", "1boy", "2girls", "2boys", "3girls", "3boys",
    "hatsune", "miku", "saber", "rem", "ram", "anime", "manga",
    "selfie", "自拍", "女孩", "男孩", "女人", "男人", "人物", "角色",
    "脸", "眼睛", "头发", "服装", "衣服", "裙子", "校服"
]


def is_character_prompt(positive_prompt: str) -> bool:
    """判断是否是人物类提示词"""
    prompt_lower = positive_prompt.lower()
    
    # 检查是否包含人物关键词
    for keyword in CHARACTER_KEYWORDS:
        if keyword in prompt_lower:
            return True
    
    return False


def get_default_negative_prompt(is_character: bool = True) -> str:
    """获取默认的负面提示词"""
    if is_character:
        return ", ".join(CHARACTER_NEGATIVE_TAGS)
    else:
        return ", ".join(NON_CHARACTER_NEGATIVE_TAGS)


def merge_person_tags(tags: list) -> list:
    """合并多个 1girl/1boy 为 ngirl/nboy，包括空格分隔的情况"""
    # 展开空格分隔的标签
    expanded = []
    for tag in tags:
        parts = [t.strip() for t in tag.split() if t.strip()]
        expanded.extend(parts)
    
    # 统计 1girl 和 1boy 的数量
    girl_count = sum(1 for t in expanded if t.lower() == "1girl")
    boy_count = sum(1 for t in expanded if t.lower() == "1boy")
    
    # 移除所有 1girl 和 1boy
    filtered = [t for t in expanded if t.lower() not in ("1girl", "1boy")]
    
    # 根据数量添加正确的标签
    if girl_count > 0:
        if girl_count == 1:
            filtered.insert(0, "1girl")
        else:
            filtered.insert(0, f"{girl_count}girls")
    
    if boy_count > 0:
        if boy_count == 1:
            filtered.insert(0, "1boy")
        else:
            filtered.insert(0, f"{boy_count}boys")
    
    return filtered
