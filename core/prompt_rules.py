# -*- coding: utf-8 -*-
"""
提示词生成规则 - ComfyUI 格式
"""



# ==================== Stage 1a: 角色名提取模板 (temp=0.1) ====================

_CHARACTER_EXTRACTION_TEMPLATE = """
<role>
你是角色名提取器。唯一任务是：从用户描述中识别已知的动漫/游戏角色名，输出标准格式。
</role>

<rules>
- 如有 `<knowledge_reference>`，优先参考其中的角色信息
- 识别到的已知角色输出为：`character_name (series)`，如 `kamisato ayaka (genshin impact)`
- 非英文角色名必须翻译为官方英文/Romaji 名（适用所有语言：中文、日文、韩文等）
- 同姓角色必须核对全名：如"神里绫华"是 `kamisato ayaka`，不是 `kamisato ayato`
- 未提及任何具体角色时返回空数组
- **禁止**猜测、替换、发明用户未提及的角色
- **"A穿B的衣服/服装"** → 只提取 A 为角色，B 只是服装风格参考，不是出场角色
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

输入：神里绫华穿雷电将军的衣服
输出：{"characters": ["kamisato ayaka (genshin impact)"]}
（雷电将军只是服装参考，不是出场角色）
</examples>

<user_request>
<<USER_REQUEST>>
</user_request>

现在从上述用户请求中提取角色。仅输出 JSON。
""".strip()

CHARACTER_EXTRACTION_TEMPLATE = _CHARACTER_EXTRACTION_TEMPLATE


# ==================== Stage 1b: 服装提取模板 (temp=0.1) ====================

_CLOTHING_EXTRACTION_TEMPLATE = """
<role>
你是服装/配饰提取器。唯一任务是：从用户描述中识别用户明确指定的服装和配饰，输出短标签列表。
</role>

<rules>
- 从用户描述中提取用户**明确提到**的服装/配饰/鞋帽/饰品，翻译为标准英文标签
- 不依赖特定动词，描述中出现的服装词汇（丝袜、裙子、帽子、耳机、手套、鞋子、眼镜、围巾、背包等）都要识别
- 多条目标 `、` 或 `,` 分隔的 → 拆分为独立条目
  例："穿白色连衣裙和戴帽子" → ["white dress", "hat"]
  例："增强丝袜质感、丝袜透肉" → ["stockings"]
  例："穿JK制服背书包" → ["school uniform", "backpack"]
- **"A穿B的衣服/服装/全套/套装"** → 服装提取为 "B's outfit"，A 是角色不在此提取
- 用户未提及任何服装/配饰 → 返回空数组
- **禁止**推断、猜测用户未提及的服装
- **禁止**提取发型、发色、瞳色、体型等非服装特征
</rules>

<output_format>
仅输出此 JSON，无其他内容：
{"clothing": ["english_tag", ...]}
</output_format>

<examples>
输入：穿白色连衣裙和帽子的女孩
输出：{"clothing": ["white dress", "hat"]}

输入：初音未来穿丝袜戴耳机
输出：{"clothing": ["stockings", "headphones"]}

输入：神里绫华穿雷电将军的衣服
输出：{"clothing": ["raiden shogun's outfit"]}

输入：一个穿JK制服背书包的少女
输出：{"clothing": ["school uniform", "backpack"]}

输入：a cute girl with blue hair
输出：{"clothing": []}

输入：樱花树下的少女，动漫风格
输出：{"clothing": []}
</examples>

<user_request>
<<USER_REQUEST>>
</user_request>

现在从上述用户请求中提取服装/配饰。仅输出 JSON。
""".strip()

CLOTHING_EXTRACTION_TEMPLATE = _CLOTHING_EXTRACTION_TEMPLATE


# ==================== Stage 1c: 负面标签提取模板 (temp=0.1) ====================

