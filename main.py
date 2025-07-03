import os
import math
import time
import subprocess
import json
import shutil
import mimetypes
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import gspread

# ================= CONFIG =================
SOURCE_VIDEO = "movie.mp4"
OUTPUT_FOLDER = "output_parts"
PART_DURATION = 40  # seconds
SHEET_NAME = "Project3-S3"
DRIVE_FOLDER_ID = "1zgLj5Wg42TFIsi4-60J2w757gvaojcQO"
GOOGLE_CREDENTIALS = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
MAX_UPLOAD_RETRIES = 5
UPLOAD_RETRY_DELAY = 5

# Overlay Config
TOP_TEXT = "Superhit Don no.1"
BOTTOM_TEXT_PREFIX = "PART-"
FONT_FILE = "arial.ttf"
FONT_SIZE = 64
TEXT_COLOR = "black"
CANVAS_W = 1080
CANVAS_H = 1920
TOP_MARGIN = 100
BOTTOM_MARGIN = 150
LOGO_FILE = "logo.png"
# ==========================================

def load_google_clients():
    creds = service_account.Credentials.from_service_account_info(
        GOOGLE_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"],
    )
    drive_service = build("drive", "v3", credentials=creds)
    sheet_client = gspread.authorize(creds)
    return drive_service, sheet_client

def get_video_duration(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as e:
        print(f"⚠️ Error getting duration of {file_path}: {e}")
        return 0

def build_vf_filter(part_label):
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
    return ",".join(filter_parts)

def split_video():
    if os.path.exists(OUTPUT_FOLDER):
        shutil.rmtree(OUTPUT_FOLDER)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    total_duration = get_video_duration(SOURCE_VIDEO)
    num_parts = math.ceil(total_duration / PART_DURATION)

    print(f"🎞️ Total duration: {total_duration}s, Parts: {num_parts}")
    for i in range(num_parts):
        start = i * PART_DURATION
        part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
        temp_output = f"{OUTPUT_FOLDER}/temp_{i+1:03}.mp4"
        final_output = f"{OUTPUT_FOLDER}/part_{i+1:03}.mp4"

        vf_filter = build_vf_filter(part_label)

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", str(start),
            "-t", str(PART_DURATION),
            "-i", SOURCE_VIDEO,
            *( ["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else [] ),
            "-vf", vf_filter,
            "-r", "30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
            "-movflags", "+faststart",
            temp_output
        ]

        print(f"⏳ Encoding Part {i+1}/{num_parts}")
        try:
            subprocess.run(cmd, check=True)
            subprocess.run(["ffmpeg", "-y", "-i", temp_output, "-map_metadata", "-1", "-movflags", "+faststart", "-c", "copy", final_output], check=True)
            os.remove(temp_output)
            print(f"✅ Part {i+1} saved: {final_output}")
        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg failed on part {i+1}: {e}")
            raise

def upload_with_retry(drive_service, file_path, max_retries=MAX_UPLOAD_RETRIES):
    for attempt in range(max_retries):
        try:
            filename = os.path.basename(file_path)
            file_metadata = {
                "name": filename,
                "parents": [DRIVE_FOLDER_ID]
            }
            mime = mimetypes.guess_type(file_path)[0] or 'video/mp4'
            media = MediaFileUpload(file_path, mimetype=mime, resumable=True)
            file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            print(f"✅ Uploaded: {filename} (ID: {file.get('id')})")
            return file.get("id")
        except Exception as e:
            wait_time = UPLOAD_RETRY_DELAY * (2 ** attempt)
            print(f"❌ Upload failed (attempt {attempt+1}/{max_retries}): {e}")
            print(f"🔁 Retrying in {wait_time}s...")
            time.sleep(wait_time)
    raise Exception(f"🚨 Upload permanently failed for {file_path} after {max_retries} attempts.")

def update_sheet(sheet, filename, part_number, duration):
    try:
        sheet.append_row([f"PART-{part_number}", filename, duration, "Uploaded"])
    except Exception as e:
        print(f"⚠️ Failed to update sheet for {filename}: {e}")

def main():
    try:
        print("🔐 Authenticating with Google...")
        drive_service, sheet_client = load_google_clients()
        sheet = sheet_client.open(SHEET_NAME).sheet1

        print("🔪 Splitting video...")
        split_video()

        print("☁️ Uploading parts to Drive...")
        for filename in sorted(os.listdir(OUTPUT_FOLDER)):
            if not filename.endswith(".mp4"):
                continue
            full_path = os.path.join(OUTPUT_FOLDER, filename)
            part_number = int(filename.split("_")[1].split(".")[0])

            try:
                upload_with_retry(drive_service, full_path)
                duration = get_video_duration(full_path)
                update_sheet(sheet, filename, part_number, duration)
            except Exception as e:
                print(f"🔥 Failed to upload {filename}: {e}")
                break

        print("🎉 All done!")
    except Exception as e:
        print(f"💥 Fatal error occurred: {e}")

if __name__ == "__main__":
    main()
