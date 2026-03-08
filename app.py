from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import re
import httpx
from urllib.parse import quote
import os
import traceback

app = FastAPI()


def extract_youtube_id(url: str) -> str:
    pattern = r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})'
    match = re.search(pattern, url)
    return match.group(1) if match else url


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


@app.get("/")
def home():
    return {"status": "running"}


@app.get("/stream")
async def stream_download(download_url: str, filename: str = "video.mp4", media_type: str = "video/mp4"):
    async def stream_file():
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.instagram.com/",
            "Origin": "https://www.instagram.com",
        }
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True, headers=headers) as client:
            async with client.stream("GET", download_url) as response:
                if response.status_code not in [200, 206]:
                    raise HTTPException(status_code=400, detail=f"Failed to fetch file: {response.status_code}")
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk

    return StreamingResponse(
        stream_file(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/download")
async def download(url: str, output_format: str = "video"):
    try:
        if output_format not in ["video", "audio"]:
            raise HTTPException(status_code=400, detail="Invalid output_format. Choose from: video, audio")

        if not is_youtube(url) and not is_instagram(url):
            raise HTTPException(status_code=400, detail="Only YouTube and Instagram URLs are supported")

        if is_instagram(url):
            return await handle_instagram(url, output_format)

        return await handle_youtube(url, output_format)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}")


async def handle_instagram(url: str, output_format: str):
    import yt_dlp
    if output_format == "audio":
        ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'bestaudio[ext=m4a]/bestaudio'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            best = next((f for f in reversed(formats) if f.get('acodec') != 'none' and f.get('vcodec') == 'none'), formats[-1])
            title = sanitize_title(info.get('title') or "instagram_audio")
            return {
                "title": title,
                "thumbnail": info.get('thumbnail'),
                "duration": info.get('duration'),
                "source": "instagram",
                "output_format": best.get('ext', 'm4a'),
                "download_url": best.get('url'),
                "stream_url": build_stream_url(best.get('url'), f"{title}.{best.get('ext', 'm4a')}", "audio/mp4"),
            }
    else:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'best[ext=mp4]/best'}
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


async def handle_youtube(url: str, output_format: str):
    api_url = f"https://ytdl.socialplug.io/api/video-info?url={quote(url, safe='')}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(api_url)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch video info")
        data = response.json()

    title = sanitize_title(data.get('title') or "video")
    thumbnail = data.get('image')
    duration = int(data.get('lengthSeconds') or 0)
    format_options = data.get('format_options', {})

    if output_format == "audio":
        audio_data = format_options.get('audio', {}).get('mp3')

        if not audio_data or audio_data is False or not isinstance(audio_data, dict) or not audio_data.get('url'):
            raise HTTPException(status_code=400, detail={
                "message": "Audio is not available for this video",
                "videoId": extract_youtube_id(url),
            })

        return {
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "source": "youtube",
            "output_format": "mp3",
            "download_url": audio_data.get('url'),
            "stream_url": audio_data.get('url'),
        }

    else:
        mp4_list = format_options.get('video', {}).get('mp4', [])

        if not mp4_list:
            raise HTTPException(status_code=400, detail="No video formats available")

        mp4_with_audio = [f for f in mp4_list if f.get('hasAudio') is True]

        if not mp4_with_audio:
            raise HTTPException(status_code=400, detail="No video with audio available")

        selected = mp4_with_audio[-1]

        return {
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "resolution": selected.get('quality', 'unknown'),
            "source": "youtube",
            "output_format": "mp4",
            "download_url": selected.get('url'),
            "stream_url": selected.get('url'),
        }