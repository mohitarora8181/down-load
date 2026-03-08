from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import yt_dlp
import re
import httpx
from urllib.parse import quote
import os
import traceback

app = FastAPI()


def is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_instagram(url: str) -> bool:
    return "instagram.com" in url


def sanitize_title(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title)


def build_stream_url(direct_url: str, filename: str, media_type: str) -> str:
    encoded_url = quote(direct_url, safe='')
    base_url = os.environ.get('BASE_URL', 'https://down-load.onrender.com')
    return f"{base_url}/stream?download_url={encoded_url}&filename={filename}&media_type={media_type}"


def get_best_audio(formats: list) -> dict:
    audio_formats = [
        f for f in formats
        if f.get('acodec') != 'none'
        and f.get('vcodec') == 'none'
        and f.get('ext') in ['m4a', 'mp3']
    ]
    if not audio_formats:
        audio_formats = [
            f for f in formats
            if f.get('acodec') != 'none'
            and f.get('vcodec') == 'none'
        ]
    return audio_formats[-1] if audio_formats else formats[-1]


def get_cookies_file() -> str | None:
    """read cookies from environment variable and save to temp file"""
    cookies_content = os.environ.get('YOUTUBE_COOKIES')
    if not cookies_content:
        return None
    cookies_path = '/tmp/yt_cookies.txt'
    with open(cookies_path, 'w') as f:
        f.write(cookies_content)
    return cookies_path


def get_yt_dlp_opts_base() -> dict:
    """base yt-dlp options with cookies if available"""
    opts = {
        'quiet': True,
        'no_warnings': True,
    }
    cookies_file = get_cookies_file()
    if cookies_file:
        opts['cookiefile'] = cookies_file
    return opts


@app.get("/")
def home():
    cookies_available = bool(os.environ.get('YOUTUBE_COOKIES'))
    return {
        "status": "running",
        "cookies": "available ✅" if cookies_available else "not set ❌",
    }


