from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from yt_dlp import YoutubeDL
import threading, os, uuid

app = Flask(__name__)
CORS(app)

DOWNLOADS = "downloads"
os.makedirs(DOWNLOADS, exist_ok=True)

progress = {}

def download(task_id, url, mode, quality):
    progress[task_id] = {"progress":0,"status":"downloading","file":None}

    quality_map = {
        "1080p": "bestvideo[height<=1080]+bestaudio/best",
        "720p": "bestvideo[height<=720]+bestaudio/best",
        "480p": "bestvideo[height<=480]+bestaudio/best",
        "360p": "bestvideo[height<=360]+bestaudio/best"
    }

    def progress_hook(d):
        if d.get("status") == "downloading":
            if d.get("total_bytes") and d.get("downloaded_bytes"):
                progress[task_id]["progress"] = int((d["downloaded_bytes"] / d["total_bytes"]) * 100)

    opts = {
        "outtmpl": os.path.join(DOWNLOADS, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "merge_output_format": "mp4",  # IMPORTANTE!
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ]
    }

    if mode == "audio":
        opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
        })
    else:
        opts.update({"format": quality_map.get(quality, "720p")})

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if mode == "audio":
                filename = filename.rsplit(".", 1)[0] + ".mp3"
            else:
                filename = filename.rsplit(".", 1)[0] + ".mp4"
            progress[task_id]["file"] = filename
            progress[task_id]["status"] = "done"
    except:
        progress[task_id]["status"] = "error"

@app.get("/download")
def create_download():
    url = request.args.get("url")
    mode = request.args.get("type")
    quality = request.args.get("quality", "720p")
    task = str(uuid.uuid4())
    threading.Thread(target=download, args=(task, url, mode, quality), daemon=True).start()
    return jsonify({"task": task})

@app.get("/progress")
def get_progress():
    return jsonify(progress.get(request.args.get("task"), {"status": "notfound"}))

@app.get("/file")
def get_file():
    task = request.args.get("task")
    file_path = progress.get(task, {}).get("file")
    if file_path and os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
