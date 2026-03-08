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
    quality_formats = {
        "best":  "best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/best",
        "1080p": "best[ext=mp4][height<=1080][vcodec!=none][acodec!=none]/best[height<=1080]/best",
        "720p":  "best[ext=mp4][height<=720][vcodec!=none][acodec!=none]/best[height<=720]/best",
        "480p":  "best[ext=mp4][height<=480][vcodec!=none][acodec!=none]/best[height<=480]/best",
        "360p":  "best[ext=mp4][height<=360][vcodec!=none][acodec!=none]/best[height<=360]/best",
    }

    if output_format == "audio":
        ydl_opts = {
            **get_yt_dlp_opts_base(),
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio',
            'prefer_free_formats': False,
        }
    else:
        if quality not in quality_formats:
            raise HTTPException(status_code=400, detail=f"Invalid quality. Choose from: {', '.join(quality_formats.keys())}")
        ydl_opts = {
            **get_yt_dlp_opts_base(),
            'format': quality_formats[quality],
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = sanitize_title(info.get('title') or "video")

        if output_format == "audio":
            formats = info.get('formats', [])
            best_audio = get_best_audio(formats)
            ext = best_audio.get('ext', 'm4a')
            return {
                "title": title,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "source": "youtube",
                "output_format": ext,
                "download_url": best_audio.get('url'),
                "stream_url": build_stream_url(best_audio.get('url'), f"{title}.{ext}", "audio/mp4"),
            }
        else:
            return {
                "title": title,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "resolution": f"{info.get('width')}x{info.get('height')}",
                "source": "youtube",
                "output_format": "mp4",
                "download_url": info.get('url'),
                "stream_url": build_stream_url(info.get('url'), f"{title}.mp4", "video/mp4"),
            }