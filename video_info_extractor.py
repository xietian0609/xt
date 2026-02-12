#!/usr/bin/env python3
"""视频重要信息抽取工具。

功能：
1. 提取基础元数据（时长、分辨率、帧率、编码格式、码率）
2. 基于帧间差异检测关键片段（镜头切换）
3. 输出结构化 JSON 报告

依赖：
- ffprobe（来自 ffmpeg）
- 可选：opencv-python（用于镜头切换检测）
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class VideoMetadata:
    path: str
    duration_seconds: float
    size_bytes: int
    bit_rate: int | None
    format_name: str
    width: int | None
    height: int | None
    fps: float | None
    codec: str | None


@dataclass
class SceneBoundary:
    frame_index: int
    timestamp_seconds: float
    score: float


@dataclass
class ExtractionReport:
    metadata: VideoMetadata
    summary: list[str]
    key_moments: list[SceneBoundary]


class ExtractionError(RuntimeError):
    """无法完成抽取时抛出的异常。"""


def _run_ffprobe(video_path: Path) -> dict[str, Any]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise ExtractionError("未检测到 ffprobe，请先安装 ffmpeg。") from exc
    except subprocess.CalledProcessError as exc:
        raise ExtractionError(f"ffprobe 执行失败: {exc.stderr.strip()}") from exc

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ExtractionError("ffprobe 输出解析失败（非 JSON）。") from exc


def _parse_fraction(value: str | None) -> float | None:
    if not value:
        return None
    if "/" not in value:
        try:
            return float(value)
        except ValueError:
            return None
    num_str, den_str = value.split("/", 1)
    try:
        num = float(num_str)
        den = float(den_str)
    except ValueError:
        return None
    if den == 0:
        return None
    return num / den


def extract_metadata(video_path: Path) -> VideoMetadata:
    raw = _run_ffprobe(video_path)
    fmt = raw.get("format", {})
    streams = raw.get("streams", [])

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})

    duration = float(fmt.get("duration", 0.0) or 0.0)
    size_bytes = int(fmt.get("size", 0) or 0)
    bit_rate = fmt.get("bit_rate")
    return VideoMetadata(
        path=str(video_path),
        duration_seconds=duration,
        size_bytes=size_bytes,
        bit_rate=int(bit_rate) if bit_rate and str(bit_rate).isdigit() else None,
        format_name=str(fmt.get("format_name", "unknown")),
        width=video_stream.get("width"),
        height=video_stream.get("height"),
        fps=_parse_fraction(video_stream.get("avg_frame_rate")),
        codec=video_stream.get("codec_name"),
    )


def detect_key_moments(video_path: Path, sensitivity: float = 2.8, max_points: int = 12) -> list[SceneBoundary]:
    """基于灰度帧差检测关键时刻。

    sensitivity 越小越敏感；越大越保守。
    """
    try:
        import cv2  # type: ignore
    except Exception:
        return []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ExtractionError("无法读取视频，请确认文件路径和编码是否可用。")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    prev_gray = None
    diffs: list[tuple[int, float]] = []
    frame_index = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff = cv2.absdiff(gray, prev_gray)
            score = float(diff.mean())
            diffs.append((frame_index, score))
        prev_gray = gray
        frame_index += 1

    cap.release()

    if not diffs:
        return []

    scores = [s for _, s in diffs]
    baseline = statistics.mean(scores)
    spread = statistics.pstdev(scores) or 1.0
    threshold = baseline + sensitivity * spread

    boundaries = [
        SceneBoundary(frame_index=i, timestamp_seconds=i / fps, score=s)
        for i, s in diffs
        if s >= threshold
    ]

    # 对时间接近的切换点做稀疏化，避免同一切换出现多个点。
    sparse: list[SceneBoundary] = []
    min_gap_sec = 1.2
    for b in boundaries:
        if not sparse or b.timestamp_seconds - sparse[-1].timestamp_seconds >= min_gap_sec:
            sparse.append(b)

    if len(sparse) <= max_points:
        return sparse

    # 仅保留分值最高的 max_points 个，时间升序输出。
    top = sorted(sparse, key=lambda x: x.score, reverse=True)[:max_points]
    return sorted(top, key=lambda x: x.timestamp_seconds)


def _human_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = min(int(math.log(size_bytes, 1024)), len(units) - 1)
    value = size_bytes / (1024**idx)
    return f"{value:.2f} {units[idx]}"


def build_summary(metadata: VideoMetadata, key_moments: list[SceneBoundary]) -> list[str]:
    lines = [
        f"视频时长约 {metadata.duration_seconds:.1f} 秒，封装格式 {metadata.format_name}。",
        f"文件大小 {_human_size(metadata.size_bytes)}，编码 {metadata.codec or 'unknown'}。",
    ]
    if metadata.width and metadata.height:
        lines.append(f"分辨率 {metadata.width}x{metadata.height}。")
    if metadata.fps:
        lines.append(f"平均帧率约 {metadata.fps:.2f} FPS。")

    if key_moments:
        ts = ", ".join(f"{m.timestamp_seconds:.1f}s" for m in key_moments[:6])
        lines.append(f"检测到 {len(key_moments)} 个疑似关键切换时刻：{ts}。")
    else:
        lines.append("未检测到明显镜头切换（可能缺少 OpenCV 或视频变化较平缓）。")
    return lines


def extract_video_highlights(video_path: Path) -> ExtractionReport:
    metadata = extract_metadata(video_path)
    key_moments = detect_key_moments(video_path)
    summary = build_summary(metadata, key_moments)
    return ExtractionReport(metadata=metadata, summary=summary, key_moments=key_moments)


def _to_json(report: ExtractionReport) -> str:
    payload = {
        "metadata": asdict(report.metadata),
        "summary": report.summary,
        "key_moments": [asdict(item) for item in report.key_moments],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="视频重要信息抽取")
    parser.add_argument("video", type=Path, help="输入视频文件路径")
    parser.add_argument("-o", "--output", type=Path, help="输出 JSON 文件路径")
    args = parser.parse_args()

    if not args.video.exists():
        raise SystemExit(f"文件不存在: {args.video}")

    report = extract_video_highlights(args.video)
    text = _to_json(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
        print(f"抽取完成，结果已写入: {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
