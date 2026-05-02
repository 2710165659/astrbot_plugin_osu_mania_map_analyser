class ManiaMapAnalyserError(Exception):
    """Plugin-local error type for beatmap download and render failures."""


class NonManiaBeatmapError(ManiaMapAnalyserError):
    """Raised when the requested beatmap is not osu!mania."""
