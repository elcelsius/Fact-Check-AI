"""Referência manual do vídeo, independente dos tempos originais da captura."""

import re


MAX_VIDEO_SECONDS = 999 * 3600 + 59 * 60 + 59


def validate_video_position(seconds: int | None) -> int | None:
    if seconds is not None and (type(seconds) is not int or not 0 <= seconds <= MAX_VIDEO_SECONDS):
        raise ValueError("Informe uma posição do vídeo entre 00:00:00 e 999:59:59.")
    return seconds


def parse_video_position(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"[0-9]+:[0-5][0-9](?::[0-5][0-9])?", value):
        raise ValueError("Use MM:SS ou HH:MM:SS, por exemplo 12:30 ou 01:12:30.")
    parts = [int(part) for part in value.split(":")]
    seconds = parts[-1] + parts[-2] * 60
    if len(parts) == 3:
        seconds += parts[0] * 3600
    return validate_video_position(seconds)


def timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def video_range(source: dict, offset_seconds: int) -> str:
    return f"{timestamp(source['start'] + offset_seconds)} → {timestamp(source['end'] + offset_seconds)}"


def describe_time(source: dict, offset_seconds: int | None = None) -> str:
    capture = f"captura: {source['start']:.1f}–{source['end']:.1f} s"
    if offset_seconds is None:
        return capture
    return f"Vídeo (ref.): {video_range(source, offset_seconds)} · {capture}"