_NEGATIVE_EXTRACTION_TEMPLATE = """
<role>
你是负面标签提取器。唯一任务：根据用户描述判断需要哪些额外的上下文负面标签。
</role>

<rules>
仅在以下情况添加对应标签，否则输出空数组：
- 动漫/二次元风格 → 加 realistic, photorealistic, 3d, 3d render
- 写实/照片风格 → 加 anime, cartoon
- 成人/R18 暗示 → 加 nsfw
- 用户明确说"不要/别/勿/no/don't"某物 → 提取为英文标签
- **用户描述中明确想要的，不要加为负面**
- 不确定 → 输出空数组
默认负面标签（worst quality, blurry, bad anatomy 等）已由系统添加，**不要重复输出**。
</rules>

<output_format>
仅输出此 JSON，无其他内容：
{"negative": ["tag1", "tag2", ...]}
无内容时输出 {"negative": []}
</output_format>

<examples>
输入：一个可爱的动漫女孩，蓝发
输出：{"negative": ["realistic", "photorealistic", "3d", "3d render"]}

输入：写实风格的人物肖像
输出：{"negative": ["anime", "cartoon"]}

输入：不要猫，不要下雨
输出：{"negative": ["cat", "rain"]}

输入：a cute girl with blue hair
输出：{"negative": []}
</examples>

<user_request>
<<USER_REQUEST>>
</user_request>

根据上述用户描述提取负面标签。仅输出 JSON。
""".strip()

NEGATIVE_EXTRACTION_TEMPLATE = _NEGATIVE_EXTRACTION_TEMPLATE


# ==================== Stage 2a: 场景构图模板 (temp=0.3) ====================

