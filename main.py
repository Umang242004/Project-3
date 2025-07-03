
# main.py
import os
import json
import subprocess
import mimetypes
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ========== CONFIG ==========
INPUT_VIDEO = "movie.mp4"
LOGO_FILE = "logo.png"  # Optional, supports image or video
OUTPUT_DIR = "output_parts"
CLIP_LENGTH = 40  # seconds
TOP_TEXT = "Superhit Don no.1"
BOTTOM_TEXT_PREFIX = "PART-"
FONT_FILE = "arial.ttf"
FONT_SIZE = 64
TEXT_COLOR = "black"
CANVAS_W = 1080
CANVAS_H = 1920
TOP_MARGIN = 100
BOTTOM_MARGIN = 150

DRIVE_FOLDER_NAME = "Project3-S2"
SHEET_NAME = "Project3-S3"

# ========== GOOGLE AUTH ==========
creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
credentials = service_account.Credentials.from_service_account_info(creds_json, scopes=[
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'])

drive_service = build('drive', 'v3', credentials=credentials)
sheet_client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_json))
sheet = sheet_client.open(SHEET_NAME).sheet1

# ========== PREP ==========
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# ========== STEP 1: Get Video Duration ==========
result = subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=noprint_wrappers=1:nokey=1", INPUT_VIDEO],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT
)
duration = float(result.stdout)
total_parts = int(duration // CLIP_LENGTH) + 1

# ========== STEP 2: Split Video with Overlays ==========
for i in range(total_parts):
    start = i * CLIP_LENGTH
    output_file = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"

    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease",
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=white",
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}",
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th"
    ]

    if os.path.exists(LOGO_FILE):
        mime = mimetypes.guess_type(LOGO_FILE)[0]
        if mime and mime.startswith('video'):
            overlay_cmd = f"[1:v]scale=200:200[logo];[0:v][logo]overlay=W-w-50:50"
        else:
            overlay_cmd = f"overlay=W-w-50:50"
        filter_parts.append(f"movie={LOGO_FILE},{overlay_cmd}")

    vf_filter = ",".join(filter_parts)

    cmd = [
        "ffmpeg",
        "-ss", str(start),
        "-i", INPUT_VIDEO,
        *( ["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else [] ),
        "-t", str(CLIP_LENGTH),
        "-vf", vf_filter,
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        "-ar", "44100",
        "-movflags", "+faststart",
        output_file
    ]

    subprocess.run(cmd)

    # ========== STEP 3: Upload to Google Drive ==========
    file_metadata = {'name': os.path.basename(output_file), 'parents': [DRIVE_FOLDER_NAME]}
    media_mime = mimetypes.guess_type(output_file)[0] or 'video/mp4'
    media_body = {'mimeType': media_mime, 'name': os.path.basename(output_file)}

    upload = drive_service.files().create(
        body=file_metadata,
        media_body=output_file,
        fields='id'
    ).execute()

    # ========== STEP 4: Update Google Sheet ==========
    sheet.append_row([
        part_label,
        os.path.basename(output_file),
        CLIP_LENGTH,
        "uploaded"
    ])

print("\n✅ All done!")
