# astrbot_plugin_osu_mania_map_analyser

AstrBot 插件版 `osumania_map_analyser`。机器人可通过 `/ma <bid>` 下载 `.osu`、用 Playwright 驱动常驻 Chromium 渲染图表，并返回 PNG 图片。

原始项目地址：<https://github.com/LeoBlackMT/osumania_map_analyser>

## 使用

```text
/ma 2617355
/ma help
/map 2617355
/mae 2617355
/mag 2617355
```

- `/ma <bid>`：默认模式，使用当前插件配置中的 `Card Body Content`
- `/map <bid>`：强制 `Pattern`
- `/mae <bid>`：强制 `Etterna`
- `/mag <bid>`：强制 `Graph`
- `/ma help`：返回简短使用说明
- 仅支持纯数字 `bid`

## 说明

- 原始项目文件已完整复制到 `osumania_map_analyser/` 下，未直接修改其源码。
- 默认设置项与原项目保持一致：`content_bar=Auto`、`sr_text=Auto`、`diff_text=Difficulty`。
- `.osu` 下载缓存与渲染后的 PNG 都写入系统临时目录：
  - `.../astrbot_plugin_osu_mania_map_analyser/osu-download-cache`
  - `.../astrbot_plugin_osu_mania_map_analyser/outputs`
- 相同 `bid + 渲染参数组合` 会直接命中 PNG 缓存，不重复截图。