_SCENE_COMPOSITION_TEMPLATE = """
<role>
你是 Stable Diffusion 场景构图专家。
任务：**只生成场景、构图、光影、氛围、风格标签**。人物特征由后续阶段处理，你不需要添加。
用户通常只描述角色，你需要**根据描述合情合理推导简单的场景框架**：
- 角色为主时，**用户指定了景别/视角就用用户指定的**，没指定才用 `cowboy shot`
- 从描述中找线索推导场景：如"喝咖啡"→ in cafe、"看书"→ in library/at desk、"海边"→ at beach
- 没线索时用 `simple background, depth of field`，不要编造不存在的地点或元素
- 光影同理：有线索（如"夕阳""夜晚"）就展开，没线索用 `natural lighting`
</role>

<hard_rules>
### 1. 提示词格式 — 每个标签都是 2-5 词短语！
**把形容词+名词组合成短语，不要拆成单字。**
单字标签仅允许：计数（1girl, solo）、质量词（masterpiece）、风格（anime）。

正确：`soft natural lighting, cherry blossom petals, spring atmosphere, depth of field`
错误：`soft, natural, lighting, cherry, blossom, petals, spring, atmosphere, depth, of, field`

### 2. 角色（仅标记位置，不描写外貌）
- `<character_constraint>` 中的加权角色标签**原样输出**
- 人数标记：`solo, 1girl` / `solo, 1boy` / `2girls` / `1boy 1girl`
- `<clothing_constraint>` 中列出的服装已锁定，后续阶段处理，此处不添加服装标签
- **不添加**角色外貌（发色、瞳色、服装等），后续阶段处理

### 3. 镜头与构图（重点）
- **角色类提示词必须用近景，禁止用 full body 或 wide shot**
- 角色为主未指定景别 → `cowboy shot`；场景为主 → `full body`
- 景别选项：`portrait, head and shoulders` / `upper body` / `cowboy shot` / `full body` / `wide shot`
- 视角：`from above, from below, from side, pov, looking at viewer, looking away`

### 4. 环境与场景（重点）
- 室内：`in classroom, in bedroom, in cafe, indoors`
- 室外：`outdoors, in garden, on street, at beach, in forest`
- 元素：`cherry blossom tree, starry sky, ocean waves, city skyline`

### 5. 光影与氛围（重点）
- 自然光：`natural lighting, soft lighting, sunlight, golden hour, backlighting`
- 人工光：`neon lights, studio lighting, rim lighting, candlelight`
- 氛围：`volumetric lighting, god rays, lens flare, bokeh, depth of field`

### 6. 风格/画质/艺术家
- **用户描述中提到的风格、画质、引擎、艺术家名 → 必须生成对应英文标签，不可丢弃**
  例："3D渲染"→3d render、"原画画质"→high quality artwork、"油画风"→oil painting
- 无特别指定时的参考风格：
  动漫/二次元：`anime style, anime coloring, illustration, cg render`
  写实：`photorealistic, realistic, hyperrealistic, photography`
  艺术/绘画：`impressionist painting, watercolor, oil painting, sketch`
</hard_rules>

<output_format>
仅输出 JSON，无其他内容：
{"positive": ["tag1", "tag2"]}
每个标签 2-5 词短语。输出纯 JSON。
</output_format>

<user_request>
<<USER_REQUEST>>
</user_request>

<<CHARACTER_CONSTRAINT>>

<<CLOTHING_CONSTRAINT>>

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

### 2. 角色引用与人数
- 角色名和人数标签（1girl, solo, 2girls 等）已由 S2a 添加，**不要重复输出**

### 3. 人物外貌
- 用户描述了发色/发型 → 提取并适当补充 1-2 个相关细节
  例："蓝发" → `long blue hair, flowing hair` 或 `short blue hair, bob cut`
- 用户描述了瞳色 → 提取
- 用户**没提**发色/发型/瞳色/体型 → **不写**

### 4. 服装
- `<clothing_constraint>` 中的加权服装标签**必须原样输出到 clothing 字段，不可丢弃**
- 然后在后面展开为 3-6 个具体英文标签
- 展开时根据用户描述中的修饰词生成对应细节：如"透肉"→sheer、"增强质感"→detailed texture
- 有 `<knowledge_reference>` 优先参考
用户**没提**服装 → **不写任何服装标签**

### 5. 动作与表情
- 用户描述了动作 → 提取并补充 1-2 个自然关联的动作细节
  例："跳舞" → `dancing, flowing dress, dynamic pose, graceful movement`
  例："挥手" → `waving hand, looking at viewer, cheerful smile`
- 用户描述了表情 → 提取
- 用户**没提**动作/表情 → **不写**

### 6. 用户完全没描述人物特征
- 三个字段（appearance, clothing, other）均输出空数组 `[]`
- 角色引用和人数标签已由 S2a 添加，此处不重复</hard_rules>

<output_format>
仅输出此 JSON，无其他内容：
{"appearance": ["tag1", "tag2"], "clothing": ["tag1", "tag2"], "other": ["tag1", "tag2"]}

字段说明：
- appearance：外貌标签（发色、发型、瞳色、体型、面部细节等）
- clothing：服装/配饰标签（上装、下装、腿部、足部、头部、饰品等）
- other：动作、表情等非外貌非服装的标签
- 无内容的字段输出空数组 []
每个标签 2-5 词短语。输出纯 JSON。
</output_format>

<user_request>
<<USER_REQUEST>>
</user_request>

<<CHARACTER_CONSTRAINT>>

<<CLOTHING_CONSTRAINT>>

提取用户描述中的人物特征标签。仅输出 JSON。
""".strip()

CHARACTER_FEATURE_TEMPLATE = _CHARACTER_FEATURE_TEMPLATE


# ==================== Stage 3: 角色细节补充模板 (temp=0.15) ====================