@app.get("/stream")
async def stream_download(download_url: str, filename: str = "audio.m4a", media_type: str = "audio/mp4"):
    async def stream_file():
        is_youtube_url = "googlevideo.com" in download_url or "youtube.com" in download_url
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        if is_youtube_url:
            headers.update({
                "Referer": "https://www.youtube.com/",
                "Origin": "https://www.youtube.com",
            })
        else:
            headers.update({
                "Referer": "https://www.instagram.com/",
                "Origin": "https://www.instagram.com",
            })

        async with httpx.AsyncClient(
            timeout=300.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            async with client.stream("GET", download_url) as response:
                if response.status_code not in [200, 206]:
                    raise HTTPException(status_code=400, detail=f"Failed to fetch file: {response.status_code}")
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk

    return StreamingResponse(
        stream_file(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Accept-Ranges": "bytes",
        }
    )


@app.get("/download")
async def download(url: str, quality: str = "720p", output_format: str = "video"):
    try:
        if output_format not in ["video", "audio"]:
            raise HTTPException(status_code=400, detail="Invalid output_format. Choose from: video, audio")

        if not is_youtube(url) and not is_instagram(url):
            raise HTTPException(status_code=400, detail="Invalid URL. Only YouTube and Instagram URLs are supported")

        if is_instagram(url):
            return await handle_instagram(url, output_format)

        return await handle_youtube(url, quality, output_format)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")


async def handle_instagram(url: str, output_format: str):
    if output_format == "audio":
        ydl_opts = {
            **get_yt_dlp_opts_base(),
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'prefer_free_formats': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            best_audio = get_best_audio(formats)
            title = sanitize_title(info.get('title') or "instagram_audio")
            return {
                "title": title,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "source": "instagram",
                "output_format": "m4a",
                "download_url": best_audio.get('url'),
                "stream_url": build_stream_url(best_audio.get('url'), f"{title}.m4a", "audio/mp4"),
            }
    else:
        ydl_opts = {
            **get_yt_dlp_opts_base(),
            'format': 'best[ext=mp4]/best',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = sanitize_title(info.get('title') or "instagram_video")
            return {
                "title": title,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "resolution": f"{info.get('width')}x{info.get('height')}",
                "source": "instagram",
                "output_format": "mp4",
                "download_url": info.get('url'),
                "stream_url": build_stream_url(info.get('url'), f"{title}.mp4", "video/mp4"),
            }


async def handle_youtube(url: str, quality: str, output_format: str):
    quality_map = {
        "best": None, "1080p": 1080,
        "720p": 720, "480p": 480, "360p": 360,
    }

    if quality not in quality_map:
        raise HTTPException(status_code=400, detail=f"Invalid quality. Choose from: {', '.join(quality_map.keys())}")

    height = quality_map[quality]

    # NO format filter — fetch ALL formats, pick manually
    ydl_opts = {
        **get_yt_dlp_opts_base(),
        'format': 'bestaudio/best' if output_format == "audio" else 'worstvideo',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # only extract info — no format filter crash
        info = ydl.sanitize_info(
            ydl.extract_info(url, download=False, process=False)
        )
        # process without format selection
        info = ydl.process_ie_result(info, download=False)

    # now pick format manually from all available
    formats = info.get('formats', [])
    title = sanitize_title(info.get('title') or "video")

    if output_format == "audio":
        # pick best audio only format
        audio_formats = [
            f for f in formats
            if f.get('acodec') not in (None, 'none')
            and f.get('vcodec') in (None, 'none')
            and f.get('url')
        ]
        if not audio_formats:
            # fallback — any format with audio
            audio_formats = [
                f for f in formats
                if f.get('acodec') not in (None, 'none')
                and f.get('url')
            ]
        if not audio_formats:
            audio_formats = [f for f in formats if f.get('url')]

        if not audio_formats:
            raise HTTPException(status_code=400, detail="No audio format found")

        # sort by bitrate — pick highest
        audio_formats.sort(key=lambda f: f.get('abr') or f.get('tbr') or 0)
        best = audio_formats[-1]
        ext = best.get('ext', 'm4a')
        return {
            "title": title,
            "thumbnail": info.get('thumbnail'),
            "duration": info.get('duration'),
            "source": "youtube",
            "output_format": ext,
            "download_url": best.get('url'),
            "stream_url": build_stream_url(best.get('url'), f"{title}.{ext}", "audio/mp4"),
        }

    else:
        # pick progressive format (video+audio in one file — no ffmpeg needed)
        progressive = [
            f for f in formats
            if f.get('vcodec') not in (None, 'none')
            and f.get('acodec') not in (None, 'none')
            and f.get('url')
            and (height is None or (f.get('height') or 0) <= height)
        ]
        # fallback — progressive any height
        if not progressive:
            progressive = [
                f for f in formats
                if f.get('vcodec') not in (None, 'none')
                and f.get('acodec') not in (None, 'none')
                and f.get('url')
            ]
        # fallback — any video
        if not progressive:
            progressive = [
                f for f in formats
                if f.get('vcodec') not in (None, 'none')
                and f.get('url')
            ]
        # last fallback
        if not progressive:
            progressive = [f for f in formats if f.get('url')]

        if not progressive:
            raise HTTPException(status_code=400, detail="No video format found")

        # sort by height — pick best
        progressive.sort(key=lambda f: f.get('height') or 0)
        best = progressive[-1]

        return {
            "title": title,
            "thumbnail": info.get('thumbnail'),
            "duration": info.get('duration'),
            "resolution": f"{best.get('width')}x{best.get('height')}",
            "source": "youtube",
            "output_format": best.get('ext', 'mp4'),
            "download_url": best.get('url'),
            "stream_url": build_stream_url(best.get('url'), f"{title}.mp4", "video/mp4"),
        }