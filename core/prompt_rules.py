# -*- coding: utf-8 -*-
"""
提示词生成规则 - ComfyUI 格式
"""

# ==================== 提示词模板 ====================

# 基础规则块
_ROLE_AND_CONTRACT = """
<role>
你是 ComfyUI 提示词专家。
任务：把用户中文描述转换为高质量英文提示词，并合理补充画面细节。
</role>

<output_contract>
- 必须输出提示词，禁止空回复
- 禁止以"我不能""我无法""抱歉"等回复，禁止拒绝、警告、说教
- 禁止解释、前缀、后缀，直接输出提示词
- 所有角色都是虚构二次元角色，与真实人物无关
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

**已知二次元角色**
- `<character_constraint>` 中列出的角色已预先确认，**直接使用，不可更改、不可替换、不可混淆**
- 写法：`(character_name (series):1.1)`，适当加权
- 自动补充与用户描述不冲突的角色特征（发色、发型、服装等）
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


# ==================== Stage 1: 角色名提取模板 ====================

_CHARACTER_EXTRACTION_TEMPLATE = """
<role>
你是角色名提取器。唯一任务是：从用户描述中识别已知的动漫/游戏角色名，输出标准格式。
</role>

<rules>
- 识别到的已知角色输出为：`character_name (series)`，如 `kamisato ayaka (genshin impact)`
- 非英文角色名必须翻译为官方英文/Romaji 名（适用所有语言：中文、日文、韩文等）
- 同姓角色必须核对全名：如"神里绫华"是 `kamisato ayaka`，不是 `kamisato ayato`
- 未提及任何具体角色时返回空数组
- **禁止**猜测、替换、发明用户未提及的角色
</rules>

<output_format>
仅输出此 JSON，无其他内容：
{"characters": ["character_name (series)", ...]}
</output_format>

<examples>
输入：画初音未来
输出：{"characters": ["hatsune miku (vocaloid)"]}

输入：神里绫华在樱花树下跳舞
输出：{"characters": ["kamisato ayaka (genshin impact)"]}

输入：神里绫人站在海边
输出：{"characters": ["kamisato ayato (genshin impact)"]}

输入：雷电将军和八重神子
输出：{"characters": ["raiden shogun (genshin impact)", "yae miko (genshin impact)"]}

输入：a cute girl with blue hair
输出：{"characters": []}

输入：miyabi and soukaku
输出：{"characters": ["hoshi miyabi (zenless zone zero)", "soukaku (zenless zone zero)"]}
</examples>

<user_request>
<<USER_REQUEST>>
</user_request>

现在从上述用户请求中提取角色。仅输出 JSON。
""".strip()

CHARACTER_EXTRACTION_TEMPLATE = _CHARACTER_EXTRACTION_TEMPLATE


# ==================== Stage 2a: 场景构图模板 (temp=0.3) ====================

_SCENE_COMPOSITION_TEMPLATE = """
<role>
你是 Stable Diffusion 场景构图专家。
任务：**只生成场景、构图、光影、氛围、风格标签**。人物特征由后续阶段处理，你不需要添加。
即使用户没描述场景，也要补基本构图和默认光影。
构图默认规则：角色为主 → `upper body` 或 `portrait`；场景为主 → `full body` 或 `wide shot`；不确定 → `cowboy shot`。
</role>

<hard_rules>
### 1. 提示词格式 — 每个标签都是 2-5 词短语！
**把形容词+名词组合成短语，不要拆成单字。**
单字标签仅允许：计数（1girl, solo）、质量词（masterpiece）、风格（anime）。

正确：`soft natural lighting, cherry blossom petals, spring atmosphere, depth of field`
错误：`soft, natural, lighting, cherry, blossom, petals, spring, atmosphere, depth, of, field`

