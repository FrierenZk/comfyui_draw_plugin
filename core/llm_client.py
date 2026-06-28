# -*- coding: utf-8 -*-
"""LLM 调用客户端：tool calling、web search、格式校验重试、外部搜索。"""

import asyncio
import json
import os
import re
import time
from typing import TYPE_CHECKING

from src.services import llm_service

if TYPE_CHECKING:
    from ..sdk_runtime import ComfyUIDrawInvocation


class LLMClientMixin:
    """LLM 调用+搜索能力，作为 ComfyUIDrawGenerator 的 mixin 父类。"""

# ── 格式校验 ──────────────────────────────────────────

    @staticmethod
    def _validate_json_response(text: str, key: str) -> bool:
        """校验响应是否包含有效的 JSON 且包含指定 key。"""
        t = text.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            t = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        try:
            data = json.loads(t)
            return isinstance(data, dict) and key in data
        except json.JSONDecodeError:
            m = re.search(r'\{.*"' + key + r'".*\}', t, re.DOTALL)
            if m:
                try:
                    json.loads(m.group())
                    return True
                except json.JSONDecodeError:
                    pass
        return False

    # ── LLM 调用 + 重试 ───────────────────────────────────

    async def _llm_generate(
        self, task_name: str, prompt: str, temperature: float, max_tokens: int,
        validate: callable = None, with_search: int = 0,
    ) -> tuple[bool, str]:
        """统一 LLM 调用。with_search=N 表示最多 N 次搜索（0=不搜索）。"""
        for attempt in range(3):
            text = await self._llm_generate_once(task_name, prompt, temperature, max_tokens, with_search)
            if not text:
                return False, ""
            if validate is None or validate(text):
                return True, text
            self.inv._debug_log(f"LLM 格式校验失败，重试 {attempt + 1}/3")
            prompt = prompt.rstrip() + (
                "\n\n<format_reminder>\n"
                "Your previous output did not match the required JSON format. "
                "Output ONLY valid JSON — no markdown code blocks, no explanations, no prefixes.\n"
                "</format_reminder>"
            )

        self.logger.error("LLM 格式校验失败，已重试 3 次，终止任务")
        return False, ""

    async def _llm_generate_once(
        self, task_name: str, prompt: str, temperature: float, max_tokens: int,
        with_search: int = 0,
    ) -> str:
        """Anthropic SDK 直连调用。with_search=N 表示最多 N 次搜索（0=不搜索）。"""
        base_url = self.inv._get_config("llm", "anthropic_base_url", "https://api.deepseek.com/anthropic")
        model = self.inv._get_config("llm", "model_name", "deepseek-v4-pro")

        # 注入 env 条目到 os.environ，调用后恢复
        restored = {}
        for entry in self.inv._get_config("llm", "anthropic_env", []):
            if isinstance(entry, str) and "=" in entry:
                k, v = entry.split("=", 1)
                k, v = k.strip(), v.strip()
                if k:
                    restored[k] = os.environ.get(k)
                    os.environ.setdefault(k, v)

        api_key = self.inv._get_config("llm", "anthropic_api_key", "") or os.environ.get("ANTHROPIC_API_KEY", "")
        use_anthropic = self.inv._get_config("llm", "use_anthropic_api", True) and bool(api_key)
        self.inv._debug_log(f"LLM 路径: {'Anthropic直连' if use_anthropic else 'MaiBot旧API'}")

        if use_anthropic:
            try:
                from anthropic import AsyncAnthropic
            except ImportError:
                pass  # fall through to old API
            else:
                try:
                    self._last_truncated = False
                    tools_arg = [{"type": "web_search_20260209", "name": "web_search", "max_uses": with_search}] if with_search > 0 else None
                    client = AsyncAnthropic(api_key=api_key, base_url=base_url)
                    t0 = time.monotonic()
                    kwargs = dict(model=model, max_tokens=max_tokens,
                                  messages=[{"role": "user", "content": prompt}],
                                  system="Output ONLY the requested JSON format, no markdown, no explanations. Search only for specific, essential facts. Do not broad-search.",
                                  thinking={"type": "enabled" if with_search > 0 else "disabled"})
                    if tools_arg:
                        kwargs["tools"] = tools_arg
                    response = await client.messages.create(**kwargs)
                    await client.close()

                    elapsed = time.monotonic() - t0
                    usage = getattr(response, "usage", None)
                    if usage:
                        out_tk = getattr(usage, "output_tokens", 0)
                        self.inv._debug_log(
                            f"LLM token: in={getattr(usage, 'input_tokens', '?')} "
                            f"out={out_tk} "
                            f"cache_read={getattr(usage, 'cache_read_input_tokens', 0)} "
                            f"耗时={elapsed:.1f}s"
                        )
                        self._last_truncated = out_tk >= max_tokens
                        if self._last_truncated:
                            self.logger.warning(
                                f"LLM 输出截断! out={out_tk} >= max={max_tokens}，考虑调高对应 max_tokens 配置"
                            )

                    # 记录各 block 类型
                    block_types = [getattr(b, "type", "?") for b in response.content]
                    self.inv._debug_log(f"LLM blocks: {block_types}")

                    text = " ".join(
                        b.text for b in response.content
                        if hasattr(b, "text") and b.text
                    )
                    self.inv._debug_log(f"LLM 原生响应: {text[:200]}")
                    return text  # 即使空也不回退旧API，交给 _llm_generate 重试
                except Exception as e:
                    self.inv._debug_log(f"Anthropic 直连失败，回退旧 API: {e}")
                finally:
                    for k, v in restored.items():
                        if v is None: del os.environ[k]
                        else: os.environ[k] = v
                    restored.clear()

        # 旧 API 回退（无 Anthropic key 时用）
        try:
            result = await llm_service.generate(
                llm_service.LLMServiceRequest(
                    task_name=task_name,
                    request_type="comfyui_draw_plugin.llm_generate",
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            if result.success and result.completion.response:
                raw = result.completion.response.strip()
                self.inv._debug_log(f"LLM token(旧API): {getattr(result.completion, 'usage', 'N/A')}")
                return raw
        except Exception as e:
            self.logger.error(f"LLM 调用失败: {e}")
        return ""

    # ── 外部搜索 ──────────────────────────────────────────

    _CHAR_CACHE_FILE = "character_info.json"
    _CLOTH_CACHE_FILE = "clothing_info.json"
    _CACHE_TIERS = [3, 7, 30, 90]  # 天

    def _load_json_cache(self, filename: str) -> dict:
        path = os.path.join(os.path.dirname(__file__), "..", "cache", filename)
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_json_cache(self, filename: str, data: dict) -> None:
        path = os.path.join(os.path.dirname(__file__), "..", "cache", filename)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    async def _fetch_character_info(self, task_name: str, characters: list[str]) -> str:
        """预搜索角色外观信息（分级过期缓存）。"""
        if not characters:
            return ""
        cache_key = ",".join(sorted(c.lower() for c in characters))
        return await self._cached_search(
            task_name, cache_key, self._CHAR_CACHE_FILE,
            f"Search and list key appearance facts for: {', '.join(characters)}. Reply with bullet points only.",
        )

    async def _fetch_clothing_info(self, task_name: str, clothing: list[str]) -> str:
        """预搜索服装信息（分级过期缓存）。clothing 为 S1 LLM 提取的服装标签列表。"""
        if not clothing:
            return ""
        cache_key = ",".join(sorted(c.lower() for c in clothing))
        return await self._cached_search(
            task_name, cache_key, self._CLOTH_CACHE_FILE,
            f"Search and describe the appearance of: {', '.join(clothing)}. Reply with bullet points only.",
        )

    async def _cached_search(
        self, task_name: str, cache_key: str, cache_file: str, prompt: str,
    ) -> str:
        """通用分级缓存搜索。"""
        cache = self._load_json_cache(cache_file)
        entry = cache.get(cache_key)
        now = time.time()

        if entry and now - entry.get("ts", 0) < entry.get("ttl", 3) * 86400:
            self.inv._debug_log(f"缓存命中({entry.get('ttl')}天): {cache_key[:60]}")
            return entry["data"]

        text = await self._llm_generate_once(
            task_name=task_name, prompt=prompt,
            temperature=0.1, max_tokens=800, with_search=2,
        )
        result = text.strip() if text else ""
        if not result:
            return ""

        new_ttl = 3
        if entry:
            similar = await self._judge_similarity(task_name, entry.get("data", "")[:500], result[:500])
            old_tier = self._CACHE_TIERS.index(entry.get("ttl", 3))
            new_ttl = self._CACHE_TIERS[min(old_tier + 1, 3)] if similar else 3
            self.inv._debug_log(f"缓存升级: {entry.get('ttl')}→{new_ttl}天 ({'相似' if similar else '变化'})")

        # 仅 Anthropic 路径且未截断才写缓存
        if self.inv._get_config("llm", "use_anthropic_api", False) and not getattr(self, "_last_truncated", False):
            cache[cache_key] = {"data": result, "ts": now, "ttl": new_ttl}
            self._save_json_cache(cache_file, cache)
        return result

    async def _judge_similarity(self, task_name: str, old: str, new: str) -> bool:
        """LLM 判断两段角色信息是否语义相同（极轻量调用）。"""
        text = await self._llm_generate_once(
            task_name=task_name,
            prompt=f"Are these two character descriptions semantically the same? Reply YES or NO.\n\nA: {old[:300]}\n\nB: {new[:300]}",
            temperature=0.1, max_tokens=10, with_search=0,
        )
        return "YES" in text.upper()


    async def _search_knowledge(self, query: str) -> str:
        """无操作——server 端 web_search 已覆盖。保留以兼容 stages 调用。"""
        cache_key = query.strip().lower()
        if cache_key in self._knowledge_cache:
            return self._knowledge_cache[cache_key]

