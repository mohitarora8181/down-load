# 📥 YouTube & Instagram Video Downloader API

A FastAPI-based REST API to download videos and audio from YouTube and Instagram.

---

## 🚀 Features

- Download YouTube videos in multiple qualities (360p, 480p, 720p, 1080p, best)
- Download Instagram reels, posts and videos
- Extract audio (m4a) from YouTube and Instagram
- Stream files directly with correct filename and format
- Returns direct download URL and stream URL

---

## 📦 Requirements

- Python 3.8+
- FastAPI
- yt-dlp
- instaloader
- httpx
- uvicorn

---

## 🔧 Installation

**1. Clone the repository**
```bash
git clone https://github.com/mohitarora8181/down-load.git
cd down-load
```

**2. Install dependencies**
```bash
pip install fastapi yt-dlp instaloader httpx uvicorn
```

**3. Run the server**
```bash
uvicorn app:app --reload
```

Server will start at `http://127.0.0.1:8000`

---

## 📡 API Endpoints

### 1. `/download` - Get video/audio info and download URL

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | string | ✅ | - | YouTube or Instagram URL |
| `quality` | string | ❌ | `720p` | Video quality (YouTube only) |
| `output_format` | string | ❌ | `video` | `video` or `audio` |

**Quality options:** `360p`, `480p`, `720p`, `1080p`, `best`

---

### 2. `/stream` - Stream and download file directly

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `download_url` | string | ✅ | - | Direct file URL |
| `filename` | string | ❌ | `audio.m4a` | Output filename |
| `media_type` | string | ❌ | `audio/mp4` | MIME type |

---

## 📝 Example Usage

### YouTube Video
```
GET http://127.0.0.1:8000/download?url=https://www.youtube.com/watch?v=VIDEO_ID&quality=720p&output_format=video
```

### YouTube Audio
```
GET http://127.0.0.1:8000/download?url=https://www.youtube.com/watch?v=VIDEO_ID&output_format=audio
```

### Instagram Reel/Post Video
```
GET http://127.0.0.1:8000/download?url=https://www.instagram.com/reels/REEL_ID/&output_format=video
```

### Instagram Audio
```
GET http://127.0.0.1:8000/download?url=https://www.instagram.com/reels/REEL_ID/&output_format=audio
```

---

## 📤 Example Response

### Video Response
```json
{
    "title": "Video Title",
    "thumbnail": "https://thumbnail_url...",
    "duration": 120,
    "resolution": "1280x720",
    "source": "youtube",
    "output_format": "mp4",
    "download_url": "https://direct_video_url...",
    "stream_url": "http://127.0.0.1:8000/stream?download_url=...&filename=Video Title.mp4&media_type=video/mp4"
}
```

### Audio Response
```json
{
    "title": "Video Title",
    "thumbnail": "https://thumbnail_url...",
    "duration": 120,
    "source": "youtube",
    "output_format": "m4a",
    "download_url": "https://direct_audio_url...",
    "stream_url": "http://127.0.0.1:8000/stream?download_url=...&filename=Video Title.m4a&media_type=audio/mp4"
}
```

---

## 📱 Flutter Integration

```dart
import 'package:dio/dio.dart';

final dio = Dio();

// Get download info
final response = await dio.get(
    'http://YOUR_SERVER_IP:8000/download',
    queryParameters: {
        'url': 'YOUTUBE_OR_INSTAGRAM_URL',
        'quality': '720p',
        'output_format': 'video',
    },
);

final data = response.data;
final streamUrl = data['stream_url'];

// Download file using stream_url
await dio.download(
    streamUrl,
    '/storage/emulated/0/Movies/video.mp4',
);
```

---

## 📱 Kotlin Integration

```kotlin
import java.net.URL
import org.json.JSONObject

// Get download info
val response = URL("http://YOUR_SERVER_IP:8000/download?url=YOUR_URL&quality=720p&output_format=video")
    .readText()
val data = JSONObject(response)
val streamUrl = data.getString("stream_url")

// Download file using stream_url
// Use OkHttp or Retrofit to download the file
```

---

## ⚠️ Notes

- `stream_url` forces the browser/app to **download** the file with correct filename
- `download_url` is a **direct URL** that may open in browser
- Audio format will be **m4a** (better quality than mp3, no FFmpeg needed)
- Instagram supports **public posts and reels** only
- YouTube quality above **720p** requires FFmpeg installed
- Direct URLs are **temporary** and expire after some time

---

## 📂 Supported URL Formats

### YouTube
```
https://www.youtube.com/watch?v=VIDEO_ID
https://youtu.be/VIDEO_ID
```

### Instagram
```
https://www.instagram.com/reels/REEL_ID/
https://www.instagram.com/reel/REEL_ID/
https://www.instagram.com/p/POST_ID/
```

---

## 📄 License

MIT License