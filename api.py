"""
FORGE API - Programmatic access to FORGE video generation
Built by CB ⚡

Run with: uvicorn api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import tempfile
import json
import time
import subprocess
import os
import base64
import urllib.request
import uuid
from pathlib import Path

app = FastAPI(
    title="FORGE API",
    description="Frame Output & Rendering Generation Engine - Audio to Video API",
    version="1.0.0"
)

# ============================================================================
# Configuration
# ============================================================================

LTX_API_BASE = "https://api.ltx.video/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"

# Get API keys from environment or secrets
def get_api_key(service: str) -> str:
    """Get API key from env var or secrets file"""
    env_var = f"{service.upper()}_API_KEY"
    if os.environ.get(env_var):
        return os.environ[env_var]
    
    # Try secrets file
    secrets_paths = [
        f"/home/ubuntu/.secrets/{service.lower()}.json",
        os.path.expanduser(f"~/.secrets/{service.lower()}.json"),
        f".secrets/{service.lower()}.json"
    ]
    
    for path in secrets_paths:
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
                return data.get("api_key", "")
    
    return ""

# Job storage (in production, use Redis or a database)
JOBS = {}
OUTPUT_DIR = tempfile.mkdtemp(prefix="forge_api_")

# ============================================================================
# Models
# ============================================================================

class AudioToVideoRequest(BaseModel):
    audio_url: Optional[str] = None  # URL to audio file
    audio_base64: Optional[str] = None  # Base64 encoded audio
    style: str = "Cinematic"
    style_notes: Optional[str] = None
    prompt_override: Optional[str] = None  # Skip transcription, use this prompt directly
    model: str = "ltx-2-fast"
    resolution: str = "1920x1080"
    fps: int = 25
    shot_density: str = "balanced"  # sparse, balanced, dense

class JobStatus(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    progress: Optional[int] = None
    message: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None

# ============================================================================
# Helper Functions
# ============================================================================

def transcribe_audio(audio_path: str, openai_key: str) -> str:
    """Transcribe audio using OpenAI Whisper"""
    import urllib.request
    
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex[:16]}"
    
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    
    body = (
        f'--{boundary}\r\n'
        f'Content-Disposition: form-data; name="file"; filename="audio.mp3"\r\n'
        f'Content-Type: audio/mpeg\r\n\r\n'
    ).encode() + audio_data + (
        f'\r\n--{boundary}\r\n'
        f'Content-Disposition: form-data; name="model"\r\n\r\n'
        f'whisper-1\r\n'
        f'--{boundary}--\r\n'
    ).encode()
    
    req = urllib.request.Request(
        f"{OPENAI_API_BASE}/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        }
    )
    
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode())
        return result.get("text", "")

def generate_scene_prompts(transcript: str, style: str, openai_key: str, num_scenes: int = 5) -> List[str]:
    """Use GPT-4 to generate scene descriptions from transcript"""
    
    system_prompt = f"""You are a video director. Given a transcript, create {num_scenes} visual scene descriptions for video clips.
    
Style: {style}

Rules:
- Each scene should be 1-2 sentences
- Be specific about camera angles, lighting, subjects
- Match the content/mood of the transcript
- Return ONLY a JSON array of strings, nothing else

