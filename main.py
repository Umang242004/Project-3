# parallel_main.py
import os
import json
import subprocess
import mimetypes
import time
import ssl
import traceback
import gspread
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.errors import HttpError
import base64

# ========== CONFIG ==========
DRIVE_FILE_ID = "1Xyqk2ti5S2lKtELz2AWwdzeQI94KCQzf"
DRIVE_FOLDER_ID = "1zgLj5Wg42TFIsi4-60J2w757gvaojcQO"
INPUT_VIDEO = "movie.mp4"
WEBM_FILE = "movie.webm"
LOGO_FILE = "logo.png"
OUTPUT_DIR = "output_parts"
CLIP_LENGTH = 40
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
MAX_WORKERS = 4  # number of parallel workers

# ========== DECODE GOOGLE_CREDENTIALS ==========
raw = os.environ.get("GOOGLE_CREDENTIALS", "")
if not raw.strip():
    raise Exception("❌ GOOGLE_CREDENTIALS secret is empty or not set.")
try:
    decoded = base64.b64decode(raw).decode()
    creds_json = json.loads(decoded)
except Exception as e:
    raise Exception("❌ Failed to decode GOOGLE_CREDENTIALS. Ensure it is base64-encoded JSON.") from e

credentials = service_account.Credentials.from_service_account_info(creds_json, scopes=[
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'])
drive_service = build('drive', 'v3', credentials=credentials)
sheet_client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_json))
sheet = sheet_client.open(SHEET_NAME).sheet1

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== UTILS ==========
def download_from_drive(file_id, dest_path):
    print(f"⬇️ Downloading {file_id} ➜ {dest_path}")
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        response, content = drive_service._http.request(request.uri, method='GET')
        f.write(content)

def get_video_duration(file):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                             "-of", "default=noprint_wrappers=1:nokey=1", file], stdout=subprocess.PIPE)
    return float(result.stdout.decode().strip())

def safe_run(cmd):
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError:
        traceback.print_exc()
        return False

def safe_upload_to_drive(filepath, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            file_metadata = {'name': os.path.basename(filepath), 'parents': [DRIVE_FOLDER_ID]}
            mime = mimetypes.guess_type(filepath)[0] or 'video/mp4'
            media = MediaFileUpload(filepath, mimetype=mime, resumable=True)
            uploaded = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            return uploaded["id"]
        except Exception as e:
            print(f"⚠️ Upload attempt {attempt} failed: {e}")
            time.sleep(5)
    return None

def get_existing_parts():
    try:
        return set(row[0] for row in sheet.get_all_values()[1:])
    except Exception:
        return set()

def process_part(i, duration):
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
    start = i * CLIP_LENGTH
    temp_out = os.path.join(OUTPUT_DIR, f"temp_{i+1:03}.mp4")
    final_out = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")

    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease",
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=white",
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}",
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th"
    ]

    if os.path.exists(LOGO_FILE):
        mime = mimetypes.guess_type(LOGO_FILE)[0]
        overlay = f"movie={LOGO_FILE},scale=200:200[logo];[0:v][logo]overlay=W-w-50:50" if mime and mime.startswith('video') \
            else f"movie={LOGO_FILE},scale=200:200[logo];[in][logo]overlay=W-w-50:50"
        filter_parts.append(overlay)

    vf = ",".join(filter_parts)

    if not safe_run(["ffmpeg", "-ss", str(start), "-t", str(CLIP_LENGTH), "-i", INPUT_VIDEO,
                     *( ["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else [] ),
                     "-vf", vf, "-r", "30", "-preset", "ultrafast",
                     "-c:v", "libx264", "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
                     "-movflags", "+faststart", temp_out]):
        return part_label, 0, "ffmpeg_error"

    if not safe_run(["ffmpeg", "-i", temp_out, "-map_metadata", "-1", "-movflags", "+faststart", "-c", "copy", final_out]):
        return part_label, 0, "finalize_error"

    os.remove(temp_out)
    file_id = safe_upload_to_drive(final_out)
    actual_duration = round(get_video_duration(final_out), 2)
    status = "uploaded" if file_id else "upload_failed"
    return part_label, actual_duration, status

# ========== RUN ==========
if not os.path.exists(WEBM_FILE):
    download_from_drive(DRIVE_FILE_ID, WEBM_FILE)
if not os.path.exists(INPUT_VIDEO):
    safe_run(["ffmpeg", "-i", WEBM_FILE, "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
              "-movflags", "+faststart", INPUT_VIDEO])

video_duration = get_video_duration(INPUT_VIDEO)
total_parts = int(video_duration // CLIP_LENGTH) + 1
existing_parts = get_existing_parts()

print(f"🧹 Total parts: {total_parts}. Starting parallel processing with {MAX_WORKERS} workers.")

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(process_part, i, video_duration): f"{BOTTOM_TEXT_PREFIX}{i+1}"
        for i in range(total_parts)
        if f"{BOTTOM_TEXT_PREFIX}{i+1}" not in existing_parts
    }
    for future in as_completed(futures):
        part, dur, status = future.result()
        sheet.append_row([part, f"part_{int(part.split('-')[1]):03}.mp4", dur, status])
        print(f"✅ {part} → {status}")

print("\n🎉 All parts processed.")
