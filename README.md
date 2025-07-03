# 🎬 Auto Reels Split & Upload Pipeline

This repo automates:

1. Splitting a movie into 40s vertical Instagram Reels
2. Optional logo/banner overlay (image or video)
3. Uploading clips to a Google Drive folder
4. Logging metadata into Google Sheets

---

## ✅ Prerequisites

- Python 3.8+
- FFmpeg (installed & in PATH)
- Google Cloud Service Account JSON (added to GitHub Secrets)
- A Drive folder (`Project3-S2`) shared with the service account
- A Sheet named `Project3-S3` with columns:


---

## 🗂️ Files Included

| File             | Purpose                                |
| ---------------- | -------------------------------------- |
| `main.py`        | Main automation logic                  |
| `requirements.txt`| Python dependencies                   |
| `.github/workflows/reels.yml` | GitHub Actions automation |
| `movie.mp4`      | Your full movie (upload manually)      |
| `logo.png` or `logo.mp4` | (Optional) Logo/banner overlay |

---

## 🔐 GitHub Secrets Needed

| Name                | Value                                |
| ------------------- | ------------------------------------ |
| `GOOGLE_CREDENTIALS`| Contents of your service account JSON |

---

## ▶️ Run Locally

```bash
pip install -r requirements.txt
python main.py
 
---

Let me know if you’d like me to bundle everything (`main.py`, `requirements.txt`, `.github/workflows/reels.yml`, `README.md`) into a `.zip` and give it to you now.