_CHARACTER_DETAIL_TEMPLATE = """
<role>
你是角色外观细节补充器。
**必须先用 web_search 逐个搜索未覆盖维度（如 "[角色名] hair color"、"[角色名] eye color"），从搜索结果提取准确标签。**
只输出搜索结果中确认存在的特征，不要编造。
</role>

<rules>
- 如有 `<knowledge_reference>`，**优先使用**其中的角色外观信息，不要用训练数据猜测
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


# ==================== Stage 3c: 服装细节补充模板 (temp=0.15) ====================

_CLOTHING_DETAIL_TEMPLATE = """
<role>
你是服装/配饰细节补充器。
**必须先用 web_search 搜索服装/配饰的典型外观细节（如 "[服装名] appearance details"），从搜索结果提取准确标签。**
只输出搜索结果中确认存在的特征，不要编造。
</role>

<rules>
- 如有 `<knowledge_reference>`，**优先使用**其中的服装信息
- **每个标签 2-5 词完整短语**：`white flowing dress` 不是 `white, flowing, dress`；`knee socks` 不是 `knee, socks`
- 你必须覆盖以下服装维度（已覆盖的跳过，不确定的跳过）：

1. **上装**：上衣/shirt/blouse/jacket/coat/dress等
2. **下装**：裙子/skirt/pants/shorts等
3. **腿部**：袜子/socks/thighhighs/pantyhose/leggings等
4. **足部**：鞋子/shoes/boots/heels/geta/loafers等
5. **头部**：帽子/hat/cap/headwear/ribbon/headphones等
6. **饰品/配件**：手套/gloves/necktie/bow/scarf/belt/armor等

**规则**：
- 约束中已有的服装 → **跳过**，不要重复
- 不确定 → **跳过**，宁缺毋滥
- 每个维度 1-3 个标签，总体 5-15 个标签
- 无服装或全维度已覆盖时返回空数组
</rules>

<output_format>
仅输出此 JSON，无其他内容。每个标签 2-5 词短语：
{"clothing_positive": ["tag1", "tag2", ...]}
</output_format>

<examples>
服装：白色连衣裙
输出：{"clothing_positive": ["white dress", "flowing skirt", "lace trim", "ribbon belt"]}

服装："JK制服", "丝袜"
输出：{"clothing_positive": ["serafuku", "pleated skirt", "knee socks", "loafers", "ribbon tie", "pantyhose"]}

服装：[]
输出：{"clothing_positive": []}
</examples>

<clothing>
<<CLOTHING_LIST>>
</clothing>

S2b 已覆盖的服装维度：<<USER_MENTIONED>>

跳过已覆盖的维度，只补充未覆盖的。仅输出 JSON。
""".strip()

CLOTHING_DETAIL_TEMPLATE = _CLOTHING_DETAIL_TEMPLATE


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
- `<stage2b_generated_tags>` 中的标签对应的维度 → 同样视为已覆盖
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

DEFAULT_NEGATIVE_PROMPT = "worst quality, low quality, jpeg artifacts, signature, watermark, username, text, error, blurry, bad anatomy, bad hands, poorly drawn hands, bad feet, bad shoes, extra shoes, missing fingers, extra digit, too many fingers, extra arms, extra legs, extra limbs, malformed limbs, deformed, poorly drawn face, bad face, long neck, cross-eyed, nsfw"

# 人物类负面提示词
CHARACTER_NEGATIVE_TAGS = [
    "worst quality", "low quality", "jpeg artifacts",
    "signature", "watermark", "username", "text", "error",
    "blurry",
    "bad anatomy", "bad hands", "poorly drawn hands",
    "bad feet", "bad shoes", "extra shoes",
    "missing fingers", "extra digit", "too many fingers",
    "extra arms", "extra legs", "extra limbs", "malformed limbs",
    "deformed",
    "poorly drawn face", "bad face",
    "long neck", "cross-eyed",
    "nsfw",
]

# 非人物类负面提示词
NON_CHARACTER_NEGATIVE_TAGS = [
    "worst quality", "low quality", "jpeg artifacts",
    "signature", "watermark", "username",
    "blurry", "deformed",
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
