"""Video tools: download a video from a direct URL and split a video into image frames."""

from __future__ import annotations

import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

from .base import Tool, ToolError
from .filesystem import Workspace

VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".m4v", ".ogv")
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024
CHUNK = 1024 * 1024


def download_video(workspace: Workspace, url: str, output_dir: str = "downloads", filename: str = "") -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ToolError(f"URL must start with http:// or https://: {url}")

    out_dir = workspace.resolve(output_dir or "downloads")
    out_dir.mkdir(parents=True, exist_ok=True)

    request = urllib.request.Request(url, headers={"User-Agent": "devsecops-agent/0.2"})  # noqa: S310
    # Scheme is restricted to http/https above, so file:// and custom schemes cannot reach urlopen.
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 # nosec B310
        content_type = response.headers.get("Content-Type", "")
        looks_like_video = content_type.startswith(
            ("video/", "application/octet-stream")
        ) or parsed.path.lower().endswith(VIDEO_EXTENSIONS)
        if not looks_like_video:
            raise ToolError(f"URL does not look like a direct video link (Content-Type: {content_type})")

        name = Path(filename or unquote(parsed.path)).name or "video.mp4"  # .name strips any directories
        if not name.lower().endswith(VIDEO_EXTENSIONS):
            name += ".mp4"
        target = out_dir / name

        written = 0
        with target.open("wb") as fh:
            while chunk := response.read(CHUNK):
                written += len(chunk)
                if written > MAX_DOWNLOAD_BYTES:
                    fh.close()
                    target.unlink(missing_ok=True)
                    raise ToolError(f"Download is larger than {MAX_DOWNLOAD_BYTES // CHUNK} MB")
                fh.write(chunk)

    return f"Downloaded {target.relative_to(workspace.root)} ({written / CHUNK:.2f} MB)"


def split_video_into_frames(
    workspace: Workspace,
    video_path: str,
    output_dir: str = "",
    every_n_frames: int = 1,
    image_format: str = "jpg",
    max_frames: int = 0,
) -> str:
    try:
        import cv2
    except ImportError as exc:
        raise ToolError("OpenCV is not installed. Run: pip install 'devsecops-agent[video]'") from exc

    video = workspace.resolve(video_path)
    if not video.is_file():
        raise ToolError(f"Video file not found: {video_path}")

    every_n_frames = max(1, int(every_n_frames or 1))
    max_frames = max(0, int(max_frames or 0))
    image_format = (image_format or "jpg").lower().lstrip(".")
    if image_format not in ("jpg", "jpeg", "png"):
        raise ToolError(f"Unsupported image format: {image_format} (use jpg or png)")

    out_dir = workspace.resolve(output_dir) if output_dir else video.with_name(f"{video.stem}_frames")
    out_dir.mkdir(parents=True, exist_ok=True)

    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ToolError(f"Could not open video: {video_path}")
    try:
        digits = max(6, len(str(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))))
        read = saved = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if read % every_n_frames == 0:
                frame_path = out_dir / f"frame_{read:0{digits}d}.{image_format}"
                if not cv2.imwrite(str(frame_path), frame):
                    raise ToolError(f"Failed to write {frame_path.name}")
                saved += 1
                if max_frames and saved >= max_frames:
                    break
            read += 1
    finally:
        capture.release()
    return f"Saved {saved} frames to {out_dir.relative_to(workspace.root)}"


def video_tools(workspace: Workspace) -> list[Tool]:
    return [
        Tool(
            name="download_video",
            description="Download a video from a direct http(s) video URL into the workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Direct URL of the video file"},
                    "output_dir": {"type": "string", "description": "Folder to save into (default: downloads)"},
                    "filename": {"type": "string", "description": "Optional file name"},
                },
                "required": ["url"],
            },
            handler=lambda **kw: download_video(workspace, **kw),
        ),
        Tool(
            name="split_video_into_frames",
            description="Split a video in the workspace into image frames.",
            input_schema={
                "type": "object",
                "properties": {
                    "video_path": {"type": "string", "description": "Path to the video file"},
                    "output_dir": {"type": "string", "description": "Folder for frames (default: <name>_frames)"},
                    "every_n_frames": {"type": "integer", "description": "Keep one frame in every N (default 1)"},
                    "image_format": {"type": "string", "enum": ["jpg", "png"], "description": "Frame format"},
                    "max_frames": {"type": "integer", "description": "Stop after this many frames (0 = no limit)"},
                },
                "required": ["video_path"],
            },
            handler=lambda **kw: split_video_into_frames(workspace, **kw),
        ),
    ]
