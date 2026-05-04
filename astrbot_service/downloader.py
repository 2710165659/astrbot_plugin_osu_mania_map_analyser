from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import ManiaMapAnalyserError


def download_beatmap_file(bid: str, temp_dir: Path) -> Path:
    temp_dir.mkdir(parents=True, exist_ok=True)
    target_path = temp_dir / f"{bid}.osu"
    if target_path.is_file() and target_path.stat().st_size > 0:
        return target_path

    request = Request(
        url=f"https://osu.ppy.sh/osu/{bid}",
        headers={"User-Agent": "astrbot-osu-mania-map-analyser/1.0"},
    )

    try:
        with urlopen(request, timeout=20) as response:
            data = response.read()
    except HTTPError as exc:
        if exc.code == 404:
            raise ManiaMapAnalyserError(f"未找到 bid {bid} 对应的谱面") from exc
        raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：http {exc.code}") from exc
    except URLError as exc:
        raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：{exc.reason}") from exc

    if not data:
        raise ManiaMapAnalyserError(f"下载谱面 {bid} 失败：返回内容为空")

    target_path.write_bytes(data)
    return target_path
