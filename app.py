"""
Audio-to-Video Generator
Streamlit web app for generating videos from audio files.
"""

import streamlit as st
import tempfile
import json
import time
import subprocess
from pathlib import Path
import urllib.request
import urllib.error
import os

# ============================================================================
# Configuration
# ============================================================================

st.set_page_config(
    page_title="Audio to Video Generator",
    page_icon="🎬",
    layout="centered"
)

# LTX Video settings
LTX_API_BASE = "https://api.ltx.video/v1"
LTX_MODEL = "ltx-2-fast"
LTX_RESOLUTION = "1920x1080"
LTX_FPS = 25
LTX_REQUEST_TIMEOUT = 300

# Valid durations for LTX at 1080p/25fps
VALID_DURATIONS = [6, 8, 10, 12, 14, 16, 18, 20]

# OpenAI settings
WHISPER_MODEL = "whisper-1"
OPENAI_MODEL = "gpt-4o"

# Style presets
STYLE_PRESETS = {
    "Cinematic Stock Footage": "cinematic stock footage, professional quality, smooth camera movements",
    "Nature Documentary": "nature documentary style, BBC Earth quality, wildlife and landscapes",
    "News/Corporate": "professional news broadcast style, clean and modern, corporate aesthetic",
    "Artistic/Abstract": "artistic abstract visuals, creative color grading, experimental cinematography",
    "Vintage/Retro": "vintage film aesthetic, warm colors, nostalgic mood, film grain",
    "Tech/Futuristic": "futuristic technology aesthetic, sleek and modern, digital effects",
    "Custom": ""
}

# ============================================================================
# API Functions
# ============================================================================

def get_api_keys():
    """Get API keys from Streamlit secrets or environment."""
    keys = {}
    
    # Try Streamlit secrets first, then environment variables
    try:
        keys['openai'] = st.secrets.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        keys['ltx'] = st.secrets.get("LTX_API_KEY") or os.environ.get("LTX_API_KEY")
    except Exception:
        keys['openai'] = os.environ.get("OPENAI_API_KEY")
        keys['ltx'] = os.environ.get("LTX_API_KEY")
    
    return keys

def get_audio_duration(audio_path):
    """Get duration of audio file in seconds."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def transcribe_audio(audio_path, api_key, progress_callback=None):
    """Transcribe audio using OpenAI Whisper API."""
    if progress_callback:
        progress_callback("Transcribing audio...")
    
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    
    filename = Path(audio_path).name
    
    body = []
    body.append(f"--{boundary}".encode())
    body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode())
    body.append(b"Content-Type: audio/mpeg")
    body.append(b"")
    body.append(audio_data)
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="model"')
    body.append(b"")
    body.append(WHISPER_MODEL.encode())
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="response_format"')
    body.append(b"")
    body.append(b"text")
    body.append(f"--{boundary}--".encode())
    body.append(b"")
    
    body_bytes = b"\r\n".join(body)
    
    url = "https://api.openai.com/v1/audio/transcriptions"
    req = urllib.request.Request(url, data=body_bytes, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8")

def generate_scene_prompts(transcript, duration, style, api_key, progress_callback=None):
    """Generate scene prompts using OpenAI GPT-4."""
    if progress_callback:
        progress_callback("Generating scene descriptions...")
    
    num_clips = max(4, min(20, int(duration / 12)))
    
    prompt = f"""Analyze this audio transcript and create {num_clips} video scene prompts for a visual accompaniment.

TRANSCRIPT:
{transcript}

REQUIREMENTS:
1. Create exactly {num_clips} scenes that flow with the content
2. Each scene duration must be one of: {VALID_DURATIONS} seconds
3. Total duration must be approximately {int(duration)} seconds (±5 seconds is OK)
4. Visual style: {style}
5. Prompts should be detailed, cinematic descriptions for AI video generation
6. Include camera movements, lighting, mood, and specific visual details
7. Match scenes to the content being discussed at that point in the audio

OUTPUT FORMAT (JSON array only, no other text):
[
    {{"prompt": "Detailed scene description...", "duration": 12}},
    {{"prompt": "Next scene description...", "duration": 10}},
    ...
]"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096
    }
    
    req = urllib.request.Request(url, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.data = json.dumps(data).encode()
    
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode())
        content = result["choices"][0]["message"]["content"]
    
    # Parse JSON
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    
    return json.loads(content.strip())

