import os
import shutil
import urllib.request
from urllib.parse import urlparse, unquote

VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".m4v", ".ogv")


def _download_video(url: str, output_dir: str = "downloads", filename: str = "") -> str:
    """Download a video from a direct URL and save it to output_dir.

    Returns a human readable status string, matching the other tools.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return f"Invalid URL (must start with http:// or https://): {url}"

    try:
        os.makedirs(output_dir, exist_ok=True)

        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            content_type = response.headers.get("Content-Type", "")
            if not (content_type.startswith("video/")
                    or content_type.startswith("application/octet-stream")
                    or parsed.path.lower().endswith(VIDEO_EXTENSIONS)):
                return f"URL does not look like a direct video link (Content-Type: {content_type})"

            if not filename:
                filename = os.path.basename(unquote(parsed.path)) or "video.mp4"
            filename = os.path.basename(filename)  # prevent path traversal
            if not filename.lower().endswith(VIDEO_EXTENSIONS):
                filename += ".mp4"

            file_path = os.path.join(output_dir, filename)
            with open(file_path, "wb") as f:
                shutil.copyfileobj(response, f)

        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        return f"Successfully downloaded video to {file_path} ({size_mb:.2f} MB)"
    except Exception as e:
        return f"Error downloading video: {str(e)}"


def _split_video_into_frames(video_path: str, output_dir: str = "", every_n_frames: int = 1,
                             image_format: str = "jpg", max_frames: int = 0) -> str:
    """Split a local video file into image frames using OpenCV.

    video_path: path to the video file.
    output_dir: folder for the frames (defaults to '<video name>_frames' next to the video).
    every_n_frames: save one frame out of every N (1 = every frame).
    image_format: jpg or png.
    max_frames: stop after saving this many frames (0 = no limit).

    Returns a human readable status string, matching the other tools.
    """
    try:
        import cv2
    except ImportError:
        return "OpenCV is not installed. Run: pip install opencv-python"

    if not os.path.isfile(video_path):
        return f"Video file not found: {video_path}"

    try:
        every_n_frames = max(1, int(every_n_frames or 1))
        max_frames = max(0, int(max_frames or 0))
    except (TypeError, ValueError):
        return "every_n_frames and max_frames must be whole numbers"

    image_format = (image_format or "jpg").lower().lstrip(".")
    if image_format not in ("jpg", "jpeg", "png"):
        return f"Unsupported image format: {image_format} (use jpg or png)"

    if not output_dir:
        base = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(os.path.dirname(video_path), f"{base}_frames")

    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        return f"Could not open video (unsupported or corrupt file): {video_path}"

    try:
        os.makedirs(output_dir, exist_ok=True)

        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        digits = max(6, len(str(total_frames)))

        read_count = 0
        saved_count = 0
        while True:
            success, frame = capture.read()
            if not success:
                break
            if read_count % every_n_frames == 0:
                frame_path = os.path.join(output_dir, f"frame_{read_count:0{digits}d}.{image_format}")
                if not cv2.imwrite(frame_path, frame):
                    return f"Failed to write frame to {frame_path}"
                saved_count += 1
                if max_frames and saved_count >= max_frames:
                    break
            read_count += 1

        return f"Successfully saved {saved_count} frames to {output_dir}"
    except Exception as e:
        return f"Error splitting video into frames: {str(e)}"
    finally:
        capture.release()


if __name__ == '__main__':
    print(_download_video("https://samplelib.com/lib/preview/mp4/sample-5s.mp4", "../downloads"))
    print(_split_video_into_frames("../downloads/sample-5s.mp4", "../downloads/sample-5s_frames", every_n_frames=10))
