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

    def hook(d):
        if d["status"]=="downloading":
            if d.get("total_bytes") and d.get("downloaded_bytes"):
                progress[task_id]["progress"] = int((d["downloaded_bytes"]/d["total_bytes"])*100)

    opts = {
        "progress_hooks":[hook],
        "outtmpl":os.path.join(DOWNLOADS,"%(_filename)s.%(ext)s")
    }

    if mode=="audio":
        opts.update({
            "format":"bestaudio/best",
            "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3"}]
        })
    else:
        opts.update({"format":quality_map.get(quality,"720p")})

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url,download=True)
            if mode=="audio":
                file= os.path.join(DOWNLOADS,info["title"]+".mp3")
            else:
                file = ydl.prepare_filename(info)
            progress[task_id]["file"]=file
            progress[task_id]["status"]="done"
    except:
        progress[task_id]["status"]="error"

@app.get("/download")
def dl():
    url=request.args.get("url")
    mode=request.args.get("type")
    quality=request.args.get("quality","720p")
    task=str(uuid.uuid4())
    threading.Thread(target=download,args=(task,url,mode,quality),daemon=True).start()
    return jsonify({"task":task})

@app.get("/progress")
def prg():
    task=request.args.get("task")
    return jsonify(progress.get(task,{"status":"notfound"}))

@app.get("/file")
def file():
    task=request.args.get("task")
    file=progress.get(task,{}).get("file")
    if file and os.path.exists(file):
        return send_file(file,as_attachment=True)
    return "",404

if __name__=="__main__":
    app.run(host="0.0.0.0",port=8080)
