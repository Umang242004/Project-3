import os
import json
import subprocess
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from tqdm import tqdm

# ========== CONFIG ==========
DRIVE_FILE_ID = "1Xyqk2ti5S2lKtELz2AWwdzeQI94KCQzf"  # .webm input

# ========== GOOGLE AUTH ==========
creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
credentials = service_account.Credentials.from_service_account_info(creds_json, scopes=[
    'https://www.googleapis.com/auth/drive'])
drive_service = build('drive', 'v3', credentials=credentials)

# ========== DOWNLOAD FROM DRIVE ==========
def download_from_drive(file_id, dest_path):
    print(f"⬇️ Downloading {dest_path} from Google Drive...")
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        response = request.execute()
        f.write(response)
    print(f"✅ Downloaded {dest_path}")

# ========== GET VIDEO DURATION ==========
def get_video_duration(file_path):
    """Get video duration in seconds"""
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(result.stdout.strip())

# Download the .webm file if it doesn't exist
if not os.path.exists("movie.webm"):
    download_from_drive(DRIVE_FILE_ID, "movie.webm")

# ========== CONVERSION WITH PROGRESS ==========
if os.path.exists("movie.webm") and not os.path.exists("movie.mp4"):
    print("🎬 Converting .webm to .mp4...")
    
    # Get video duration for progress calculation
    duration = get_video_duration("movie.webm")
    print(f"Video duration: {duration:.2f} seconds")
    
    cmd = [
        "ffmpeg", "-i", "movie.webm",
        "-c:v", "libx264", "-c:a", "aac",
        "-progress", "pipe:1",
        "movie.mp4"
    ]
    
    # Run conversion with progress tracking
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, universal_newlines=True)
    
    with tqdm(total=duration, desc="Converting", unit="sec", ncols=80) as pbar:
        current_time = 0
        for line in process.stdout:
            if line.startswith('out_time_ms='):
                time_ms = int(line.split('=')[1])
                new_time = time_ms / 1000000  # Convert microseconds to seconds
                pbar.update(new_time - current_time)
                current_time = new_time
    
    process.wait()
    
    if process.returncode == 0:
        print("✅ Conversion complete!")
        print(f"Output: movie.mp4")
    else:
        print("❌ Conversion failed!")
        print(f"Error: {process.stderr.read()}")
else:
    print("❌ movie.webm not found or movie.mp4 already exists")

print("\n🎉 Done! Simple .webm to .mp4 conversion completed.")