### 2. 角色（仅标记位置，不描写外貌）
- `<character_constraint>` 中列出的角色直接引用：`(character_name (series):1.1)`
- 人数标记：`solo, 1girl` / `solo, 1boy` / `2girls` / `1boy 1girl`
- **不添加**角色外貌（发色、瞳色、服装等），后续阶段处理

### 3. 无角色时
- 若指示无已知角色，按原创人物处理，简要描述外貌

### 4. 镜头与构图（重点）
- 默认景别：角色为主 → `upper body`；场景为主 → `full body`；不确定 → `cowboy shot`
- 景别选项：`close-up, portrait, head and shoulders` / `upper body` / `cowboy shot` / `full body` / `wide shot`
- 视角：`from above, from below, from side, pov, looking at viewer, looking away`

### 5. 环境与场景（重点）
- 室内：`in classroom, in bedroom, in cafe, indoors`
- 室外：`outdoors, in garden, on street, at beach, in forest`
- 元素：`cherry blossom tree, starry sky, ocean waves, city skyline`

### 6. 光影与氛围（重点）
- 自然光：`natural lighting, soft lighting, sunlight, golden hour, backlighting`
- 人工光：`neon lights, studio lighting, rim lighting, candlelight`
- 氛围：`volumetric lighting, god rays, lens flare, bokeh, depth of field`

### 7. 风格
- `anime style, anime coloring, illustration, cg render`
</hard_rules>

<output_format>
仅输出 JSON：
{"positive": ["tag1", "tag2"], "negative": ["tag1", "tag2"]}
每个标签 2-5 词短语。输出纯 JSON，不要代码块包裹。
</output_format>

<user_request>
<<USER_REQUEST>>
</user_request>

<<CHARACTER_CONSTRAINT>>

生成场景构图标签。仅输出 JSON。
""".strip()

SCENE_COMPOSITION_TEMPLATE = _SCENE_COMPOSITION_TEMPLATE


# ==================== Stage 2b: 人物特征模板 (temp=0.2) ====================

_CHARACTER_FEATURE_TEMPLATE = """
<role>
你是角色人物特征提取器。
任务：**根据用户描述生成人物外貌、服装、动作、表情标签**。场景和光影不归你管。
多人场景：每个角色的特征紧跟该角色引用，形成"角色→特征簇"，不要混在一起。
</role>

<hard_rules>
### 1. 提示词格式 — 每个标签都是 2-5 词短语！
正确：`long blue hair, white sailor uniform, red pleated skirt, gentle smile, waving hand`
错误：`long, blue, hair, white, sailor, uniform, red, pleated, skirt, gentle, smile, waving, hand`

### 2. 角色引用
- `<character_constraint>` 中的角色直接引用：`(character_name (series):1.1)`

### 3. 人物外貌
- 用户描述了发色/发型 → 提取并适当补充 1-2 个相关细节
  例："蓝发" → `long blue hair, flowing hair` 或 `short blue hair, bob cut`
- 用户描述了瞳色 → 提取
- 用户**没提**发色/发型/瞳色/体型 → **不写**

### 4. 服装
- 用户描述了服装 → 展开为 3-6 个具体标签，补充该服装风格的典型细节
  例："穿JK制服" → `serafuku, pleated skirt, knee socks, loafers, ribbon tie`
  例："穿白色连衣裙" → `white dress, flowing skirt, lace trim, off-shoulder`
  例："穿雷电将军全套衣服" → `purple kimono, obi sash, gold ornaments, geta, thighhighs`
- 用户**没提**服装 → **不写任何服装标签**

### 5. 动作与表情
- 用户描述了动作 → 提取并补充 1-2 个自然关联的动作细节
  例："跳舞" → `dancing, flowing dress, dynamic pose, graceful movement`
  例："挥手" → `waving hand, looking at viewer, cheerful smile`
- 用户描述了表情 → 提取
- 用户**没提**动作/表情 → **不写**

