"""
FORGE - Frame Output & Rendering Generation Engine
AI-powered audio-to-video generation tool
Built by CB ⚡
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
import base64
import re

# ============================================================================
# Configuration
# ============================================================================

st.set_page_config(
    page_title="FORGE | Audio to Video",
    page_icon="⚡",
    layout="wide"
)

# LTX Video settings
LTX_API_BASE = "https://api.ltx.video/v1"
LTX_MODELS = {
    "Fast (Recommended)": "ltx-2-fast",
    "Pro (Higher Quality)": "ltx-2-pro"
}
LTX_RESOLUTIONS = {
    "1080p (1920x1080)": "1920x1080",
    "1440p (2560x1440)": "2560x1440",
    "4K (3840x2160)": "3840x2160"
}
LTX_FPS_OPTIONS = [25, 50]
LTX_REQUEST_TIMEOUT = 300

# Valid durations for LTX at 1080p/25fps
VALID_DURATIONS = [6, 8, 10, 12, 14, 16, 18, 20]

# OpenAI settings
WHISPER_MODEL = "whisper-1"
OPENAI_MODEL = "gpt-4o"

# Camera motion presets
CAMERA_MOTIONS = [
    "Auto (AI decides)",
    "Static",
    "Dolly In",
    "Dolly Out",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Jib Up",
    "Jib Down",
    "Crane Shot",
    "Tracking Shot",
    "Handheld",
    "Orbit",
    "Focus Shift"
]

# Style presets with detailed prompts
STYLE_PRESETS = {
    "Cinematic": {
        "description": "cinematic stock footage, professional quality, smooth camera movements, cinematic color grading, shallow depth of field",
        "shot_styles": ["wide establishing", "medium shot", "close-up detail", "tracking shot", "aerial view"]
    },
    "Documentary": {
        "description": "documentary style, BBC Earth quality, observational footage, natural lighting, authentic moments",
        "shot_styles": ["fly-on-wall", "interview framing", "B-roll coverage", "archival aesthetic", "talking head"]
    },
    "News/Corporate": {
        "description": "professional news broadcast style, clean and modern, corporate aesthetic, blue and white tones",
        "shot_styles": ["anchor desk", "split screen", "lower third space", "clean backdrop", "professional lighting"]
    },
    "Artistic/Abstract": {
        "description": "artistic abstract visuals, creative color grading, experimental cinematography, symbolic imagery",
        "shot_styles": ["extreme close-up", "dutch angle", "silhouette", "lens flare", "double exposure"]
    },
    "Vintage/Retro": {
        "description": "vintage film aesthetic, warm colors, nostalgic mood, film grain, 70s/80s style",
        "shot_styles": ["soft focus", "lens distortion", "vignette", "overexposed", "sepia tones"]
    },
    "Tech/Futuristic": {
        "description": "futuristic technology aesthetic, sleek and modern, digital effects, neon accents, cyberpunk",
        "shot_styles": ["holographic", "data visualization", "circuit patterns", "glitch effects", "wireframe"]
    },
    "Custom": {
        "description": "",
        "shot_styles": []
    }
}

# ============================================================================
# API Functions
# ============================================================================

def get_api_keys():
    """Get API keys from Streamlit secrets or environment."""
    keys = {}
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

def compress_audio_for_whisper(audio_path, max_size_mb=24):
    """Compress audio file if it exceeds the size limit for Whisper API."""
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    
    if file_size_mb <= max_size_mb:
        return audio_path  # No compression needed
    
    # Create compressed version
    compressed_path = Path(audio_path).parent / f"compressed_{Path(audio_path).stem}.mp3"
    
    # Calculate target bitrate based on file duration and max size
    # Get duration first
    duration_cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    try:
        result = subprocess.run(duration_cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
    except:
        duration = 1200  # Assume 20 min if we can't detect
    
    # Target ~20MB to leave headroom (in bits)
    target_size_bits = 20 * 1024 * 1024 * 8
    target_bitrate = int(target_size_bits / duration / 1000)  # kbps
    target_bitrate = max(32, min(128, target_bitrate))  # Clamp between 32-128 kbps
    
    compress_cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-b:a", f"{target_bitrate}k",
        "-ac", "1",  # Mono
        "-ar", "16000",  # 16kHz sample rate (fine for speech)
        str(compressed_path)
    ]
    
    try:
        subprocess.run(compress_cmd, check=True, capture_output=True)
        return compressed_path
    except subprocess.CalledProcessError:
        # If compression fails, return original and hope for the best
        return audio_path


def transcribe_audio(audio_path, api_key, progress_callback=None):
    """Transcribe audio using OpenAI Whisper API with timestamps."""
    if progress_callback:
        progress_callback("Checking audio file size...")
    
    # Auto-compress if file is too large
    original_path = audio_path
    audio_path = compress_audio_for_whisper(audio_path)
    
    if audio_path != original_path:
        if progress_callback:
            progress_callback("Audio compressed for upload. Transcribing...")
    elif progress_callback:
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
    body.append(b"verbose_json")  # Get timestamps
    body.append(f"--{boundary}--".encode())
    body.append(b"")
    
    body_bytes = b"\r\n".join(body)
    
    url = "https://api.openai.com/v1/audio/transcriptions"
    req = urllib.request.Request(url, data=body_bytes, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))

def generate_scene_prompts(transcript_data, duration, style, settings, api_key, custom_shots=None, shot_format=None):
    """Generate scene prompts using OpenAI GPT-4."""
    
    # Extract text and segments from transcript
    if isinstance(transcript_data, dict):
        transcript_text = transcript_data.get("text", "")
        segments = transcript_data.get("segments", [])
    else:
        transcript_text = transcript_data
        segments = []
    
    # Calculate number of clips based on density setting
    density_multiplier = {
        "Sparse (longer shots)": 0.5,
        "Balanced": 1.0,
        "Dense (more shots)": 1.5,
        "Very Dense (rapid cuts)": 2.0
    }
    base_clips = max(4, min(30, int(duration / 12)))
    num_clips = int(base_clips * density_multiplier.get(settings.get('density', 'Balanced'), 1.0))
    num_clips = max(4, min(40, num_clips))
    
    # Build custom shots instruction based on format
    custom_shots_instruction = ""
    if custom_shots and custom_shots.strip():
        format_instructions = {
            "📝 Simple List": """The user provided a SIMPLE LIST of desired shots. 
