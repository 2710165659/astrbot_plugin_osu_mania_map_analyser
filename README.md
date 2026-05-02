# astrbot_plugin_osu_mania_map_analyser

AstrBot 插件版 `osumania_map_analyser`。机器人可通过 `/ma <bid>` 下载 `.osu`、用 Playwright 驱动常驻 Chromium 渲染图表，并返回 PNG 图片。

原始项目地址：<https://github.com/LeoBlackMT/osumania_map_analyser>

## 安装

首次使用前，除了安装 Python 依赖，还需要额外安装 Playwright 的 Chromium 内核。建议在 AstrBot 实际运行插件的同一 Python 环境中执行：

```powershell
python -m playwright install-deps chromium
```

验证，预期输出：`Chromium OK: ...`
```powershell
python - <<'PY'
import asyncio
from playwright.async_api import async_playwright

async def main():
    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
    print("Chromium OK:", browser.version)
    await browser.close()
    await p.stop()

asyncio.run(main())
PY
```

## 使用

- `/ma <bid>`：默认等同于 `/ma -a <bid>`
- `/ma -n <bid>`：`None`，主体不显示任何内容，即短卡片模式
- `/ma -a <bid>`：`Auto`，主体内容按谱面 LN 占比自动选择 `Pattern` 或 `Etterna`
- `/ma -p <bid>`：`Pattern`，主体显示键型分析
- `/ma -e <bid>`：`Etterna`，主体显示 Etterna 7 大键型分
- `/ma -g <bid>`：`Graph`，主体显示难度变化图
- `/ma help`：返回简短使用说明
- 仅支持纯数字 `bid`

注：对于非4/6/7K谱面，主体内容将自动回退为Pattern显示。