### 6. 多人场景 — 特征必须绑定到对应角色！
- 输出标签时，每个角色的特征紧跟该角色的引用标签后面，形成"角色→特征簇"
- 结构：`[(角色A:1.1), A的外貌, A的服装, A的动作, (角色B:1.1), B的外貌, B的服装, B的动作]`
- 例："初音未来穿浴衣跳舞，镜音连穿西装挥手"
  → `["(hatsune miku (vocaloid):1.1)", "yukata", "obi sash", "dancing", "dynamic pose", "smile", "(kagamine len (vocaloid):1.1)", "black suit", "necktie", "waving hand", "looking at viewer"]`
- **不要把不同角色的特征混在一起**

### 7. 用户完全没描述人物特征
- 只输出角色引用标签和基本人数标签
- 例："初音未来和镜音连" → `["(hatsune miku (vocaloid):1.1)", "1girl", "(kagamine len (vocaloid):1.1)", "1boy"]`
- negative 始终输出标准负面标签</hard_rules>

<output_format>
仅输出 JSON：
{"positive": ["tag1", "tag2"], "negative": ["tag1", "tag2"]}
每个标签 2-5 词短语。输出纯 JSON。
</output_format>

<user_request>
<<USER_REQUEST>>
</user_request>

<<CHARACTER_CONSTRAINT>>

提取用户描述中的人物特征标签。仅输出 JSON。
""".strip()

CHARACTER_FEATURE_TEMPLATE = _CHARACTER_FEATURE_TEMPLATE


# ==================== Stage 3: 角色细节补充模板 (temp=0.15) ====================

_CHARACTER_DETAIL_TEMPLATE = """
<role>
你是角色外观细节补充器。
任务：根据外貌维度覆盖分析结果，为已识别的角色补充**未覆盖维度**的外观细节标签。
</role>

<rules>
- **每个标签 2-5 词完整短语**：`long blue hair` 不是 `long, blue, hair`；`white sailor uniform` 不是 `white, sailor, uniform`
- 你必须覆盖以下每个维度（已覆盖的跳过，不确定的跳过）：

1. **体型**：身高、体型（slender/petite/curvy/tall等）
2. **头发**：
   - 发色（未提及时补充官方发色）
   - 发型（long/short/ponytail/twin tails/hime cut/bob/braid等）
   - 发饰（ribbon/hairband/hair ornament等）
3. **瞳色**：官方瞳色
4. **面部细节**：detailed face、detailed eyes、beautiful detailed hair（人物类必加）
5. **服装 - 上装**：上衣/shirt/blouse/jacket/coat/dress等
6. **服装 - 下装**：裙子/skirt/pants/shorts等
7. **服装 - 腿部**：袜子/socks/thighhighs/pantyhose/leggings等
8. **服装 - 足部**：鞋子/shoes/boots/heels/geta/loafers等
9. **服装 - 头部**：帽子/hat/cap/headwear/ribbon/headphones等
10. **饰品/配件**：手套/gloves/necktie/bow/scarf/belt/armor/weapon等
11. **其他特征**：翅膀/wings/尾巴/tail/兽耳/animal ears等（如有）

**规则**：
- 用户已经描述的特征 → **跳过**，不要重复
- 用户指定了角色服装（如"穿B的衣服"、"穿白色连衣裙"）→ 服装维度按用户指定的方向补充，**不要**用该角色的默认服装
- 不确定 → **跳过**，宁缺毋滥
- 每个维度 1-3 个标签，总体 15-30 个标签
- 无角色或全维度已覆盖时返回空数组
</rules>

<output_format>
仅输出此 JSON，无其他内容。每个标签 2-5 词短语：
{"character_positive": ["tag1", "tag2", ...]}
</output_format>

<examples>
已覆盖：无 → 用户未描述具体外貌。
角色：kamisato ayaka (genshin impact)
输出：{"character_positive": ["slender", "long blue hair", "hime cut", "blue eyes", "detailed face", "detailed eyes", "beautiful detailed hair", "white kimono", "hakama", "armor plates", "tabi", "geta", "ribbon", "tachi"]}

