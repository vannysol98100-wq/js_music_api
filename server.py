# server.py
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from yt_dlp import YoutubeDL
import threading, os, uuid, tempfile, traceback, shutil

app = Flask(__name__)
CORS(app)

DOWNLOADS = "downloads"
os.makedirs(DOWNLOADS, exist_ok=True)

progress = {}

def download(task_id, url, mode, quality, cookiefile_path=None):
    """
    Faz o download. Se cookiefile_path for passado (caminho local para cookies.txt),
    o yt-dlp usará esse cookiefile.
    """
    progress[task_id] = {"progress": 0, "status": "downloading", "file": None, "note": None}

    quality_map = {
        "1080p": "bestvideo[height<=1080]+bestaudio/best",
        "720p": "bestvideo[height<=720]+bestaudio/best",
        "480p": "bestvideo[height<=480]+bestaudio/best",
        "360p": "bestvideo[height<=360]+bestaudio/best"
    }

    def progress_hook(d):
        if d.get("status") == "downloading":
            if d.get("total_bytes") and d.get("downloaded_bytes"):
                try:
                    progress[task_id]["progress"] = int((d["downloaded_bytes"] / d["total_bytes"]) * 100)
                except Exception:
                    progress[task_id]["progress"] = 0

    opts = {
        "outtmpl": os.path.join(DOWNLOADS, "%(title)s.%(ext)s"),
        "progress_hooks": [progress_hook],
        "merge_output_format": "mp4",
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
        ],
        # iOS client por padrão (melhor bypass). Se cookiefile_path fornecido, cookiefile será usado também.
        "extractor_args": {"youtube": {"player_client": ["ios"]}},
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "quiet": True,
    }

    # Se veio cookiefile, inclua no opts
    if cookiefile_path:
        opts["cookiefile"] = cookiefile_path

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
            # se usamos cookiefile, podemos apagar após finalizado
            if cookiefile_path and os.path.exists(cookiefile_path):
                try:
                    os.remove(cookiefile_path)
                except: pass

    except Exception as e:
        tb = traceback.format_exc()
        # marca o erro e salva um arquivo de debug para investigar
        err_path = os.path.join(DOWNLOADS, f"{task_id}_error.txt")
        with open(err_path, "w", encoding="utf-8") as ef:
            ef.write("Exception:\n")
            ef.write(tb)
        # detecta mensagem de "Sign in to confirm you’re not a bot"
        msg = str(e).lower()
        if "sign in to confirm" in msg or "sign in to confirm" in tb.lower() or "use --cookies" in tb.lower():
            progress[task_id]["status"] = "need_cookies"
            progress[task_id]["note"] = "This video requires cookies (user login). Upload a cookies.txt with the same request or retry with account cookies."
        else:
            progress[task_id]["status"] = "error"
            progress[task_id]["note"] = "Unexpected error. Check error file."
        progress[task_id]["file"] = err_path
        # cleanup cookiefile (if any)
        if cookiefile_path and os.path.exists(cookiefile_path):
            try:
                os.remove(cookiefile_path)
            except: pass

@app.route("/download", methods=["GET", "POST"])
def create_download():
    """
    GET usage (normal): /download?url=...&type=audio&quality=720p
    POST usage (upload cookies): multipart/form-data with fields:
      - url (text)
      - type (text) optional
      - quality (text) optional
      - cookies (file) optional -> cookies.txt uploaded by user
    """
    # accept both GET and POST
    if request.method == "GET":
        url = request.args.get("url")
        mode = request.args.get("type", "audio")
        quality = request.args.get("quality", "720p")
        cookiefile_path = None
    else:
        url = request.form.get("url")
        mode = request.form.get("type", "audio")
        quality = request.form.get("quality", "720p")
        cookiefile_path = None
        # handle uploaded cookies file
        uploaded = request.files.get("cookies")
        if uploaded:
            # Salva em /tmp com nome relacionado ao task (gerado abaixo)
            # mas precisamos do task_id antes - então geramos temporário aqui e renomeamos depois
            tmpdir = tempfile.gettempdir()
            # create a safe tmp file path; will be moved into download thread args
            cookiefile_path = os.path.join(tmpdir, f"cookies_upload_{uuid.uuid4().hex}.txt")
            uploaded.save(cookiefile_path)

    if not url:
        return jsonify({"error": "missing url parameter"}), 400

    task = str(uuid.uuid4())
    # if POST and a cookiefile was uploaded, we already created it above; pass its path to thread
    threading.Thread(target=download, args=(task, url, mode, quality, cookiefile_path), daemon=True).start()
    return jsonify({"task": task})

@app.get("/progress")
def get_progress():
    task = request.args.get("task")
    return jsonify(progress.get(task, {"status": "notfound"}))

@app.get("/file")
def get_file():
    task = request.args.get("task")
    file_path = progress.get(task, {}).get("file")
    if file_path and os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    return "", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
