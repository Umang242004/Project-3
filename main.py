import os
from googleapiclient.http import MediaFileUpload

PARTS_DIR = 'output_parts'
FOLDER_ID = '1zgLj5Wg42TFIsi4-60J2w757gvaojcQO'  # ✅ Your Drive folder ID

for filename in sorted(os.listdir(PARTS_DIR)):
    if not filename.endswith('.mp4'):
        continue

    file_path = os.path.join(PARTS_DIR, filename)
    print(f"📤 Uploading {filename}...")

    file_metadata = {
        'name': filename,
        'parents': [FOLDER_ID]
    }

    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
    request = drive_service.files().create(body=file_metadata, media_body=media, fields='id')

    response = None
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"   ➤ Upload progress: {int(status.progress() * 100)}%")
        except Exception as e:
            print(f"⚠️ Error uploading {filename}: {e}")
            break

    if response:
        print(f"✅ Uploaded: {filename} (File ID: {response.get('id')})")
