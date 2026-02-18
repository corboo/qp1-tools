# 🎬 Audio to Video Generator

A Streamlit web app that transforms audio files into AI-generated videos.

## Features

- 📝 **Auto-transcription** - Uses OpenAI Whisper
- 🎬 **AI Scene Generation** - GPT-4 creates scene descriptions from transcript
- 🎥 **Video Generation** - LTX Video creates cinematic clips
- 🔗 **Auto-assembly** - Stitches clips and merges audio

## Quick Start (Local)

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API keys:**
   ```bash
   mkdir -p .streamlit
   cp .streamlit/secrets.toml.example .streamlit/secrets.toml
   # Edit secrets.toml with your API keys
   ```

3. **Install ffmpeg** (required for audio/video processing):
   ```bash
   # macOS
   brew install ffmpeg
   
   # Ubuntu/Debian
   sudo apt install ffmpeg
   ```

4. **Run the app:**
   ```bash
   streamlit run app.py
   ```

## Deploy to Streamlit Cloud

1. **Push to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Audio to Video Generator"
   git remote add origin https://github.com/YOUR_USERNAME/audio-to-video.git
   git push -u origin main
   ```

2. **Deploy on Streamlit Cloud:**
   - Go to [share.streamlit.io](https://share.streamlit.io)
   - Click "New app"
   - Select your repository
   - Set main file path: `app.py`

3. **Configure Secrets:**
   - In your app settings, click "Secrets"
   - Add your API keys:
     ```toml
     OPENAI_API_KEY = "sk-..."
     LTX_API_KEY = "ltxv_..."
     ```

4. **Note:** Streamlit Cloud needs ffmpeg. Add a `packages.txt` file:
   ```
   ffmpeg
   ```

## Required API Keys

| Service | Purpose | Get Key |
|---------|---------|---------|
| OpenAI | Transcription (Whisper) + Scene Generation (GPT-4) | [platform.openai.com](https://platform.openai.com/api-keys) |
| LTX Video | Video clip generation | [ltx.video](https://ltx.video) |

## Usage

1. Upload an audio file (MP3, WAV, M4A, etc.)
2. Select a visual style or enter a custom description
3. Click "Generate Video"
4. Wait for processing (~1-2 min per 10 seconds of audio)
5. Preview and download your video

## Style Presets

- **Cinematic Stock Footage** - Professional, smooth camera movements
- **Nature Documentary** - BBC Earth quality, wildlife focus
- **News/Corporate** - Clean, modern professional look
- **Artistic/Abstract** - Creative, experimental visuals
- **Vintage/Retro** - Warm colors, nostalgic film aesthetic
- **Tech/Futuristic** - Sleek, modern digital effects
- **Custom** - Enter your own style description

## Estimated Processing Times

| Audio Length | Est. Time |
|--------------|-----------|
| 1 minute | 5-10 min |
| 2 minutes | 10-20 min |
| 5 minutes | 25-45 min |

## Troubleshooting

**"Missing API keys" error:**
- Make sure secrets.toml exists with valid keys
- On Streamlit Cloud, check the Secrets settings

**"Could not read audio file":**
- Ensure ffmpeg is installed
- Try a different audio format (MP3 recommended)

**Video generation fails:**
- Check LTX API key is valid
- Verify you have API credits remaining

## API Mode (for Agents)

FORGE also provides a REST API for programmatic access:

### Start the API Server
```bash
pip install fastapi uvicorn python-multipart
uvicorn api:app --host 0.0.0.0 --port 8000
```

### API Endpoints

**POST /generate** - Start a video generation job
```bash
curl -X POST "http://localhost:8000/generate" \
  -F "audio_url=https://example.com/audio.mp3" \
  -F "style=Cinematic" \
  -F "model=ltx-2-fast" \
  -F "resolution=1920x1080"
```

**GET /status/{job_id}** - Check job status
```bash
curl "http://localhost:8000/status/abc123"
```

**GET /download/{job_id}** - Download completed video
```bash
curl "http://localhost:8000/download/abc123" -o video.mp4
```

### Environment Variables
Set API keys via environment:
```bash
export OPENAI_API_KEY="sk-..."
export LTX_API_KEY="ltxv_..."
```

Or place them in `~/.secrets/openai.json` and `~/.secrets/ltx.json`

## License

MIT