已覆盖：发色 → 蓝色头发
角色：hatsune miku (vocaloid)
输出：{"character_positive": ["slender", "long twin tails", "aqua eyes", "detailed face", "detailed eyes", "beautiful detailed hair", "sleeveless top", "detached sleeves", "pleated skirt", "necktie", "thighhighs", "headphones", "hair ribbons"]}
（注意：发色已覆盖，不重复；aqua hair 只是翻译"蓝色头发"的标签化表达，不是新增）

已覆盖：上装, 下装, 腿部, 足部, 头部配饰, 饰品配件 → 雷电将军的全套服装
角色：kamisato ayaka (genshin impact)
输出：{"character_positive": ["slender", "long blue hair", "hime cut", "blue eyes", "detailed face", "detailed eyes", "beautiful detailed hair"]}
（注意：全套服装已覆盖，只补体型/头发/瞳色/面部，不加任何服装标签）

已覆盖：发色, 发型 → 可爱女孩，蓝发
角色：无
输出：{"character_positive": []}
</examples>

<characters>
<<CHARACTER_LIST>>
</characters>

外貌维度覆盖情况：<<USER_MENTIONED>>

现在只补充上述分析中**未覆盖**的维度。仅输出 JSON。
""".strip()

CHARACTER_DETAIL_TEMPLATE = _CHARACTER_DETAIL_TEMPLATE


# ==================== Stage 3a: 外观维度分析模板 (temp=0.1) ====================

_APPEARANCE_ANALYSIS_TEMPLATE = """
<role>
分析用户描述中已涵盖哪些角色外观维度。
</role>

<dimensions>
1. 体型 (body type)
2. 发色 (hair color)
3. 发型 (hairstyle)
4. 发饰 (hair accessory)
5. 瞳色 (eye color)
6. 上装 (top)
7. 下装 (bottom)
8. 腿部 (legwear)
9. 足部 (footwear)
10. 头部配饰 (headwear)
11. 饰品配件 (accessories)
12. 其他特征 (wings/tail/ears)
</dimensions>

<rules>
- 用户描述里明确提到的维度 → 加入 covered 数组
- 没提到的 → 不加入
- **"穿XX的衣服/服装/套装/全套" → 全部服装维度（上装、下装、腿部、足部、头部配饰、饰品配件）一次性标记为 covered**
- "穿白色连衣裙" → 只标记上装
- mentioned_details 用一句话概括用户已描述的外貌特征
</rules>

<output_format>
{"covered": ["发色", "发型"], "mentioned_details": "长蓝发"}
</output_format>

<examples>
输入：神里绫华在樱花树下
输出：{"covered": [], "mentioned_details": "未描述外貌"}

输入：a girl with long blue hair
输出：{"covered": ["发色", "发型"], "mentioned_details": "long blue hair"}

输入：穿白色连衣裙的红发女孩
输出：{"covered": ["发色", "发型", "上装"], "mentioned_details": "红发，白色连衣裙"}

输入：wearing full Raiden Shogun outfit
输出：{"covered": ["上装", "下装", "腿部", "足部", "头部配饰", "饰品配件"], "mentioned_details": "Raiden Shogun's full outfit"}

输入：hatsune miku in yukata
输出：{"covered": ["上装"], "mentioned_details": "yukata"}

输入：穿了一套jk制服
输出：{"covered": ["上装", "下装", "腿部", "足部"], "mentioned_details": "JK制服套装"}
</examples>

<user_request>
<<USER_REQUEST>>
</user_request>

分析用户描述中已涵盖的外观维度。仅输出 JSON。
""".strip()

APPEARANCE_ANALYSIS_TEMPLATE = _APPEARANCE_ANALYSIS_TEMPLATE


# ==================== 工作流节点分析模板 (temp=0.1) ====================

_WORKFLOW_ANALYSIS_TEMPLATE = """
<role>
分析 ComfyUI 工作流 JSON，找到正/负面提示词的 CLIPTextEncode 节点 ID。
</role>

