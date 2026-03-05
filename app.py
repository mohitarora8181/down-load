from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import yt_dlp
import instaloader
import re
import httpx
from urllib.parse import quote

app = FastAPI()


def is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_instagram(url: str) -> bool:
    return "instagram.com" in url


def get_instagram_shortcode(url: str) -> str:
    match = re.search(r'/(?:reels|reel|p)/([^/?]+)', url)
    if match:
        return match.group(1)
    raise HTTPException(status_code=400, detail="Invalid Instagram URL")


def sanitize_title(title: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", title)


def build_stream_url(direct_url: str, filename: str, media_type: str) -> str:
    encoded_url = quote(direct_url, safe='')
    return f"http://127.0.0.1:8000/stream?download_url={encoded_url}&filename={filename}&media_type={media_type}"


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


@app.get("/stream")
async def stream_download(download_url: str, filename: str = "audio.m4a", media_type: str = "audio/mp4"):
    async def stream_file():
        async with httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.instagram.com/",
            }
        ) as client:
            async with client.stream("GET", download_url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to fetch file: {response.status_code}"
                    )
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
            raise HTTPException(
                status_code=400,
                detail="Invalid output_format. Choose from: video, audio"
            )

        if not is_youtube(url) and not is_instagram(url):
            raise HTTPException(
                status_code=400,
                detail="Invalid URL. Only YouTube and Instagram URLs are supported"
            )

        if is_instagram(url):
            return await handle_instagram(url, output_format)

        return await handle_youtube(url, quality, output_format)

    except instaloader.exceptions.InstaloaderException as e:
        raise HTTPException(status_code=400, detail="Instagram Error: " + str(e))
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail="YouTube Error: " + str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error: " + str(e))


async def handle_instagram(url: str, output_format: str):
    if output_format == "audio":
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'quiet': True,
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
            'format': 'best[ext=mp4]/best',
            'quiet': True,
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
        "best": "best[ext=mp4][vcodec!=none][acodec!=none]/best[ext=mp4]/best",
        "1080p": "best[ext=mp4][height<=1080][vcodec!=none][acodec!=none]/best[height<=1080]",
        "720p":  "best[ext=mp4][height<=720][vcodec!=none][acodec!=none]/best[height<=720]",
        "480p":  "best[ext=mp4][height<=480][vcodec!=none][acodec!=none]/best[height<=480]",
        "360p":  "best[ext=mp4][height<=360][vcodec!=none][acodec!=none]/best[height<=360]",
    }

    if output_format == "audio":
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio',
            'quiet': True,
            'prefer_free_formats': False,
        }
    else:
        if quality not in quality_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid quality. Choose from: {', '.join(quality_formats.keys())}"
            )
        ydl_opts = {
            'format': quality_formats[quality],
            'quiet': True,
        }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        title = sanitize_title(info.get('title') or "video")

        if output_format == "audio":
            formats = info.get('formats', [])
            best_audio = get_best_audio(formats)
            ext = best_audio.get('ext')

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