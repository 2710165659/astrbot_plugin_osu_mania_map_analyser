# astrbot_plugin_osu_mania_map_analyser

AstrBot 插件版 `osumania_map_analyser`。机器人可通过 `/ma <bid>` 下载 `.osu`、用 Playwright 驱动常驻 Chromium 渲染图表，并返回 PNG 图片。![效果图](image.png)

原始项目地址：<https://github.com/LeoBlackMT/osumania_map_analyser>

> osumania_map_analyser文件即为原始项目文件(head 5dbd97c)，未改动，受astrbot插件安装行为限制，未采用submodule。

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

基于 `osumania_map_analyser` 实现本项目，可以分析键型，预估对应 RF/LN 段位。

```text
/ma <bid>       默认等同于 /ma -a <bid>
/ma -n <bid>    主体不显示任何内容，即短卡片模式
/ma -a <bid>    主体内容按谱面 LN 占比自动选择 Pattern 或 Etterna
/ma -p <bid>    主体显示 Pattern 键型分析，非 4/6/7K 主体自动回退 Pattern
/ma -e <bid>    主体显示 Etterna 7 大键型分
/ma -g <bid>    主体显示难度变化图，命令简写 /mag
/ma help        显示本帮助文本

示例:
/ma 5170433+dt1.1
```