Distribute these shots intelligently throughout the video, matching them to appropriate moments in the audio.
Add transitional shots as needed to fill gaps and maintain flow.""",
            
            "⏱️ Timestamps": """The user provided TIMESTAMPED shots.
Place these shots at their specified times. Fill any gaps with appropriate transitional visuals.""",
            
            "💬 Script-Matched": """The user provided SCRIPT-MATCHED shots (visual cues tied to specific dialogue/topics).
When the transcript discusses those topics, use the specified visuals. Generate appropriate B-roll for unspecified sections.""",
            
            "🔢 Numbered Sequence": """The user provided a NUMBERED SEQUENCE of shots in order.
Use these shots in sequence, distributing timing evenly or as makes sense for the content."""
        }
        
        format_hint = format_instructions.get(shot_format, format_instructions["📝 Simple List"])
        
        custom_shots_instruction = f"""
IMPORTANT - USER-SPECIFIED VISUALS:
{format_hint}

User's shot list:
{custom_shots}

Incorporate ALL user shots. Enhance with additional detail (camera movement, lighting, mood) but preserve their creative intent."""

    # Build consistency instruction
    consistency = settings.get('consistency', 50)
    if consistency < 30:
        consistency_instruction = "Allow significant visual variation between scenes. Each scene can look distinctly different."
    elif consistency < 70:
        consistency_instruction = "Maintain moderate visual consistency. Characters should look similar but environments can vary."
    else:
        consistency_instruction = "Maintain HIGH visual consistency. Characters must look identical across all scenes. Environments should share similar lighting and color palette."

    # Camera motion preference
    camera_motion = settings.get('camera_motion', 'Auto (AI decides)')
    camera_instruction = ""
    if camera_motion != "Auto (AI decides)":
        camera_instruction = f"Preferred camera motion: {camera_motion}. Incorporate this style where appropriate."

    prompt = f"""Analyze this audio transcript and create {num_clips} video scene prompts for visual accompaniment.

