import os
import re
import json
import glob
import time
import hashlib
import subprocess
import urllib.request

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
YT_COOKIES_TXT = os.environ.get("YT_COOKIES", "").strip()

YT_CACHE = "build/yt_clips"
COOKIES_FILE = "build/yt_cookies.txt"
VOICE = "es-AR-TomasNeural"

def setup_cookies():
    if YT_COOKIES_TXT:
        os.makedirs("build", exist_ok=True)
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(YT_COOKIES_TXT)
        return COOKIES_FILE
    return None

def get_audio_duration(mp3_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path]
    out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout.strip()
    return float(out) if out else 0.0

def has_real_audio(mp3_path):
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 2000:
        return False
    if get_audio_duration(mp3_path) < 1.0:
        return False
    cmd = ["ffmpeg", "-i", mp3_path, "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    m = re.search(r"max_volume:\s*([-\d\.]+)\s*dB", res.stdout)
    return bool(m and float(m.group(1)) > -45.0)

def generate_tts_and_subs(text, out_mp3, out_srt, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            subprocess.run([
                "edge-tts", "--voice", VOICE, "--rate=+4%",
                "--text", text,
                "--write-media", out_mp3,
                "--write-subtitles", out_srt
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if has_real_audio(out_mp3) and os.path.exists(out_srt):
                return
        except Exception:
            pass
        time.sleep(3 * attempt)
    raise RuntimeError("No se pudo generar voz válida tras varios intentos.")

def clean_drawtext(txt):
    txt = re.sub(r'[^\w\sáéíóúÁÉÍÓÚñÑüÜ\-\.\,\(\)\/]', '', txt)
    return txt.replace(":", " -").replace("'", "").strip()

def get_youtube_search_query(scene):
    narration = scene.get("narration", "")
    is_tech = (scene.get("visual_type") == "ai_technique")

    if is_tech:
        instruction = (
            "Sos un experto en artes marciales y defensa personal. Dada esta narración, "
            "devolvé ÚNICAMENTE una búsqueda corta en inglés (4 a 6 palabras) para encontrar en YouTube "
            "una demostración técnica exacta de ese golpe, bloqueo o movimiento (ej: 'open palm strike chin self defense tutorial'). "
        )
    else:
        instruction = (
            "Sos un editor de documentales de artes marciales. Dada esta narración de contexto, "
            "devolvé ÚNICAMENTE una búsqueda corta en inglés (4 a 6 palabras) para encontrar en YouTube "
            "un video real de entrenamiento, sparring o situación de defensa personal acorde (ej: 'martial arts sparring gym training'). "
        )

    prompt = f"{instruction}Sin comillas ni explicaciones.\nNarración: {narration}"

    if GEMINI_KEY:
        try:
            url = f"https://googleapis.com{GEMINI_KEY}"
            data = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.loads(r.read().decode("utf-8"))
                q = res["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"')
                if q:
                    return q
        except Exception:
            pass
    if OPENROUTER_KEY:
        try:
            url = "https://openrouter.ai"
            payload = {"model": "google/gemini-2.5-flash", "messages": [{"role": "user", "content": prompt}]}
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_KEY}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                res = json.loads(r.read().decode("utf-8"))
                q = res["choices"][0]["message"]["content"].strip().strip('"')
                if q:
                    return q
        except Exception:
            pass
    return "self defense martial arts technique tutorial"
def download_youtube_clip(query, duration, cookies_path, scene_seed=0):
    os.makedirs(YT_CACHE, exist_ok=True)
    q_hash = hashlib.md5(f"{query.lower()}_{scene_seed}".encode()).hexdigest()[:10]
    cached_mp4 = f"{YT_CACHE}/{q_hash}.mp4"
    cached_meta = f"{YT_CACHE}/{q_hash}.json"

    if os.path.exists(cached_mp4) and os.path.getsize(cached_mp4) > 80000 and os.path.exists(cached_meta):
        with open(cached_meta, "r", encoding="utf-8") as f:
            return cached_mp4, json.load(f)

    base_cmd = ["yt-dlp", "--no-warnings", "--no-playlist", "--match-filter", "duration > 30 & duration < 900"]
    if cookies_path and os.path.exists(cookies_path):
        base_cmd.extend(["--cookies", cookies_path])

    try:
        info_cmd = base_cmd + ["--dump-json", "--max-downloads", "1", f"ytsearch4:{query}"]
        res = subprocess.run(info_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
        lines = [l for l in res.stdout.splitlines() if l.strip().startswith("{")]
        if not lines:
            return None, None
        meta_raw = json.loads(lines[0])
        vid_url = meta_raw.get("webpage_url")
        vid_dur = float(meta_raw.get("duration") or 60)
        uploader = meta_raw.get("uploader") or meta_raw.get("channel") or "YouTube Creator"
        title = meta_raw.get("title") or query

        # Saltar intro típica (35s o 25% del video) y recortar exactamente la duración necesaria
        start_sec = min(35.0, max(5.0, vid_dur * 0.25))
        end_sec = min(vid_dur - 2.0, start_sec + duration + 3.0)
        if end_sec <= start_sec + 3.0:
            start_sec, end_sec = 0.0, min(vid_dur, duration + 3.0)

        dl_cmd = [
            "yt-dlp", "--no-warnings",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
            "--download-sections", f"*{start_sec:.1f}-{end_sec:.1f}",
            "--force-keyframes-at-cuts",
            "-o", cached_mp4, vid_url
        ]
        if cookies_path and os.path.exists(cookies_path):
            dl_cmd.extend(["--cookies", cookies_path])

        subprocess.run(dl_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        if os.path.exists(cached_mp4) and os.path.getsize(cached_mp4) > 80000:
            meta = {"uploader": uploader, "title": title, "url": vid_url}
            with open(cached_meta, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)
            return cached_mp4, meta
    except Exception as e:
        print(f"  [Aviso YT] No se pudo bajar '{query}': {str(e)[:70]}")
    return None, None

def render_all():
    cookies_path = setup_cookies()
    script_files = sorted(glob.glob("build/scripts/*_script.json"))
    sub_style = "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35"

    for script_path in script_files:
        with open(script_path, "r", encoding="utf-8") as f:
            script = json.load(f)

        mod_id = os.path.basename(script_path).replace("_script.json", "")
        mod_dir = f"build/renders/{mod_id}"
        os.makedirs(mod_dir, exist_ok=True)
        print(f"Procesando capítulo: {script.get('module_title', mod_id)}")

        for scene in script["scenes"]:
            s_num = scene["scene_number"]
            mp3_path = f"{mod_dir}/scene_{s_num:03d}.mp3"
            srt_path = f"{mod_dir}/scene_{s_num:03d}.srt"
            out_yt = f"{mod_dir}/scene_{s_num:03d}_yt.mp4"
            credit_json = f"{mod_dir}/scene_{s_num:03d}_credit.json"

            if os.path.exists(out_yt) and os.path.getsize(out_yt) > 80000:
                continue

            if not (has_real_audio(mp3_path) and os.path.exists(srt_path)):
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
                generate_tts_and_subs(scene["narration"], mp3_path, srt_path)
            duration = get_audio_duration(mp3_path) + 0.35

            yt_query = get_youtube_search_query(scene)
            print(f"  Buscando en YouTube: '{yt_query}'...")
            source_video, yt_meta = download_youtube_clip(yt_query, duration, cookies_path, s_num)

            # Respaldo dentro de YouTube si la búsqueda muy específica no trajo resultados
            if not source_video:
                source_video, yt_meta = download_youtube_clip("martial arts self defense training", duration, cookies_path, s_num)

            if not source_video or not os.path.exists(source_video):
                print(f"  [Aviso] Sin video disponible para escena {s_num}, saltando...")
                continue

            vf_parts = [
                "scale=1920:1080:force_original_aspect_ratio=increase",
                "crop=1920:1080",
                "setsar=1"
            ]

            if yt_meta:
                with open(credit_json, "w", encoding="utf-8") as cf:
                    json.dump(yt_meta, cf, ensure_ascii=False)
                credit_lbl = clean_drawtext(f"Fuente YouTube: {yt_meta['uploader']}")[:55]
                vf_parts.append("drawbox=x=30:y=28:w=640:h=44:color=black@0.65:t=fill")
                vf_parts.append(f"drawtext=font='DejaVu Sans':text='{credit_lbl}':fontcolor=white@0.9:fontsize=18:x=46:y=41")

            vf_parts.append(f"subtitles={srt_path}:force_style='{sub_style}'")
            vf = ",".join(vf_parts)

            subprocess.run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", source_video, "-i", mp3_path,
                "-t", f"{duration:.2f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                out_yt
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            print(f"  -> Escena {s_num:02d} [YOUTUBE: {yt_meta['uploader']}] lista ({duration:.1f}s)")

if __name__ == "__main__":
    render_all()
