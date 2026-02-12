# 视频重要信息抽取

一个轻量的 Python 命令行工具，用于从视频中抽取“重要信息”：

- 基础元数据：时长、分辨率、帧率、编码、码率、文件大小
- 关键时刻：基于帧间差异检测疑似镜头切换点
- 结构化输出：JSON 结果，便于后续接入检索/摘要流程

## 依赖

- Python 3.10+
- `ffprobe`（包含在 ffmpeg）
- 可选：`opencv-python`（用于关键时刻检测）

## 使用方式

```bash
python3 video_info_extractor.py /path/to/video.mp4 -o report.json
```

若不传 `-o`，则直接打印 JSON 到终端。

## 输出示例

```json
{
  "metadata": {
    "path": "demo.mp4",
    "duration_seconds": 16.1,
    "size_bytes": 8590012,
    "bit_rate": 4268930,
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "width": 1920,
    "height": 1080,
    "fps": 29.97,
    "codec": "h264"
  },
  "summary": [
    "视频时长约 16.1 秒，封装格式 mov,mp4,m4a,3gp,3g2,mj2。",
    "文件大小 8.19 MB，编码 h264。",
    "分辨率 1920x1080。",
    "平均帧率约 29.97 FPS。",
    "检测到 4 个疑似关键切换时刻：3.1s, 6.8s, 10.2s, 12.6s。"
  ],
  "key_moments": [
    {
      "frame_index": 93,
      "timestamp_seconds": 3.1,
      "score": 22.43
    }
  ]
}
```

## 测试

```bash
python3 -m unittest discover -s tests
```
