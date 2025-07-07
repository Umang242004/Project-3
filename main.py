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

# Download the .webm file if it doesn't exist
if not os.path.exists("movie.webm"):
    download_from_drive(DRIVE_FILE_ID, "movie.webm")

# ========== SIMPLE CONVERSION ==========
if os.path.exists("movie.webm") and not os.path.exists("movie.mp4"):
    print("🎬 Converting .webm to .mp4...")
    cmd = [
        "ffmpeg", "-i", "movie.webm",
        "-c:v", "libx264", "-c:a", "aac",
        "movie.mp4"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    print("✅ Conversion complete!")
    print(f"Output: movie.mp4")
else:
    print("❌ movie.webm not found or movie.mp4 already exists")

print("\n🎉 Done! Simple .webm to .mp4 conversion completed.")