Example output:
["Wide shot of a sunset over mountains, golden hour lighting, drone footage",
 "Close-up of hands working in soil, shallow depth of field, warm tones"]"""

    body = json.dumps({
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Transcript: {transcript}"}
        ],
        "temperature": 0.7
    }).encode()
    
    req = urllib.request.Request(
        f"{OPENAI_API_BASE}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {openai_key}",
            "Content-Type": "application/json"
        }
    )
    
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
        content = result["choices"][0]["message"]["content"]
        # Parse JSON from response
        try:
            return json.loads(content)
        except:
            # Try to extract JSON array from response
            import re
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                return json.loads(match.group())
            return [content]

def generate_video_clip(prompt: str, ltx_key: str, model: str, resolution: str, fps: int, duration: int = 6) -> str:
    """Generate a video clip using LTX API"""
    
    body = json.dumps({
        "prompt": prompt,
        "model": model,
        "resolution": resolution,
        "fps": fps,
        "duration": duration
    }).encode()
    
    req = urllib.request.Request(
        f"{LTX_API_BASE}/text-to-video",
        data=body,
        headers={
            "Authorization": f"Bearer {ltx_key}",
            "Content-Type": "application/json"
        }
    )
    
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode())
        return result.get("video_url", "")

def download_file(url: str, output_path: str):
    """Download a file from URL"""
    urllib.request.urlretrieve(url, output_path)

def concatenate_videos(video_paths: List[str], output_path: str):
    """Concatenate video clips using ffmpeg"""
    # Create file list
    list_path = output_path + ".txt"
    with open(list_path, "w") as f:
        for path in video_paths:
            f.write(f"file '{path}'\n")
    
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    os.remove(list_path)

def merge_audio_video(video_path: str, audio_path: str, output_path: str):
    """Merge audio with video using ffmpeg"""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)

# ============================================================================
# Background Processing
# ============================================================================

def process_audio_to_video(job_id: str, audio_path: str, request: AudioToVideoRequest):
    """Background task to process audio to video"""
    try:
        JOBS[job_id]["status"] = "processing"
        JOBS[job_id]["progress"] = 0
        
        openai_key = get_api_key("openai")
        ltx_key = get_api_key("ltx")
        
        if not openai_key:
            raise Exception("OpenAI API key not configured")
        if not ltx_key:
            raise Exception("LTX API key not configured")
        
        # Step 1: Transcribe (or use override)
        JOBS[job_id]["message"] = "Transcribing audio..."
        JOBS[job_id]["progress"] = 10
        
        if request.prompt_override:
            scenes = [request.prompt_override]
        else:
            transcript = transcribe_audio(audio_path, openai_key)
            
            # Step 2: Generate scene prompts
            JOBS[job_id]["message"] = "Generating scene descriptions..."
            JOBS[job_id]["progress"] = 20
            
            style_desc = request.style
            if request.style_notes:
                style_desc += f", {request.style_notes}"
            
            scenes = generate_scene_prompts(transcript, style_desc, openai_key)
        
        # Step 3: Generate video clips
        JOBS[job_id]["message"] = "Generating video clips..."
        video_clips = []
        
        for i, scene in enumerate(scenes):
            JOBS[job_id]["progress"] = 30 + int((i / len(scenes)) * 50)
            JOBS[job_id]["message"] = f"Generating clip {i+1}/{len(scenes)}..."
            
            video_url = generate_video_clip(
                scene, ltx_key, 
                request.model, request.resolution, request.fps
            )
            
            # Download clip
            clip_path = os.path.join(OUTPUT_DIR, f"{job_id}_clip_{i}.mp4")
            download_file(video_url, clip_path)
            video_clips.append(clip_path)
        
        # Step 4: Concatenate clips
        JOBS[job_id]["message"] = "Assembling video..."
        JOBS[job_id]["progress"] = 85
        
        concat_path = os.path.join(OUTPUT_DIR, f"{job_id}_concat.mp4")
        concatenate_videos(video_clips, concat_path)
        
        # Step 5: Merge with audio
        JOBS[job_id]["message"] = "Adding audio..."
        JOBS[job_id]["progress"] = 95
        
        final_path = os.path.join(OUTPUT_DIR, f"{job_id}_final.mp4")
        merge_audio_video(concat_path, audio_path, final_path)
        
        # Done!
        JOBS[job_id]["status"] = "completed"
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["message"] = "Video ready!"
        JOBS[job_id]["video_path"] = final_path
        
        # Cleanup intermediate files
        for clip in video_clips:
            if os.path.exists(clip):
                os.remove(clip)
        if os.path.exists(concat_path):
            os.remove(concat_path)
        
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)

# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
def root():
    return {
        "name": "FORGE API",
        "version": "1.0.0",
        "description": "Audio to Video Generation API",
        "endpoints": {
            "POST /generate": "Start a new video generation job",
            "GET /status/{job_id}": "Check job status",
            "GET /download/{job_id}": "Download completed video"
        }
    }

@app.post("/generate", response_model=JobStatus)
async def generate_video(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(None),
    audio_url: str = Form(None),
    audio_base64: str = Form(None),
    style: str = Form("Cinematic"),
    style_notes: str = Form(None),
    prompt_override: str = Form(None),
    model: str = Form("ltx-2-fast"),
    resolution: str = Form("1920x1080"),
    fps: int = Form(25)
):
    """
    Start a new audio-to-video generation job.
    
    Provide audio via one of:
    - audio_file: Upload file directly
    - audio_url: URL to audio file
    - audio_base64: Base64 encoded audio
    """
    
    job_id = str(uuid.uuid4())[:8]
    
    # Get audio file
    audio_path = os.path.join(OUTPUT_DIR, f"{job_id}_audio.mp3")
    
    if audio_file:
        with open(audio_path, "wb") as f:
            content = await audio_file.read()
            f.write(content)
    elif audio_url:
        download_file(audio_url, audio_path)
    elif audio_base64:
        with open(audio_path, "wb") as f:
            f.write(base64.b64decode(audio_base64))
    else:
        raise HTTPException(status_code=400, detail="Must provide audio_file, audio_url, or audio_base64")
    
    # Create job
    JOBS[job_id] = {
        "status": "pending",
        "progress": 0,
        "message": "Job queued"
    }
    
    # Create request object
    request = AudioToVideoRequest(
        style=style,
        style_notes=style_notes,
        prompt_override=prompt_override,
        model=model,
        resolution=resolution,
        fps=fps
    )
    
    # Start background processing
    background_tasks.add_task(process_audio_to_video, job_id, audio_path, request)
    
    return JobStatus(
        job_id=job_id,
        status="pending",
        message="Job queued for processing"
    )

@app.get("/status/{job_id}", response_model=JobStatus)
def get_status(job_id: str):
    """Get the status of a video generation job"""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    return JobStatus(
        job_id=job_id,
        status=job.get("status", "unknown"),
        progress=job.get("progress"),
        message=job.get("message"),
        error=job.get("error")
    )

@app.get("/download/{job_id}")
def download_video(job_id: str):
    """Download a completed video"""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = JOBS[job_id]
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail=f"Job not ready. Status: {job.get('status')}")
    
    video_path = job.get("video_path")
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Video file not found")
    
    return FileResponse(
        video_path,
        media_type="video/mp4",
        filename=f"forge_{job_id}.mp4"
    )

@app.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "healthy", "jobs_in_memory": len(JOBS)}

# ============================================================================
# Run with: uvicorn api:app --host 0.0.0.0 --port 8000
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
