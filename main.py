from __future__ import annotations

import asyncio
import shlex
import sys
from pathlib import Path

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_ROOT = Path(__file__).resolve().parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from ma_service.service_mania_map_analyser import ManiaMapAnalyserService
from ma_service.errors import ManiaMapAnalyserError

MODE_FLAG_TO_CONTENT_BAR = {
    "-n": "None",
    "-a": "Auto",
    "-p": "Pattern",
    "-e": "Etterna",
    "-g": "Graph",
}

HELP_TEXT = "\n".join(
    [
        "osu!mania 谱面分析",
        "",
        "基于 osumania_map_analyser 实现本项目，可以分析键型，预估对应rf/ln段位",
        "",
        "用法：",
        "/ma <bid>     默认，等同于-a",
        "/ma -n <bid>  None，主体不显示任何内容，即短卡片模式",
        "/ma -a <bid>  Auto，主体内容按 LN 占比自动选择 Pattern 或 Etterna",
        "/ma -p <bid>  Pattern，主体显示键型分析",
        "/ma -e <bid>  Etterna，主体显示 Etterna 7 大键型分",
        "/ma -g <bid>  Graph，主体显示难度变化图",
        "/ma help      查看本帮助",
        "",
        "注：对于非4/6/7K谱面，主体内容将自动回退为Pattern显示。",
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
    async def render_map_analysis(
        self,
        event: AstrMessageEvent,
        first: str = "",
        second: str = "",
    ):
        """按 beatmap id 渲染 osumania_map_analyser 图表"""

        try:
            bid, render_overrides = self._parse_ma_command(first, second)
        except ManiaMapAnalyserError as exc:
            yield event.plain_result(str(exc))
            return

        if bid is None:
            yield event.plain_result(HELP_TEXT)
            return

        yield await self._render_result(event, bid, render_overrides)

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

    def _parse_ma_command(
        self,
        first: str = "",
        second: str = "",
    ) -> tuple[str | None, dict[str, str] | None]:
        raw_argument_text = " ".join(
            part.strip()
            for part in [str(first or ""), str(second or "")]
            if part and str(part).strip()
        )
        if not raw_argument_text:
            return None, None

        try:
            tokens = shlex.split(raw_argument_text, posix=False)
        except ValueError as exc:
            raise ManiaMapAnalyserError(f"命令参数解析失败：{exc}") from exc

        if not tokens:
            return None, None

        command = tokens[0].strip().lower()
        if command in {"help", "-h", "--help"}:
            return None, None

        if len(tokens) == 1:
            return tokens[0].strip(), {"contentBar": "Auto"}

        if len(tokens) != 2:
            raise ManiaMapAnalyserError(
                "命令格式不正确。示例：/ma 5199917、/ma -a 5199917、/ma -g 5199917"
            )

        mode_flag = tokens[0].strip().lower()
        bid = tokens[1].strip()
        content_bar = MODE_FLAG_TO_CONTENT_BAR.get(mode_flag)
        if content_bar is None:
            raise ManiaMapAnalyserError(
                "未知模式参数，仅支持 -n、-a、-p、-e、-g。示例：/ma -p 5199917"
            )

        return bid, {"contentBar": content_bar}
