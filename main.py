from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from service.service_mania_map_analyser import ManiaMapAnalyserService
from service.errors import ManiaMapAnalyserError

HELP_TEXT = "\n".join(
    [
        "用法：",
        "/ma <bid> 默认模式（Auto）",
        "/map <bid> Pattern",
        "/mae <bid> Etterna",
        "/mag <bid> Graph",
        "/ma help 查看帮助",
        "仅支持纯数字 bid",
    ]
)


@register(
    "astrbot_plugin_osu_mania_map_analyser",
    "xuan_yuan",
    "Render osumania_map_analyser charts from beatmap id via Playwright.",
    "0.1.0",
)
class ManiaMapAnalyserPlugin(Star):
    """AstrBot 插件入口"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.render_service = ManiaMapAnalyserService(
            plugin_root=PLUGIN_ROOT,
            render_config={
                "capture_target": config.get("capture_target", "full_card"),
                "content_bar": config.get("content_bar", "Auto"),
                "sr_text": config.get("sr_text", "Auto"),
                "diff_text": config.get("diff_text", "Difficulty"),
                "estimator_algorithm": config.get("estimator_algorithm", "Mixed"),
                "etterna_version": config.get("etterna_version", "0.72.3"),
                "companella_etterna_version": config.get("companella_etterna_version", "0.74.0"),
                "enable_numeric_difficulty": config.get("enable_numeric_difficulty", True),
                "enable_etterna_rainbow_bars": config.get("enable_etterna_rainbow_bars", True),
                "show_mode_tag_capsule": config.get("show_mode_tag_capsule", True),
                "vibro_detection": config.get("vibro_detection", True),
                "debug_use_amount": config.get("debug_use_amount", False),
                "debug_use_sv_detection": config.get("debug_use_sv_detection", False),
                "azusa_sunny_reference_ho": config.get("azusa_sunny_reference_ho", True),
                "card_opacity": config.get("card_opacity", "95%"),
                "card_blur": config.get("card_blur", "Soft"),
                "card_radius": config.get("card_radius", "Medium"),
            },
        )
        configured_max_concurrency = int(config.get("max_concurrency", 5))
        self.max_concurrency = max(1, min(configured_max_concurrency, 5))
        self.render_timeout_seconds = config.get("render_timeout_seconds", 120)
        self._render_semaphore = asyncio.Semaphore(self.max_concurrency)

    @filter.command("ma", alias={"mania分析", "谱面分析"})
    async def render_map_analysis(self, event: AstrMessageEvent, bid: str = ""):
        """按 beatmap id 渲染 osumania_map_analyser 图表"""

        normalized = str(bid or "").strip()
        if not normalized or normalized.lower() == "help":
            yield event.plain_result(HELP_TEXT)
            return

        yield await self._render_result(event, normalized)

    @filter.command("map")
    async def render_pattern_analysis(self, event: AstrMessageEvent, bid: str):
        """按 beatmap id 渲染 Pattern 主体内容"""

        yield await self._render_result(event, bid, {"contentBar": "Pattern"})

    @filter.command("mae")
    async def render_etterna_analysis(self, event: AstrMessageEvent, bid: str):
        """按 beatmap id 渲染 Etterna 主体内容"""

        yield await self._render_result(event, bid, {"contentBar": "Etterna"})

    @filter.command("mag")
    async def render_graph_analysis(self, event: AstrMessageEvent, bid: str):
        """按 beatmap id 渲染 Graph 主体内容"""

        yield await self._render_result(event, bid, {"contentBar": "Graph"})

    async def _render_result(
        self,
        event: AstrMessageEvent,
        bid: str,
        render_overrides: dict[str, str] | None = None,
    ):
        """统一处理渲染命令，返回 plain_result 或 chain_result 对象。"""

        if self._render_semaphore.locked():
            return event.plain_result("当前谱面分析任务较多，请稍后再试")

        try:
            async with self._render_semaphore:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.render_service.generate_from_bid,
                        bid,
                        render_overrides,
                    ),
                    timeout=self.render_timeout_seconds,
                )
            image_path = result["image_path"]
            if not image_path or not Path(image_path).exists():
                raise FileNotFoundError("生成的图表文件不存在")
        except asyncio.TimeoutError:
            return event.plain_result("谱面分析渲染超时，请稍后再试")
        except ManiaMapAnalyserError as exc:
            return event.plain_result(str(exc))
        except Exception as exc:
            logger.exception("osu mania map analyser plugin failed while rendering chart")
            return event.plain_result("谱面分析渲染失败：" + str(exc))

        chain = [
            Comp.Reply(id=event.message_obj.message_id),
            Comp.Image.fromFileSystem(image_path),
        ]
        return event.chain_result(chain)
