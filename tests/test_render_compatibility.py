"""Browser integration checks for the vendored upstream and render bridge.

Run: python -m unittest discover -s tests -v
Requires Playwright and its Chromium browser (same as the plugin).
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

from astrbot_service.browser_runtime import ChromiumRenderRuntime, RenderRequest, StaticFileServer

ROOT = Path(__file__).resolve().parents[1]
STATE_MODULE = "/osumania_map_analyser/ManiaMapAnalyser by Leo_Black/js/app/core/appContext.js"


def beatmap(keys=4, ln=False):
    objects = []
    for i in range(600):
        column = (i * 7 + i // 5) % keys
        x = int((column + 0.5) * 512 / keys)
        time = 1000 + i * 125
        tail = f"{time + 100}:0:0:0:0:" if ln else "0:0:0:0:"
        objects.append(f"{x},192,{time},{128 if ln else 1},0,{tail}")
    return (
        "osu file format v14\n[General]\nMode:3\n"
        "[Metadata]\nTitle:Compatibility\nArtist:Test\nCreator:Test\n"
        f"Version:{keys}K\nBeatmapID:1\n[Difficulty]\nCircleSize:{keys}\n"
        "OverallDifficulty:8\nHPDrainRate:7\nSliderMultiplier:1.4\n"
        "[TimingPoints]\n0,500,4,2,1,100,1,0\n[HitObjects]\n"
        + "\n".join(objects)
    )


class RenderCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = StaticFileServer(ROOT)
        cls.server.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.stop()

    def test_bridge_modes_keys_mods_and_calculators(self):
        cases = [
            (f"mode-{mode}", 4, False, {"contentBar": mode}, {})
            for mode in ("None", "Auto", "Pattern", "Etterna", "Graph", "ReworkPP", "Full")
        ] + [
            ("6k", 6, False, {}, {}),
            ("7k-ln", 7, True, {}, {}),
            ("5k", 5, False, {}, {}),
            ("5k-graph", 5, False, {"contentBar": "Graph"}, {}),
            ("4k-ln", 4, True, {}, {}),
            ("dt", 4, False, {}, {"speedRate": 1.5}),
            ("ht-custom", 4, True, {}, {"speedRate": 0.8}),
            ("in", 4, True, {}, {"cvtFlag": "IN"}),
            ("ho", 4, False, {}, {"cvtFlag": "HO"}),
            ("ett-0.75", 4, False, {"contentBar": "Etterna", "etternaVersion": "0.75.0"}, {}),
            ("companella", 4, False, {"estimatorAlgorithm": "Companella"}, {}),
        ]
        for name, keys, ln, settings, runtime in cases:
            with self.subTest(name=name):
                page = self.browser.new_page(viewport={"width": 900, "height": 1400})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda msg: errors.append(msg.text) if msg.type in ("error", "warning") else None)
                try:
                    page.add_init_script("window.__MA_RENDER_PAYLOAD = " + json.dumps({
                        "osuText": beatmap(keys, ln), "settings": settings, "runtime": runtime,
                        "postRenderDelayMs": 50,
                    }))
                    page.goto(f"http://127.0.0.1:{self.server.port}/bridge/render_bridge.html")
                    page.wait_for_load_state("networkidle")
                    page.wait_for_function("window.__MA_RENDER_DONE === true", timeout=30000)
                    self.assertEqual(page.evaluate("window.__MA_RENDER_ERROR"), "")
                    # Upstream deliberately selects 0.74 for non-4K charts.
                    unexpected = [error for error in errors if not (
                        keys != 4 and error == "Etterna version 0.72.3 is unavailable; "
                        "falling back to 0.74.0. Reason: Using 0.74.0 for non-4K stability"
                    )]
                    self.assertEqual(unexpected, [], "Browser errors or silent calculator fallback")
                    self.assertIn(f"Keys: {keys}", page.locator("#rework-meta").inner_text())
                    self.assertRegex(page.locator("#rework-star").inner_text(), r"\d+\.\d+")
                    self.assertIn("Compatibility", page.locator("#status").inner_text())
                    result = page.evaluate("""async (url) => {
                        const {state, getActiveContentBar} = await import(url);
                        return {content: getActiveContentBar(), speed: state.speedRate,
                                cvt: state.cvtFlag, algorithm: state.actualEstimatorAlgorithm};
                    }""", STATE_MODULE)
                    self.assertEqual(result["speed"], runtime.get("speedRate", 1))
                    self.assertEqual(result["cvt"], runtime.get("cvtFlag"))
                    if name == "companella":
                        self.assertEqual(result["algorithm"], "Companella")
                    expected = settings.get("contentBar", "Auto")
                    if expected == "Auto":
                        expected = "Pattern" if ln else "Etterna"
                    sections = {"Pattern": "#pattern-clusters", "Etterna": "#ett-skill-bars",
                                "Graph": "#body-graph-wrap", "ReworkPP": "#pp-bars"}
                    for module, selector in sections.items():
                        visible = expected == "Full" or module == expected
                        self.assertEqual(page.locator(selector).is_visible(), visible, module)
                        if visible:
                            self.assertEqual(page.locator(selector + " .skeleton").count(), 0)
                            if module == "Graph":
                                self.assertTrue(page.locator("#body-graph-line").get_attribute("d"))
                            else:
                                self.assertNotIn("No data", page.locator(selector).inner_text())
                    if expected == "Full":
                        self.assertTrue(page.locator("#sep-pattern").is_visible())
                finally:
                    page.close()

    def test_production_runtime_screenshots(self):
        runtime = ChromiumRenderRuntime(ROOT)
        try:
            with tempfile.TemporaryDirectory() as output:
                for target in ("full_card", "graph_only"):
                    path = Path(output) / f"{target}.png"
                    runtime.render(RenderRequest(path, {
                        "osuText": beatmap(), "settings": {"contentBar": "Graph"},
                        "postRenderDelayMs": 50,
                    }, target))
                    self.assertTrue(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
