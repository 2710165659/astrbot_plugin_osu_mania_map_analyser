from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from .browser_runtime import ChromiumRenderRuntime, RenderRequest
from .downloader import download_beatmap_file
from .errors import ManiaMapAnalyserError, NonManiaBeatmapError


class ManiaMapAnalyserService:
    """把 beatmap 下载、缓存和 Playwright 渲染隔离在 service 层"""

    def __init__(self, plugin_root: Path, render_config: dict[str, Any] | None = None) -> None:
        self.plugin_root = plugin_root
        self.core_root = plugin_root / "osumania_map_analyser"
        self.overlay_root = self.core_root / "ManiaMapAnalyser by Leo_Black"
        self.temp_root = Path(tempfile.gettempdir()) / "astrbot_plugin_osu_mania_map_analyser"
        if not self.overlay_root.exists():
            raise ManiaMapAnalyserError("未找到已复制的 osumania_map_analyser 核心目录")

        self.render_settings = self._normalize_render_settings(render_config or {})
        self.runtime = ChromiumRenderRuntime(static_root=self.overlay_root.parent)

    def generate_from_bid(
        self,
        bid_input: str,
        render_overrides: dict[str, Any] | None = None,
        runtime_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bid = self._extract_bid(bid_input)
        effective_render_settings = self._build_effective_render_settings(render_overrides or {})
        effective_runtime = self._build_effective_runtime_options(runtime_overrides or {})
        output_path = self.temp_root / "outputs" / f"{bid}_{uuid4().hex[:16]}.png"

        beatmap_path = download_beatmap_file(
            bid=bid,
            temp_dir=self.temp_root / "osu-download-cache",
        )

        try:
            osu_text = beatmap_path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception as exc:
            raise ManiaMapAnalyserError(f"读取谱面文件失败：{exc}") from exc

        beatmap_mode = self._extract_beatmap_mode(osu_text)
        if beatmap_mode != 3:
            raise NonManiaBeatmapError(
                f"该谱面不是 osu!mania 谱面，无法分析。当前 Mode: {beatmap_mode}"
            )

        payload = {
            "osuText": osu_text,
            "settings": effective_render_settings,
            "runtime": effective_runtime,
            "postRenderDelayMs": 700,
        }
        self.runtime.render(
            RenderRequest(
                output_path=output_path,
                payload=payload,
                capture_target=effective_render_settings["captureTarget"],
            )
        )

        return {
            "status": "success",
            "msg": f"rendered chart successfully for bid {bid}",
            "image_path": str(output_path.resolve()),
        }

    def _extract_bid(self, bid_input: str) -> str:
        raw = str(bid_input or "").strip().strip("\"'")
        if raw.isdigit():
            return raw

        raise ManiaMapAnalyserError("bid 格式无效，请输入谱面的数字 ID，例如：5199917")

    def _extract_beatmap_mode(self, osu_text: str) -> int | None:
        match = re.search(r"(?mi)^\s*Mode\s*:\s*(\d+)\s*$", osu_text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _normalize_render_settings(self, config: dict[str, Any]) -> dict[str, Any]:
        capture_target = str(config.get("capture_target", "full_card")).strip() or "full_card"
        if capture_target not in {"full_card", "graph_only"}:
            capture_target = "full_card"

        return {
            "captureTarget": capture_target,
            "contentBar": str(config.get("content_bar", "Auto")).strip() or "Auto",
            "srText": str(config.get("sr_text", "Auto")).strip() or "Auto",
            "diffText": str(config.get("diff_text", "Difficulty")).strip() or "Difficulty",
            "estimatorAlgorithm": str(config.get("estimator_algorithm", "Mixed")).strip() or "Mixed",
            "etternaVersion": str(config.get("etterna_version", "0.72.3")).strip() or "0.72.3",
            "companellaEtternaVersion": str(
                config.get("companella_etterna_version", "0.74.0")
            ).strip() or "0.74.0",
            "enableNumericDifficulty": bool(config.get("enable_numeric_difficulty", True)),
            "enableEtternaRainbowBars": bool(config.get("enable_etterna_rainbow_bars", True)),
            "showModeTagCapsule": bool(config.get("show_mode_tag_capsule", True)),
            "vibroDetection": bool(config.get("vibro_detection", True)),
            "debugUseAmount": bool(config.get("debug_use_amount", False)),
            "debugUseSvDetection": bool(config.get("debug_use_sv_detection", False)),
            "azusaSunnyReferenceHo": bool(config.get("azusa_sunny_reference_ho", True)),
            "cardOpacity": str(config.get("card_opacity", "95%")).strip() or "95%",
            "cardBlur": str(config.get("card_blur", "Soft")).strip() or "Soft",
            "cardRadius": str(config.get("card_radius", "Medium")).strip() or "Medium",
        }

    def _build_effective_runtime_options(self, runtime_overrides: dict[str, Any]) -> dict[str, Any]:
        speed_rate = runtime_overrides.get("speedRate", 1.0)
        try:
            speed_rate = float(speed_rate)
        except (TypeError, ValueError):
            speed_rate = 1.0
        if speed_rate <= 0:
            speed_rate = 1.0

        od_flag = runtime_overrides.get("odFlag")
        if od_flag is not None:
            od_flag = str(od_flag).strip() or None

        cvt_flag = runtime_overrides.get("cvtFlag")
        if cvt_flag is not None:
            cvt_flag = str(cvt_flag).strip().upper() or None
        if cvt_flag not in {None, "IN", "HO"}:
            cvt_flag = None

        mod_signature = str(
            runtime_overrides.get("modSignature")
            or f"{speed_rate:.5f}|{od_flag or 'none'}|{cvt_flag or 'none'}"
        ).strip()

        return {
            "speedRate": speed_rate,
            "odFlag": od_flag,
            "cvtFlag": cvt_flag,
            "modSignature": mod_signature,
        }

    def _build_effective_render_settings(self, render_overrides: dict[str, Any]) -> dict[str, Any]:
        if not render_overrides:
            return dict(self.render_settings)

        merged = dict(self.render_settings)
        for key, value in render_overrides.items():
            merged[key] = value

        return self._normalize_render_settings(
            {
                "capture_target": merged.get("captureTarget", "full_card"),
                "content_bar": merged.get("contentBar", "Auto"),
                "sr_text": merged.get("srText", "Auto"),
                "diff_text": merged.get("diffText", "Difficulty"),
                "estimator_algorithm": merged.get("estimatorAlgorithm", "Mixed"),
                "etterna_version": merged.get("etternaVersion", "0.72.3"),
                "companella_etterna_version": merged.get("companellaEtternaVersion", "0.74.0"),
                "enable_numeric_difficulty": merged.get("enableNumericDifficulty", True),
                "enable_etterna_rainbow_bars": merged.get("enableEtternaRainbowBars", True),
                "show_mode_tag_capsule": merged.get("showModeTagCapsule", True),
                "vibro_detection": merged.get("vibroDetection", True),
                "debug_use_amount": merged.get("debugUseAmount", False),
                "debug_use_sv_detection": merged.get("debugUseSvDetection", False),
                "azusa_sunny_reference_ho": merged.get("azusaSunnyReferenceHo", True),
                "card_opacity": merged.get("cardOpacity", "95%"),
                "card_blur": merged.get("cardBlur", "Soft"),
                "card_radius": merged.get("cardRadius", "Medium"),
            }
        )