def generate_video_clip(prompt, duration, output_path, api_key):
    """Generate a single video clip using LTX API."""
    if duration not in VALID_DURATIONS:
        duration = min(VALID_DURATIONS, key=lambda x: abs(x - duration))
    
    url = f"{LTX_API_BASE}/text-to-video"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "prompt": prompt,
        "model": LTX_MODEL,
        "duration": duration,
        "resolution": LTX_RESOLUTION,
        "fps": LTX_FPS,
        "generate_audio": False
    }
    
    req = urllib.request.Request(url, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.data = json.dumps(data).encode()
    
    with urllib.request.urlopen(req, timeout=LTX_REQUEST_TIMEOUT) as resp:
        with open(output_path, 'wb') as f:
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                f.write(chunk)

def concatenate_videos(video_paths, output_path):
    """Concatenate videos using ffmpeg."""
    concat_file = output_path.parent / "concat_list.txt"
    with open(concat_file, "w") as f:
        for path in video_paths:
            f.write(f"file '{path.absolute()}'\n")
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    concat_file.unlink()

def merge_audio(video_path, audio_path, output_path):
    """Merge video with audio track."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        str(output_path)
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)

# ============================================================================
# Main App
# ============================================================================

def main():
    st.title("🎬 Audio to Video Generator")
    st.markdown("Transform your audio into AI-generated video content")
    
    # Check for API keys
    keys = get_api_keys()
    
    if not keys.get('openai') or not keys.get('ltx'):
        st.error("⚠️ Missing API keys. Please configure OPENAI_API_KEY and LTX_API_KEY in Streamlit secrets or environment variables.")
        
        with st.expander("How to configure API keys"):
            st.markdown("""
            **For Streamlit Cloud:**
            1. Go to your app settings
            2. Click "Secrets"
            3. Add:
            ```toml
            OPENAI_API_KEY = "sk-..."
            LTX_API_KEY = "ltxv_..."
            ```
            
            **For local development:**
            Create `.streamlit/secrets.toml` with the same content.
            """)
        return
    
    # Sidebar settings
    with st.sidebar:
        st.header("⚙️ Settings")
        
        style_preset = st.selectbox(
            "Visual Style",
            options=list(STYLE_PRESETS.keys()),
            index=0
        )
        
        if style_preset == "Custom":
            custom_style = st.text_area(
                "Custom Style Description",
                placeholder="e.g., underwater ocean documentary, blue tones, marine life"
            )
            style = custom_style
        else:
            style = STYLE_PRESETS[style_preset]
            st.caption(f"*{style}*")
        
        st.divider()
        
        st.markdown("### About")
        st.markdown("""
        This tool:
        1. 📝 Transcribes your audio
        2. 🎬 Generates scene descriptions
        3. 🎥 Creates video clips with AI
        4. 🔗 Stitches everything together
        
        Processing time: ~1 min per 10s of video
        """)
    
    # Main content
    uploaded_file = st.file_uploader(
        "Upload Audio File",
        type=["mp3", "wav", "m4a", "ogg", "flac"],
        help="Supported formats: MP3, WAV, M4A, OGG, FLAC"
    )
    
    if uploaded_file:
        st.audio(uploaded_file)
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_audio:
            tmp_audio.write(uploaded_file.getvalue())
            audio_path = Path(tmp_audio.name)
        
        try:
            duration = get_audio_duration(audio_path)
            st.info(f"📊 Duration: {duration:.1f} seconds ({duration/60:.1f} minutes)")
            
            estimated_time = max(5, int(duration / 12)) * 1.5  # ~1.5 min per clip
            st.caption(f"⏱️ Estimated processing time: {estimated_time:.0f}-{estimated_time*1.5:.0f} minutes")
            
        except Exception as e:
            st.error(f"Could not read audio file: {e}")
            return
        
        if st.button("🚀 Generate Video", type="primary", use_container_width=True):
            
            if not style:
                st.error("Please select or enter a visual style")
                return
            
            # Create temp directory for processing
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                try:
                    # Step 1: Transcribe
                    status_text.text("📝 Step 1/4: Transcribing audio...")
                    progress_bar.progress(10)
                    
                    transcript = transcribe_audio(audio_path, keys['openai'])
                    
                    with st.expander("📄 Transcript"):
                        st.text(transcript)
                    
                    # Step 2: Generate prompts
                    status_text.text("🎬 Step 2/4: Generating scene descriptions...")
                    progress_bar.progress(20)
                    
                    prompts = generate_scene_prompts(transcript, duration, style, keys['openai'])
                    
                    with st.expander(f"🎬 Scene Prompts ({len(prompts)} scenes)"):
                        for i, p in enumerate(prompts):
                            st.markdown(f"**Scene {i+1}** ({p['duration']}s)")
                            st.caption(p['prompt'])
                    
                    # Step 3: Generate video clips
                    status_text.text("🎥 Step 3/4: Generating video clips...")
                    
                    clip_paths = []
                    num_clips = len(prompts)
                    
                    for i, prompt_data in enumerate(prompts):
                        clip_progress = 20 + (60 * (i / num_clips))
                        progress_bar.progress(int(clip_progress))
                        status_text.text(f"🎥 Step 3/4: Generating clip {i+1}/{num_clips}...")
                        
                        clip_path = tmp_path / f"clip_{i:03d}.mp4"
                        generate_video_clip(
                            prompt_data["prompt"],
                            prompt_data["duration"],
                            clip_path,
                            keys['ltx']
                        )
                        clip_paths.append(clip_path)
                    
                    # Step 4: Concatenate and merge
                    status_text.text("🔗 Step 4/4: Assembling final video...")
                    progress_bar.progress(85)
                    
                    concat_path = tmp_path / "concatenated.mp4"
                    concatenate_videos(clip_paths, concat_path)
                    
                    output_path = tmp_path / "final_video.mp4"
                    merge_audio(concat_path, audio_path, output_path)
                    
                    progress_bar.progress(100)
                    status_text.text("✅ Complete!")
                    
                    # Read final video for download
                    with open(output_path, "rb") as f:
                        video_bytes = f.read()
                    
                    st.success("🎉 Video generated successfully!")
                    
                    # Video preview
                    st.video(video_bytes)
                    
                    # Download button
                    output_filename = f"{Path(uploaded_file.name).stem}_video.mp4"
                    st.download_button(
                        label="⬇️ Download Video",
                        data=video_bytes,
                        file_name=output_filename,
                        mime="video/mp4",
                        use_container_width=True
                    )
                    
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)
        
        # Cleanup temp audio file
        try:
            audio_path.unlink()
        except:
            pass

if __name__ == "__main__":
    main()
