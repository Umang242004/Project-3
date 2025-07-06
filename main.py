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
TOP_TEXT = "Superhit Don no.1"
BOTTOM_TEXT_PREFIX = "PART-"
FONT_FILE = "arial.ttf"
FONT_SIZE = 96
TEXT_COLOR = "black"
CANVAS_W = 1080  # Set to 478 for testing with successful reel's resolution
CANVAS_H = 1920  # Set to 850 for testing
TOP_MARGIN = 550
BOTTOM_MARGIN = 550
SHEET_NAME = "Project3-S3"
VIDEO_BITRATE = "4000k"  # 4 Mbps for 1080p, use "1500k" if testing 478x850
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
        media = MediaFileUpload(dest_path, resumable=True)
        response = request.execute()
        f.write(response)
    print(f"✅ Downloaded {dest_path}")

if not os.path.exists("movie.webm"):
    download_from_drive(DRIVE_FILE_ID, "movie.webm")

# ========== VERIFY METADATA ==========
def verify_metadata(file_path):
    print(f"🔍 Verifying metadata for {file_path}...")
    result = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,bit_rate,format_name:stream=codec_name,codec_type,width,height,bit_rate,r_frame_rate,pixel_format,sample_rate,channels,sample_aspect_ratio",
        "-of", "json", file_path
    ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    metadata = json.loads(result.stdout)
    print(json.dumps(metadata, indent=2))
    return metadata

# Check source video metadata
print("🔍 Checking source video metadata...")
verify_metadata("movie.webm")

# ========== CONVERT .webm ➜ .mp4 with IG/FB SAFE SETTINGS ==========
if os.path.exists("movie.webm") and not os.path.exists(INPUT_VIDEO):
    print("🎬 Converting to Instagram-compatible .mp4 (Pass 1)...")
    cmd_pass1 = [
        "ffmpeg", "-i", "movie.webm",
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", FRAME_RATE,
        "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_BITRATE, "-bufsize", f"{int(VIDEO_BITRATE.replace('k', '')) * 2}k",
        "-pass", "1", "-preset", "medium",
        "-an", "-vf", f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1:1",
        "-f", "mp4", "-y", "NUL"
    ]
    result = subprocess.run(cmd_pass1, capture_output=True, text=True, check=True)
    print(f"FFmpeg Pass 1 Output: {result.stdout}")

    print("🎬 Converting to Instagram-compatible .mp4 (Pass 2)...")
    cmd_pass2 = [
        "ffmpeg", "-i", "movie.webm",
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-pix_fmt", "yuv420p", "-r", FRAME_RATE,
        "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_BITRATE, "-bufsize", f"{int(VIDEO_BITRATE.replace('k', '')) * 2}k",
        "-pass", "2", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart",
        "-vf", f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1:1",
        "-aspect", ASPECT_RATIO, "-map_metadata", "-1",
        "-f", "mp4", INPUT_VIDEO
    ]
    result = subprocess.run(cmd_pass2, capture_output=True, text=True, check=True)
    print(f"FFmpeg Pass 2 Output: {result.stdout}")
    print(f"✅ Converted to {INPUT_VIDEO}")
    verify_metadata(INPUT_VIDEO)

# ========== CREATE OUTPUT FOLDER ==========
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ========== SAFE UPLOAD FUNCTION ==========
def safe_upload(file_metadata, media, retries=5):
    for attempt in range(retries):
        try:
            file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            permission = {'type': 'anyone', 'role': 'reader'}
            drive_service.permissions().create(fileId=file['id'], body=permission).execute()
            return file['id']
        except Exception as e:
            print(f"⚠️ Upload attempt {attempt+1} failed: {e}")
            time.sleep(5)
    raise Exception(f"❌ Upload failed for {file_metadata['name']} after {retries} retries.")

# ========== GENERATE DIRECT GOOGLE DRIVE URL ==========
def get_direct_drive_url(file_id):
    return f"https://drive.google.com/uc?export=download&id={file_id}"

