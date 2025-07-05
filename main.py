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
DRIVE_FILE_ID = "1Xyqk2ti5S2lKtELz2AWwdzeQI94KCQzf"  # .webm input
DRIVE_FOLDER_ID = "1zgLj5Wg42TFIsi4-60J2w757gvaojcQO"
INPUT_VIDEO = "movie.mp4"
LOGO_FILE = "logo.png"
OUTPUT_DIR = "output_parts"
CLIP_LENGTH = 40  # seconds
TOP_TEXT = " Don no.1"
BOTTOM_TEXT_PREFIX = "PART-"
FONT_FILE = "arial.ttf"
FONT_SIZE = 64
TEXT_COLOR = "black"
CANVAS_W = 1080
CANVAS_H = 1920
TOP_MARGIN = 550
BOTTOM_MARGIN = 550
SHEET_NAME = "Project3-S3"
VIDEO_BITRATE = "4000k"  # 4 Mbps for Instagram Reels compatibility
FRAME_RATE = "30"
ASPECT_RATIO = "9:16"

# ========== GOOGLE AUTH ==========
creds_json = json.loads(os.environ["GOOGLE_CREDENTIALS"])
credentials = service_account.Credentials.from_service_account_info(creds_json, scopes=[
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'])
drive_service = build('drive', 'v3', credentials=credentials)
sheet_client = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_dict(creds_json))
sheet = sheet_client.open(SHEET_NAME).sheet1

# ========== DOWNLOAD FROM DRIVE ==========
def download_from_drive(file_id, dest_path):
    print(f"⬇️ Downloading {dest_path} from Google Drive (ID: {file_id})...")
    request = drive_service.files().get_media(fileId=file_id)
    with open(dest_path, 'wb') as f:
        downloader = MediaFileUpload(dest_path, resumable=True)
        response = request.execute()
        f.write(response)
    print(f"✅ Downloaded {dest_path}")

if not os.path.exists("movie.webm"):
    download_from_drive(DRIVE_FILE_ID, "movie.webm")

# ========== CONVERT .webm ➜ .mp4 with IG/FB SAFE SETTINGS ==========
if os.path.exists("movie.webm") and not not os.path.exists(INPUT_VIDEO):
    print("🎬 Converting to Instagram-compatible .mp4...")
    subprocess.run([
        "ffmpeg", "-i", "movie.webm",
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", FRAME_RATE,
        "-b:v", VIDEO_BITRATE, "-preset", "medium", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart",
        "-vf", f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1:1",
        "-aspect", ASPECT_RATIO,
        INPUT_VIDEO
    ], check=True)
    print(f"✅ Converted to {INPUT_VIDEO}")

# ========== CREATE OUTPUT FOLDER ==========
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== SAFE UPLOAD FUNCTION ==========
def safe_upload(file_metadata, media, retries=5):
    for attempt in range(retries):
        try:
            request = drive_service.files().create(body=file_metadata, media_body=media, fields='id')
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    print(f"⬆️ Uploading {file_metadata['name']}: {int(status.progress() * 100)}%")
            return response['id']
        except Exception as e:
            print(f"⚠️ Upload attempt {attempt+1} failed: {e}")
            time.sleep(5)
    raise Exception(f"❌ Upload failed for {file_metadata['name']} after {retries} retries.")

# ========== GENERATE DIRECT GOOGLE DRIVE URL ==========
def get_direct_drive_url(file_id):
    return f"https://drive.google.com/uc?export=download&id={file_id}"

# ========== VERIFY VIDEO METADATA ==========
def verify_metadata(file_path):
    print(f"🔍 Verifying metadata for {file_path}...")
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,bit_rate:stream=codec_name,codec_type,width,height,bit_rate,r_frame_rate,pixel_format,sample_rate,channels",
        "-of", "json", file_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    metadata = json.loads(result.stdout.decode())
    print(json.dumps(metadata, indent=2))
    return metadata

# ========== GET DURATION ==========
result = subprocess.run([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", INPUT_VIDEO
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
duration = float(result.stdout.decode().strip())
total_parts = int(duration // CLIP_LENGTH) + (1 if duration % CLIP_LENGTH else 0)
print(f"🎞️ Total duration: {duration:.2f}s, Parts: {total_parts}")

# ========== PROCESS EACH CLIP ==========
for i in range(total_parts):
    start = i * CLIP_LENGTH
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
    temp_output = os.path.join(OUTPUT_DIR, f"temp_{i+1:03}.mp4")
    final_output = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")

    # Filters: scaling, padding, text, SAR
    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease",
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=white",
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}",
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th",
        "setsar=1:1"
    ]

    # Optional logo overlay
    if os.path.exists(LOGO_FILE):
        mime = mimetypes.guess_type(LOGO_FILE)[0]
        if mime and mime.startswith('video'):
            filter_parts.append(f"movie={LOGO_FILE},scale=200:200[logo];[0:v][logo]overlay=W-w-50:50")
        else:
            filter_parts.append(f"movie={LOGO_FILE},scale=200:200[logo];[in][logo]overlay=W-w-50:50")

    vf_filter = ",".join(filter_parts)

    # Step 1: Encode each part with overlay + formatting
    print(f"🎬 Processing part {i+1}...")
    cmd = [
        "ffmpeg", "-ss", str(start), "-i", INPUT_VIDEO,
        *( ["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else [] ),
        "-t", str(CLIP_LENGTH), "-vf", vf_filter,
        "-r", FRAME_RATE, "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-b:v", VIDEO_BITRATE, "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart", "-aspect", ASPECT_RATIO,
        temp_output
    ]
    subprocess.run(cmd, check=True)

    # Step 2: Re-encode and strip metadata (clean output for Reels)
    print(f"🔄 Re-encoding part {i+1} for Instagram compatibility...")
    subprocess.run([
        "ffmpeg", "-i", temp_output,
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-b:v", VIDEO_BITRATE, "-preset", "medium", "-crf", "22",
        "-pix_fmt", "yuv420p", "-r", FRAME_RATE,
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart", "-map_metadata", "-1",
        "-vf", f"setsar=1:1",
        "-aspect", ASPECT_RATIO,
        final_output
    ], check=True)
    os.remove(temp_output)

    # Step 3: Verify metadata
    verify_metadata(final_output)

    # Step 4: Upload to Drive
    file_metadata = {'name': os.path.basename(final_output), 'parents': [DRIVE_FOLDER_ID]}
    media_mime = mimetypes.guess_type(final_output)[0] or 'video/mp4'
    media = MediaFileUpload(final_output, mimetype=media_mime, resumable=True)
    file_id = safe_upload(file_metadata, media)
    direct_url = get_direct_drive_url(file_id)
    print(f"⬆️ Uploaded {final_output} to Drive (ID: {file_id})")
    print(f"🔗 Direct URL: {direct_url}")

    # Step 5: Update Google Sheet
    sheet.append_row([part_label, os.path.basename(final_output), CLIP_LENGTH, "uploaded", direct_url])
    print(f"✅ Processed and uploaded: {final_output}")

print("\n🎉 All done! All parts are Reels-ready, compliant, and uploaded with direct URLs.")