```python
import os
import json
import subprocess
import mimetypes
import gspread
import time
import io # Added for MediaIoBaseDownload

# Import necessary modules for OAuth2
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ========== CONFIGURATION ==========
# Google Drive IDs
DRIVE_FILE_ID = "1Xyqk2ti5S2lKtELz2AWwdzeQI94KCQzf" # ID of your movie.webm file in Google Drive
DRIVE_FOLDER_ID = "1zgLj5Wg42TFIsi4-60J2w757gvaojcQO" # ID of the folder where processed clips will be uploaded

# Video Processing Settings
INPUT_VIDEO = "movie.mp4" # Will be converted from movie.webm
LOGO_FILE = "logo.png" # Optional logo file (ensure this file is in your repo if used)
OUTPUT_DIR = "output_parts" # Directory to store temporary video parts
CLIP_LENGTH = 40 # seconds per clip
TOP_TEXT = "Don no.1"
BOTTOM_TEXT_PREFIX = "PART-"
FONT_FILE = "arial.ttf" # Ensure this font is available on the GitHub Actions runner or provide it
FONT_SIZE = 108
TEXT_COLOR = "black"
CANVAS_W = 1080 # Output video width (e.g., for Instagram Reels)
CANVAS_H = 1920 # Output video height

# Text Positioning (adjust as needed for your font and canvas size)
TOP_MARGIN = 550
BOTTOM_MARGIN = 550

# Google Sheets Settings
SHEET_NAME = "Project3-S3" # Name of your Google Sheet

# OAuth2 Scopes (permissions required for Drive and Sheets)
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

# ========== GOOGLE AUTHENTICATION (OAuth2 via Refresh Token for CI/CD) ==========
# Retrieve credentials from GitHub Actions environment variables
CLIENT_ID = os.environ.get('GDRIVE_CLIENT_ID')
CLIENT_SECRET = os.environ.get('GDRIVE_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('GDRIVE_REFRESH_TOKEN')

if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    raise ValueError("Missing Google Drive OAuth secrets (GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET, GDRIVE_REFRESH_TOKEN) in environment variables. Please check GitHub Actions secrets.")

# Construct credentials object using the refresh token
# --- START OF CHANGE ---
creds = Credentials(
    token=None, # Access token will be retrieved using refresh token
    refresh_token=REFRESH_TOKEN,
    token_uri='https://oauth2.googleapis.com/token',
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    scopes=SCOPES
)
# --- END OF CHANGE ---

# Refresh credentials if expired (this will use the refresh token)
try:
    if not creds.valid:
        creds.refresh(Request())
except Exception as e:
    raise Exception(f"Failed to refresh Google credentials. Ensure your REFRESH_TOKEN is valid and your OAuth client ID is correctly configured for 'Desktop app'. Error: {e}")

# Initialize Google Drive service
drive_service = build('drive', 'v3', credentials=creds)

# Initialize gspread for Google Sheets (using the same OAuth2 credentials)
sheet_client = gspread.authorize(creds)
try:
    sheet = sheet_client.open(SHEET_NAME).sheet1
except Exception as e:
    raise Exception(f"Failed to open Google Sheet '{SHEET_NAME}'. Ensure the sheet exists and your authorized Google account has access. Error: {e}")

print("✅ Google Drive and Sheets authenticated successfully.")

# ========== HELPER FUNCTIONS ==========

def download_from_drive(file_id, dest_path):
    """Downloads a file from Google Drive."""
    print(f"⬇️ Downloading file (ID: {file_id}) from Google Drive to {dest_path}...")
    request = drive_service.files().get_media(fileId=file_id)
    fh = io.FileIO(dest_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        # print(f"Download {int(status.progress() * 100)}%.") # Uncomment for verbose download progress
    print(f"✅ Download complete: {dest_path}")

def safe_upload(file_metadata, media, retries=5):
    """Uploads a file to Google Drive with retries."""
    for attempt in range(retries):
        try:
            print(f"⬆️ Uploading {file_metadata['name']} (Attempt {attempt+1}/{retries})...")
            # For user-owned My Drive folders, supportsAllDrives=True is not needed.
            # If you later switch to a Shared Drive, you would add supportsAllDrives=True here.
            request = drive_service.files().create(body=file_metadata, media_body=media, fields='id')
            response = None
            while response is None:
                status, response = request.next_chunk()
                # print(f"Upload {int(status.progress() * 100)}%.") # Uncomment for verbose upload progress
            print(f"✅ Upload successful. File ID: {response['id']}")
            return response['id']
        except Exception as e:
            print(f"⚠️ Upload attempt {attempt+1} failed: {e}")
            time.sleep(5) # Wait before retrying
    raise Exception("❌ Upload failed after multiple retries.")

# ========== MAIN WORKFLOW ==========

# 0. Download movie.webm from Google Drive
if not os.path.exists("movie.webm"):
    download_from_drive(DRIVE_FILE_ID, "movie.webm")
else:
    print("☑️ movie.webm already exists. Skipping download.")

# 1. Convert movie.webm to movie.mp4
if os.path.exists("movie.webm") and not os.path.exists(INPUT_VIDEO):
    print(f"🎬 Converting movie.webm to {INPUT_VIDEO}...")
    try:
        subprocess.run([
            "ffmpeg", "-i", "movie.webm",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-movflags", "+faststart",
            INPUT_VIDEO
        ], check=True, capture_output=True, text=True)
        print(f"✅ Conversion complete: {INPUT_VIDEO}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg conversion failed: {e.stderr}")
        raise
else:
    print(f"☑️ {INPUT_VIDEO} already exists or movie.webm is missing. Skipping conversion.")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 2. Get Video Duration
print("📊 Getting video duration...")
try:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", INPUT_VIDEO
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    duration = float(result.stdout.decode().strip())
    total_parts = int(duration // CLIP_LENGTH) + (1 if duration % CLIP_LENGTH > 0 else 0)
    print(f"🎞️ Total duration: {duration:.2f}s, Will be split into {total_parts} parts.")
except subprocess.CalledProcessError as e:
    print(f"❌ FFprobe failed to get duration: {e.stderr}")
    raise
except ValueError:
    print("❌ Could not parse video duration from ffprobe output.")
    raise

# 3. Process and Upload Each Clip
for i in range(total_parts):
    start_time = i * CLIP_LENGTH
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
    temp_output = os.path.join(OUTPUT_DIR, f"temp_part_{i+1:03}.mp4")
    final_output = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")

    print(f"\n⚙️ Processing part {i+1} (starts at {start_time}s)...")

    # FFmpeg filter complex for scaling, padding, and text overlay
    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease", # Scale video to fit
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=white", # Pad with white background
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}", # Top text
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th" # Bottom text
    ]

    # Optional: Add logo overlay if LOGO_FILE exists
    if os.path.exists(LOGO_FILE):
        # Assuming logo is an image, overlay it on the video
        filter_parts.append(f"movie={LOGO_FILE},scale=200:200[logo];[in][logo]overlay=W-w-50:50")

    vf_filter = ",".join(filter_parts)

    # FFmpeg command to extract clip, apply filters, and encode
    cmd_extract_and_filter = [
        "ffmpeg", "-ss", str(start_time), "-i", INPUT_VIDEO,
        *( ["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else [] ), # Include logo input if present
        "-t", str(CLIP_LENGTH), # Duration of the clip
        "-vf", vf_filter,
        "-r", "30", # Frame rate
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "26", # Video encoding
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100", # Audio encoding
        "-movflags", "+faststart", # Optimize for streaming
        temp_output
    ]
    try:
        subprocess.run(cmd_extract_and_filter, check=True, capture_output=True, text=True)
        print(f"✅ Processed part {i+1} to {temp_output}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg processing failed for part {i+1}: {e.stderr}")
        raise

    # Clean metadata and save to final_output (optional, but good practice)
    # This step ensures cleaner metadata and can sometimes fix playback issues.
    cmd_clean_metadata = [
        "ffmpeg", "-i", temp_output,
        "-map_metadata", "-1", # Remove all metadata
        "-movflags", "+faststart",
        "-c", "copy", # Copy streams without re-encoding
        final_output
    ]
    try:
        subprocess.run(cmd_clean_metadata, check=True, capture_output=True, text=True)
        print(f"✅ Cleaned metadata and saved to {final_output}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg metadata cleaning failed for part {i+1}: {e.stderr}")
        raise
    finally:
        os.remove(temp_output) # Clean up temporary file

    # 4. Upload to Google Drive
    file_metadata = {'name': os.path.basename(final_output), 'parents': [DRIVE_FOLDER_ID]}
    media_mime = mimetypes.guess_type(final_output)[0] or 'video/mp4' # Default to video/mp4 if type can't be guessed
    media = MediaFileUpload(final_output, mimetype=media_mime, resumable=True)
    uploaded_file_id = safe_upload(file_metadata, media)

    # 5. Update Google Sheet
    try:
        sheet.append_row([part_label, os.path.basename(final_output), CLIP_LENGTH, "uploaded", uploaded_file_id])
        print(f"✅ Google Sheet updated for {part_label}")
    except Exception as e:
        print(f"❌ Failed to update Google Sheet for {part_label}: {e}")
        # Don't raise here, as video upload was successful. Log and continue.

    # Clean up the final output file after upload to save space on runner
    os.remove(final_output)
    print(f"🗑️ Cleaned up local file: {final_output}")

print("\n🎉 All done! All parts are processed, uploaded to Drive, and sheet updated.")
```
