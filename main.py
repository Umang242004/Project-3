import os
import json
import subprocess
import mimetypes
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ========== CONFIG ==========
DRIVE_FILE_ID = "1Xyqk2ti5S2lKtELz2AWwdzeQI94KCQzf"  # .webm
DRIVE_FOLDER_ID = "1zgLj5Wg42TFIsi4-60J2w757gvaojcQO"
INPUT_VIDEO = "movie.webm"
LOGO_FILE = "logo.png"
OUTPUT_DIR = "output_parts"
CLIP_LENGTH = 40
TOP_TEXT = " Don no.1"
BOTTOM_TEXT_PREFIX = "PART-"
FONT_FILE = "arial.ttf"
FONT_SIZE = 96
TEXT_COLOR = "black"
CANVAS_W, CANVAS_H = 1080, 1920
TOP_MARGIN, BOTTOM_MARGIN = 550, 550
FRAME_RATE = "30"
VIDEO_BITRATE = "4000k"

# ========== GOOGLE AUTH ==========
creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
credentials = service_account.Credentials.from_service_account_info(creds_json, scopes=[
    'https://www.googleapis.com/auth/drive'
])
drive_service = build('drive', 'v3', credentials=credentials)

# ========== DOWNLOAD .webm ==========
def download_from_drive(file_id, dest_path):
    print(f"⬇️ Downloading {dest_path} from Google Drive...")
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        f.write(request.execute())
    print(f"✅ Downloaded: {dest_path}")

if not os.path.exists(INPUT_VIDEO):
    download_from_drive(DRIVE_FILE_ID, INPUT_VIDEO)

# ========== GET DURATION ==========
def get_duration(file_path):
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(result.stdout.strip())

duration = get_duration(INPUT_VIDEO)
total_parts = int(duration // CLIP_LENGTH) + (1 if duration % CLIP_LENGTH else 0)
print(f"🎞️ Total duration: {duration:.2f}s → {total_parts} parts")

# ========== OUTPUT FOLDER ==========
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== UPLOAD TO DRIVE ==========
def upload_to_drive(local_file):
    print(f"⬆️ Uploading {local_file} to Drive...")
    file_metadata = {
        'name': os.path.basename(local_file),
        'parents': [DRIVE_FOLDER_ID]
    }
    mime_type = mimetypes.guess_type(local_file)[0] or 'video/mp4'
    media = MediaFileUpload(local_file, mimetype=mime_type, resumable=True)

    for attempt in range(5):
        try:
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            drive_service.permissions().create(fileId=file['id'], body={'type': 'anyone', 'role': 'reader'}).execute()
            url = f"https://drive.google.com/uc?export=download&id={file['id']}"
            print(f"✅ Uploaded ➜ {url}")
            return url
        except Exception as e:
            print(f"⚠️ Attempt {attempt+1} failed: {e}")
            time.sleep(5)
    raise Exception(f"❌ Upload failed for {local_file}")

# ========== SPLIT & PROCESS ==========
for i in range(total_parts):
    start = i * CLIP_LENGTH
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
    output_file = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")

    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease",
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=black",
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}",
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th",
        "setsar=1:1"
    ]

    if os.path.exists(LOGO_FILE):
        filter_parts.append(f"movie={LOGO_FILE},scale=200:-1[logo];[in][logo]overlay=W-w-50:50")

    vf_filter = ",".join(filter_parts)

    print(f"🎬 Creating part {i+1}")
    subprocess.run([
        "ffmpeg", "-ss", str(start), "-i", INPUT_VIDEO,
        *(["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else []),
        "-t", str(CLIP_LENGTH),
        "-vf", vf_filter,
        "-r", FRAME_RATE,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart",
        "-y", output_file
    ], check=True)

    upload_to_drive(output_file)

print("\n🎉 Done! All `.webm` parts are overlayed and uploaded.")