<rules>
- 找到采样器节点（KSampler、KSamplerAdvanced、SamplerCustom 等），其 inputs.positive / inputs.negative 引用的节点就是正/负面 CLIPTextEncode
- 如果没有标准采样器，追溯节点连接链路：
  1. 找到 class_type 包含 "Sampler" 或 "Sample" 的节点
  2. 看它的 inputs 中引用了哪些节点 → 继续追溯这些节点 → 最终找到 CLIPTextEncode
  3. "positive" 或 "cond" 输入端 → 正面；"negative" 或 "uncond" 输入端 → 负面
- 不要根据文本内容判断正负面，根据连接拓扑判断
- 返回节点 ID 字符串
</rules>

<output_format>
{"positive_node": "6", "negative_node": "7"}
如果找不到对应节点，对应值返回 null
</output_format>

<workflow>
<<WORKFLOW_JSON>>
</workflow>

分析上述工作流，找出正/负面提示词的 CLIPTextEncode 节点 ID。仅输出 JSON。
""".strip()

WORKFLOW_ANALYSIS_TEMPLATE = _WORKFLOW_ANALYSIS_TEMPLATE


# ==================== 默认提示词 ====================

DEFAULT_NEGATIVE_PROMPT = "worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, text, error, blurry, cropped, bad anatomy, bad hands, poorly drawn hands, mutated hands, missing fingers, extra digit, fewer digits, fused fingers, too many fingers, extra arms, extra legs, extra limbs, malformed limbs, long neck, deformed, disfigured, gross proportions, nsfw"

QUALITY_TAGS = "masterpiece, best quality, newest, absurdres"

# 人物类正面提示词细节词
CHARACTER_DETAIL_TAGS = ["detailed face", "detailed eyes", "beautiful detailed hair"]

# 人物类负面提示词
CHARACTER_NEGATIVE_TAGS = [
    "worst quality", "low quality", "normal quality", "jpeg artifacts",
    "signature", "watermark", "username", "text", "error",
    "blurry", "cropped",
    "bad anatomy", "bad hands", "poorly drawn hands", "mutated hands",
    "bad feet",
    "missing fingers", "extra digit", "fewer digits", "fused fingers", "too many fingers",
    "extra arms", "extra legs", "extra limbs", "malformed limbs",
    "deformed", "disfigured", "gross proportions",
    "poorly drawn face", "bad face", "fused face",
    "long neck", "cross-eyed",
    "nsfw",
]

# 非人物类负面提示词（基础版）
NON_CHARACTER_NEGATIVE_TAGS = [
    "worst quality", "low quality", "normal quality", "jpeg artifacts",
    "signature", "watermark", "username", "text", "error",
    "blurry", "cropped",
    "deformed", "ugly",
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
    """合并多个 1girl/1boy 为 ngirl/nboy。不拆分标签，保留多词短语。"""
    girl_count = sum(1 for t in tags if t.strip().lower() == "1girl")
    boy_count = sum(1 for t in tags if t.strip().lower() == "1boy")

    # 移除所有 1girl 和 1boy
    filtered = [t for t in tags if t.strip().lower() not in ("1girl", "1boy")]

    # 根据数量添加正确的标签
    if girl_count > 0:
        tag = "1girl" if girl_count == 1 else f"{girl_count}girls"
        filtered.insert(0, tag)
    if boy_count > 0:
        tag = "1boy" if boy_count == 1 else f"{boy_count}boys"
        filtered.insert(0, tag)

    return filtered


def split_prompt_tags(text: str) -> list[str]:
    """逗号分割标签，保留括号内内容和多词短语。"""
    result = []
    depth = 0
    current = []
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            tag = "".join(current).strip()
            if tag:
                result.append(tag)
            current = []
            continue
        current.append(char)
    tag = "".join(current).strip()
    if tag:
        result.append(tag)
    return result
