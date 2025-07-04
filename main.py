import os
import json
import subprocess
import mimetypes
import gspread
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from oauth2client.service_account import ServiceAccountCredentials

# ========== CONFIG ==========
DRIVE_FILE_ID = "1Xyqk2ti5S2lKtELz2AWwdzeQI94KCQzf" # movie.webm file ID in Google Drive
DRIVE_FOLDER_ID = "1zgLj5Wg42TFIsi4-60J2w757gvaojcQO"  # Project3-S2 folder ID
INPUT_VIDEO = "movie.mp4"  # Will convert from movie.webm
LOGO_FILE = "logo.png"  # Optional logo file
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
SHEET_NAME = "Project3-S3"

# ========== GOOGLE AUTH ==========
creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
credentials = service_account.Credentials.from_service_account_info(creds_json, scopes=[
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'])

drive_service = build('drive', 'v3', credentials=credentials)
sheet_client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_json))
sheet = sheet_client.open(SHEET_NAME).sheet1

# ========== STEP 0: Download movie.webm from Google Drive ==========
def download_from_drive(file_id, dest_path):
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = drive_service._http.request
        response, content = downloader(request.uri, method='GET')
        f.write(content)

if not os.path.exists("movie.webm"):
    print("⬇️ Downloading movie.webm from Google Drive...")
    download_from_drive(DRIVE_FILE_ID, "movie.webm")

# ========== Convert to movie.mp4 ==========
if os.path.exists("movie.webm") and not os.path.exists("movie.mp4"):
    print("🎬 Converting movie.webm to movie.mp4...")
    subprocess.run([
        "ffmpeg", "-i", "movie.webm",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        INPUT_VIDEO
    ], check=True)

# ========== PREP ==========
os.makedirs(OUTPUT_DIR, exist_ok=True)

def safe_upload(file_metadata, media, retries=5):
    for attempt in range(retries):
        try:
            request = drive_service.files().create(body=file_metadata, media_body=media, fields='id')
            response = None
            while response is None:
                status, response = request.next_chunk()
            return response['id']
        except Exception as e:
            print(f"⚠️ Upload attempt {attempt+1} failed: {e}")
            time.sleep(5)
    raise Exception("❌ Upload failed after multiple retries.")

# ========== STEP 1: Get Video Duration ==========
result = subprocess.run([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", INPUT_VIDEO
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
duration = float(result.stdout.decode().strip())
total_parts = int(duration // CLIP_LENGTH) + 1
print(f"🎞️ Total duration: {duration:.2f}s, Parts: {total_parts}")

# ========== STEP 2: Process and Upload Each Clip ==========
for i in range(total_parts):
    start = i * CLIP_LENGTH
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
    temp_output = os.path.join(OUTPUT_DIR, f"temp_{i+1:03}.mp4")
    final_output = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")

    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease",
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=white",
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}",
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th"
    ]

    if os.path.exists(LOGO_FILE):
        mime = mimetypes.guess_type(LOGO_FILE)[0]
        if mime and mime.startswith('video'):
            filter_parts.append(f"movie={LOGO_FILE},scale=200:200[logo];[0:v][logo]overlay=W-w-50:50")
        else:
            filter_parts.append(f"movie={LOGO_FILE},scale=200:200[logo];[in][logo]overlay=W-w-50:50")

    vf_filter = ",".join(filter_parts)

    # Step 2a: Generate temp output with overlay
    cmd = [
        "ffmpeg", "-ss", str(start), "-i", INPUT_VIDEO,
        *( ["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else [] ),
        "-t", str(CLIP_LENGTH), "-vf", vf_filter,
        "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "26",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart", temp_output
    ]
    subprocess.run(cmd, check=True)

    # Step 2b: Clean metadata and save to final_output
    subprocess.run([
        "ffmpeg", "-i", temp_output,
        "-map_metadata", "-1",
        "-movflags", "+faststart",
        "-c", "copy", final_output
    ], check=True)
    os.remove(temp_output)

    # ========== STEP 3: Upload to Google Drive ==========
    file_metadata = {'name': os.path.basename(final_output), 'parents': [DRIVE_FOLDER_ID]}
    media_mime = mimetypes.guess_type(final_output)[0] or 'video/mp4'
    media = MediaFileUpload(final_output, mimetype=media_mime, resumable=True)
    safe_upload(file_metadata, media)

    # ========== STEP 4: Update Google Sheet ==========
    sheet.append_row([part_label, os.path.basename(final_output), CLIP_LENGTH, "uploaded"])
    print(f"✅ Uploaded: {final_output}")

print("\n🎉 All done! All parts are Instagram Reels-ready and uploaded to Drive.")