# ========== GET DURATION ==========
result = subprocess.run([
    "ffprobe", "-v", "error", "-show_entries", "format=duration",
    "-of", "default=noprint_wrappers=1:nokey=1", INPUT_VIDEO
], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
duration = float(result.stdout.strip())
total_parts = int(duration // CLIP_LENGTH) + (1 if duration % CLIP_LENGTH else 0)
print(f"🎞️ Total duration: {duration:.2f}s, Parts: {total_parts}")

# ========== PROCESS EACH CLIP ==========
for i in range(total_parts):
    start = i * CLIP_LENGTH
    part_label = f"{BOTTOM_TEXT_PREFIX}{i+1}"
    output_file = os.path.join(OUTPUT_DIR, f"part_{i+1:03}.mp4")

    # Filters: scaling, padding, text, SAR
    filter_parts = [
        f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease",
        f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2:color=black",
        f"drawtext=fontfile={FONT_FILE}:text='{TOP_TEXT}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y={TOP_MARGIN}",
        f"drawtext=fontfile={FONT_FILE}:text='{part_label}':fontsize={FONT_SIZE}:fontcolor={TEXT_COLOR}:x=(w-text_w)/2:y=h-{BOTTOM_MARGIN}-th",
        "setsar=1:1"
    ]

    # Optional logo overlay (simplified)
    if os.path.exists(LOGO_FILE):
        filter_parts.append(f"movie={LOGO_FILE},scale=200:-1[logo];[in][logo]overlay=W-w-50:50")

    vf_filter = ",".join(filter_parts)

    # Two-pass encoding for clip
    print(f"🎬 Processing part {i+1} (Pass 1)...")
    cmd_pass1 = [
        "ffmpeg", "-ss", str(start), "-i", INPUT_VIDEO,
        *(["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else []),
        "-t", str(CLIP_LENGTH), "-vf", vf_filter,
        "-r", FRAME_RATE, "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_BITRATE, "-bufsize", f"{int(VIDEO_BITRATE.replace('k', '')) * 2}k",
        "-pass", "1", "-preset", "medium",
        "-an", "-f", "mp4", "-y", "NUL"
    ]
    result = subprocess.run(cmd_pass1, capture_output=True, text=True, check=True)
    print(f"FFmpeg Pass 1 Output: {result.stdout}")

    print(f"🎬 Processing part {i+1} (Pass 2)...")
    cmd_pass2 = [
        "ffmpeg", "-ss", str(start), "-i", INPUT_VIDEO,
        *(["-i", LOGO_FILE] if os.path.exists(LOGO_FILE) else []),
        "-t", str(CLIP_LENGTH), "-vf", vf_filter,
        "-r", FRAME_RATE, "-c:v", "libx264", "-profile:v", "main", "-level", "4.0",
        "-b:v", VIDEO_BITRATE, "-maxrate", VIDEO_BITRATE, "-bufsize", f"{int(VIDEO_BITRATE.replace('k', '')) * 2}k",
        "-pass", "2", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100",
        "-movflags", "+faststart", "-aspect", ASPECT_RATIO,
        "-map_metadata", "-1", "-f", "mp4",
        output_file
    ]
    result = subprocess.run(cmd_pass2, capture_output=True, text=True, check=True)
    print(f"FFmpeg Pass 2 Output: {result.stdout}")

    # Verify metadata
    metadata = verify_metadata(output_file)

    # Upload to Drive
    file_metadata = {
        'name': os.path.basename(output_file),
        'parents': [DRIVE_FOLDER_ID]
    }
    media_mime = mimetypes.guess_type(output_file)[0] or 'video/mp4'
    media = MediaFileUpload(output_file, mimetype=media_mime, resumable=True)
    file_id = safe_upload(file_metadata, media)
    direct_url = get_direct_drive_url(file_id)
    print(f"⬆️ Uploaded {output_file} to Drive (ID: {file_id})")
    print(f"🔗 Direct URL: {direct_url}")

    # Update Google Sheet
    sheet.append_row([part_label, os.path.basename(output_file), CLIP_LENGTH, "uploaded", direct_url])
    print(f"✅ Processed and uploaded: {output_file}")

print("\n🎉 All done! All parts are Reels-ready, compliant, and uploaded with direct URLs.")