TRANSCRIPT:
{transcript_text}

{custom_shots_instruction}

REQUIREMENTS:
1. Create exactly {num_clips} scenes that flow with the audio content
2. Each scene duration must be one of: {VALID_DURATIONS} seconds
3. Total duration must be approximately {int(duration)} seconds (±5 seconds OK)
4. Visual style: {style}
5. {consistency_instruction}
6. {camera_instruction}
7. Prompts should be DETAILED, cinematic descriptions for AI video generation
8. Include: camera movements, lighting, mood, composition, specific visual details
9. Match scenes to the CONTENT being discussed at that timestamp

OUTPUT FORMAT (JSON array only, no other text):
[
    {{"prompt": "Detailed scene description with camera movement, lighting, composition...", "duration": 12, "timestamp": "0:00"}},
    {{"prompt": "Next scene description...", "duration": 10, "timestamp": "0:12"}},
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
        "max_tokens": 8192,
        "temperature": 0.7
    }
    
    req = urllib.request.Request(url, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.data = json.dumps(data).encode()
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
        content = result["choices"][0]["message"]["content"]
    
    # Parse JSON
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    
    return json.loads(content.strip())

def generate_video_clip(prompt, duration, output_path, api_key, settings, image_uri=None):
    """Generate a single video clip using LTX API."""
    if duration not in VALID_DURATIONS:
        duration = min(VALID_DURATIONS, key=lambda x: abs(x - duration))
    
    model = LTX_MODELS.get(settings.get('model', 'Fast (Recommended)'), 'ltx-2-fast')
    resolution = LTX_RESOLUTIONS.get(settings.get('resolution', '1080p (1920x1080)'), '1920x1080')
    fps = settings.get('fps', 25)
    
    # Limit duration for pro model and higher resolutions
    if model == "ltx-2-pro" or resolution != "1920x1080" or fps == 50:
        duration = min(duration, 10)
    
    # Use image-to-video if we have a reference image
    if image_uri:
        url = f"{LTX_API_BASE}/image-to-video"
        data = {
            "image_uri": image_uri,
            "prompt": prompt,
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "fps": fps
        }
    else:
        url = f"{LTX_API_BASE}/text-to-video"
        data = {
            "prompt": prompt,
            "model": model,
            "duration": duration,
            "resolution": resolution,
            "fps": fps,
            "generate_audio": False
        }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
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

def image_to_data_uri(image_bytes, content_type="image/jpeg"):
    """Convert image bytes to data URI for LTX API."""
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    return f"data:{content_type};base64,{b64}"

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
    # Custom CSS for IPAI branding
    st.markdown("""
    <style>
        .stApp {
            background-color: #2d2d2d;
        }
        .main .block-container {
            padding-top: 2rem;
        }
        h1 {
            background: linear-gradient(180deg, #c5c5c5 0%, #d4af37 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stButton>button {
            background: linear-gradient(135deg, #d4af37 0%, #e8c547 100%);
            color: #2d2d2d;
            border: none;
            font-weight: 600;
        }
        .stButton>button:hover {
            background: linear-gradient(135deg, #e8c547 0%, #f5d742 100%);
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Header with logo
    col1, col2, col3 = st.columns([1, 4, 1])
    with col1:
        try:
            st.image("ipai-logo.jpg", width=60)
        except:
            pass
    with col2:
        st.title("⚡ FORGE")
        st.markdown("*Frame Output & Rendering Generation Engine*")
    with col3:
        st.markdown("")
        st.caption("Built by CB")
    
    st.markdown("---")
    
    # Check for API keys
    keys = get_api_keys()
    
    if not keys.get('openai') or not keys.get('ltx'):
        st.error("⚠️ Missing API keys. Configure OPENAI_API_KEY and LTX_API_KEY in secrets.")
        with st.expander("How to configure API keys"):
            st.markdown("""
            **For Streamlit Cloud:**
            1. Go to your app settings → Secrets
            2. Add:
            ```toml
            OPENAI_API_KEY = "sk-..."
            LTX_API_KEY = "ltxv_..."
            ```
            """)
        return
    
    # ========================================================================
    # Sidebar - Settings
    # ========================================================================
    with st.sidebar:
        st.header("⚙️ Generation Settings")
        
        # Visual Style
        st.subheader("🎨 Visual Style")
        style_preset = st.selectbox(
            "Style Preset",
            options=list(STYLE_PRESETS.keys()),
            index=0
        )
        
        if style_preset == "Custom":
            style = st.text_area(
                "Custom Style Description",
                placeholder="e.g., underwater ocean documentary, bioluminescent creatures, deep blue tones"
            )
        else:
            style = STYLE_PRESETS[style_preset]["description"]
            st.caption(f"*{style}*")
        
        st.divider()
        
        # Quality Settings
        st.subheader("📺 Quality")
        
        model_choice = st.selectbox(
            "Model",
            options=list(LTX_MODELS.keys()),
            index=0,
            help="Pro is higher quality but slower and limited to 10s clips"
        )
        
        resolution_choice = st.selectbox(
            "Resolution",
            options=list(LTX_RESOLUTIONS.keys()),
            index=0,
            help="Higher resolutions cost more and limit clip duration"
        )
        
        fps_choice = st.selectbox(
            "Frame Rate",
            options=LTX_FPS_OPTIONS,
            index=0,
            help="50fps for smoother motion (limits duration)"
        )
        
        st.divider()
        
        # Shot Control
        st.subheader("🎬 Shot Control")
        
        shot_density = st.select_slider(
            "Shot Density",
            options=["Sparse (longer shots)", "Balanced", "Dense (more shots)", "Very Dense (rapid cuts)"],
            value="Balanced",
            help="How many individual shots to generate"
        )
        
        consistency = st.slider(
            "Visual Consistency",
            min_value=0,
            max_value=100,
            value=50,
            help="Low = more variation, High = characters/settings stay consistent"
        )
        
        camera_motion = st.selectbox(
            "Camera Motion Preference",
            options=CAMERA_MOTIONS,
            index=0,
            help="Suggest a camera movement style"
        )
        
        st.divider()
        
        st.markdown("### ℹ️ About FORGE")
        st.markdown("""
        1. 📝 Transcribes audio (Whisper)
        2. 🎬 Generates scene prompts (GPT-4)
        3. 🎥 Creates video clips (LTX)
        4. 🔗 Assembles final video
        
        **⏱️ ~1-2 min per 10s of video**
        """)
    
    # ========================================================================
    # Main Content Area
    # ========================================================================
    
    # Two-column layout for inputs
    input_col1, input_col2 = st.columns(2)
    
    with input_col1:
        st.subheader("🎵 Audio Input")
        uploaded_file = st.file_uploader(
            "Upload Audio File",
            type=["mp3", "wav", "m4a", "ogg", "flac"],
            help="Supported: MP3, WAV, M4A, OGG, FLAC (max 30 min)"
        )
        
        if uploaded_file:
            st.audio(uploaded_file)
    
    with input_col2:
        st.subheader("🎨 Visual Style Notes (Optional)")
        style_notes = st.text_area(
            "Additional Style Guidance",
            placeholder="e.g., 'moody noir lighting, high contrast, desaturated blues'\n'warm golden hour tones, lens flares, soft focus'\n'gritty documentary feel, handheld camera shake'",
            height=100,
            help="Describe the visual tone/mood. Applies to ALL clips on top of your style preset."
        )
        
        st.markdown("---")
        
        st.subheader("🎬 Images to Animate (Optional)")
        st.caption("⚠️ *These images will be animated directly — not used as style reference.*")
        uploaded_images = st.file_uploader(
            "Upload Images to Animate",
            type=["jpg", "jpeg", "png", "webp"],
            accept_multiple_files=True,
            help="Each uploaded image will be animated directly. Use for animating specific stills, not for style matching."
        )
        
        image_uris = []
        image_mode = "cycle"  # Default
        
        if uploaded_images and len(uploaded_images) > 0:
            # Show image grid
            num_images = len(uploaded_images)
            cols_per_row = min(3, num_images)
            img_cols = st.columns(cols_per_row)
            
            for idx, img in enumerate(uploaded_images):
                with img_cols[idx % cols_per_row]:
                    st.image(img, width=120, caption=f"#{idx + 1}")
                    content_type = f"image/{img.type.split('/')[-1]}" if '/' in str(img.type) else "image/jpeg"
                    image_uris.append(image_to_data_uri(img.getvalue(), content_type))
            
            # Image assignment mode (only show if multiple images)
            if num_images > 1:
                image_mode = st.radio(
                    "Image Assignment",
                    options=["cycle", "random", "first_only"],
                    format_func=lambda x: {
                        "cycle": "🔄 Cycle through images",
                        "random": "🎲 Random per scene",
                        "first_only": "1️⃣ Use first image only"
                    }.get(x, x),
                    horizontal=True,
                    help="How to assign reference images to scenes"
                )
        
        # For backwards compatibility, keep single image_uri for simple case
        image_uri = image_uris[0] if len(image_uris) == 1 else None
    
    st.markdown("---")
    
    # Custom Shot Prompts Section
    st.subheader("🎯 Custom Shot Prompts (Optional)")
    st.markdown("*Tell FORGE what visuals you want — use any format that works for you.*")
    
    # Format selector
    shot_format = st.radio(
        "Input Format",
        options=["📝 Simple List", "⏱️ Timestamps", "💬 Script-Matched", "🔢 Numbered Sequence"],
        horizontal=True,
        help="Choose whatever format feels natural"
    )
    
    # Dynamic placeholder based on format
    placeholders = {
        "📝 Simple List": """Just list the shots you want (FORGE will distribute them):

- Wide establishing shot of city skyline at dawn
- Close-up of hands typing on laptop  
- Drone shot revealing coastal landscape
- Medium shot of two people in conversation
- Moody silhouette against window

FORGE will intelligently place these throughout your video.""",
        
        "⏱️ Timestamps": """Specify exact timing:

0:00-0:15 - Wide establishing shot of city skyline at dawn, golden hour lighting
0:15-0:30 - Medium shot of protagonist walking through busy street
0:45-1:00 - Close-up of hands typing on laptop, soft office lighting
1:30-1:45 - Drone shot pulling back from building rooftop""",
        
        "💬 Script-Matched": """Match visuals to specific dialogue/content:

When talking about "the early days" -> Vintage sepia-toned footage of old factory
When mentioning "breakthrough moment" -> Dramatic close-up, lens flare, triumphant mood
During the statistics section -> Clean data visualization, charts animating
For the conclusion -> Wide shot of sunset over city, hopeful atmosphere""",
        
        "🔢 Numbered Sequence": """Shots in order (FORGE handles timing):

1. Opening: Aerial shot of mountain landscape at sunrise
2. Medium shot of subject walking through forest path
3. Close-up detail of hands touching tree bark
4. Wide shot of lake reflection, peaceful mood
5. Final: Pull back to reveal full panorama"""
    }
    
    custom_shots = st.text_area(
        "Your Visual Prompts",
        placeholder=placeholders.get(shot_format, placeholders["📝 Simple List"]),
        height=180,
        help="Describe the visuals you want. Be as detailed or simple as you like."
    )
    
    # Store the format choice for the prompt
    shot_input_format = shot_format
    
    # Image Animation Direction (if images uploaded)
    image_direction = ""
    if uploaded_images and len(uploaded_images) > 0:
        image_direction = st.text_area(
            "🎬 Image Animation Direction",
            placeholder="e.g., 'Slow gentle zoom in, soft lighting shifts'\n'Camera slowly pans right, particles floating'\n'Subtle breathing motion, dreamy atmosphere'",
            help="How should your reference images be animated? This applies to all clips using images."
        )
    
    st.markdown("---")
    
    # Generation Button
    if uploaded_file:
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp_audio:
            tmp_audio.write(uploaded_file.getvalue())
            audio_path = Path(tmp_audio.name)
        
        try:
            duration = get_audio_duration(audio_path)
            
            # Info row
            info_col1, info_col2, info_col3 = st.columns(3)
            with info_col1:
                st.metric("Duration", f"{duration:.1f}s ({duration/60:.1f} min)")
            with info_col2:
                est_clips = max(4, min(30, int(duration / 12)))
                st.metric("Est. Clips", f"~{est_clips}")
            with info_col3:
                est_time = est_clips * 1.5
                st.metric("Est. Time", f"~{est_time:.0f} min")
            
        except Exception as e:
            st.error(f"Could not read audio file: {e}")
            return
        
        # Collect settings
        settings = {
            'model': model_choice,
            'resolution': resolution_choice,
            'fps': fps_choice,
            'density': shot_density,
            'consistency': consistency,
            'camera_motion': camera_motion
        }
        
        # Two buttons: AI's take vs User's take
        btn_col1, btn_col2 = st.columns(2)
        
        with btn_col1:
            generate_auto = st.button(
                "🤖 Generate (AI's Take)",
                type="primary",
                use_container_width=True,
                help="Let FORGE decide the visuals based on audio content"
            )
        
        with btn_col2:
            generate_custom = st.button(
                "🎯 Generate (My Prompts)",
                type="secondary",
                use_container_width=True,
                disabled=not custom_shots.strip(),
                help="Use your custom timestamped prompts"
            )
        
        should_generate = generate_auto or generate_custom
        use_custom = generate_custom and custom_shots.strip()
        
        if should_generate:
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
                    
                    transcript_data = transcribe_audio(audio_path, keys['openai'])
                    transcript_text = transcript_data.get("text", "") if isinstance(transcript_data, dict) else transcript_data
                    
                    with st.expander("📄 Transcript"):
                        st.text(transcript_text)
                    
                    # Step 2: Generate prompts
                    status_text.text("🎬 Step 2/4: Generating scene descriptions...")
                    progress_bar.progress(20)
                    
                    prompts = generate_scene_prompts(
                        transcript_data,
                        duration,
                        style,
                        settings,
                        keys['openai'],
                        custom_shots=custom_shots if use_custom else None,
                        shot_format=shot_input_format if use_custom else None
                    )
                    
                    with st.expander(f"🎬 Scene Prompts ({len(prompts)} scenes)"):
                        for i, p in enumerate(prompts):
                            ts = p.get('timestamp', f"Scene {i+1}")
                            st.markdown(f"**{ts}** ({p['duration']}s)")
                            st.caption(p['prompt'])
                    
                    # Step 3: Generate video clips
                    status_text.text("🎥 Step 3/4: Generating video clips...")
                    
                    clip_paths = []
                    num_clips = len(prompts)
                    
                    import random as _random
                    
                    for i, prompt_data in enumerate(prompts):
                        clip_progress = 20 + (60 * (i / num_clips))
                        progress_bar.progress(int(clip_progress))
                        status_text.text(f"🎥 Step 3/4: Generating clip {i+1}/{num_clips}...")
                        
                        clip_path = tmp_path / f"clip_{i:03d}.mp4"
                        
                        # Determine which image to use for this clip
                        current_image_uri = None
                        if image_uris:
                            if image_mode == "cycle":
                                current_image_uri = image_uris[i % len(image_uris)]
                            elif image_mode == "random":
                                current_image_uri = _random.choice(image_uris)
                            elif image_mode == "first_only":
                                current_image_uri = image_uris[0]
                            else:
                                current_image_uri = image_uris[0] if image_uris else None
                        
                        # Combine scene prompt with style notes and/or image direction
                        full_prompt = prompt_data["prompt"]
                        
                        # Apply style notes (always, if provided)
                        if style_notes and style_notes.strip():
                            full_prompt = f"{style_notes.strip()}. {full_prompt}"
                        
                        # Apply image animation direction (only if using images)
                        if current_image_uri and image_direction:
                            full_prompt = f"{image_direction}. {full_prompt}"
                        
                        generate_video_clip(
                            full_prompt,
                            prompt_data["duration"],
                            clip_path,
                            keys['ltx'],
                            settings,
                            image_uri=current_image_uri
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
                    
                    st.success("🎉 Video forged successfully!")
                    
                    # Video preview
                    st.video(video_bytes)
                    
                    # Download button
                    output_filename = f"{Path(uploaded_file.name).stem}_forged.mp4"
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
    
    else:
        st.info("👆 Upload an audio file to get started")

if __name__ == "__main__":
    main()
