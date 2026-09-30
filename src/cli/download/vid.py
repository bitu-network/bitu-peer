# file: src/cli/download/vid.py
#!/usr/bin/env python3
import argparse
import sys
import yt_dlp


def download_video(url: str, highest_quality: bool = False):
    """Downloads a video using yt-dlp.

    Defaults to FullHD (1080p) or lower if 1080p isn't available.
    If highest_quality is True, downloads the absolute best quality available.
    """
    # 1080p default format string (prefers 1080p, falls back to next best)
    format_str = "bestvideo[height<=1080]+bestaudio/best[height<=1080]"

    if highest_quality:
        # Unlimited best quality format string
        format_str = "bestvideo+bestaudio/best"

    ydl_opts = {
        "format": format_str,
        # Merges video and audio streams into an MP4 container automatically
        "merge_output_format": "mp4",
        # Standard descriptive output template
        "outtmpl": "[%(upload_date>%Y.%m.%d)s~] %(title)s [%(id)s].%(ext)s",
    }

    print(
        f"[+] Quality target: {'Highest Available' if highest_quality else 'FullHD (1080p)'}"
    )
    print(f"[+] Fetching video info...")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        print(f"\n[x] An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Download videos with yt-dlp. Defaults to FullHD (1080p)."
    )
    parser.add_argument("url", help="The URL of the video to download")
    parser.add_argument(
        "-b",
        "--best",
        action="store_true",
        help="Download in the highest possible quality (bypasses 1080p limit)",
    )

    args = parser.parse_args()
    download_video(args.url, highest_quality=args.best)


if __name__ == "__main__":
    main()
