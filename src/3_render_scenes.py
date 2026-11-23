import os
import re
import json
import glob
import time
import hashlib
import subprocess
import requests

PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
PIXABAY_VID_CACHE = "build/pixabay_videos"
VOICE = "es-AR-TomasNeural"

API_HEADERS = {"Accept": "application/json"}
CDN_HEADERS = {"Referer": "https://" + "://pixabay.com"}
PIXABAY_VID_BASE = "https://" + "pixabay.com" + "/api/videos/"

def get_audio_duration(mp3_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path]
    return float(subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout)

def generate_tts_and_subs(text, out_mp3, out_srt, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            subprocess.run([
                "edge-tts", "--voice", VOICE, "--rate=+4%",
                "--text", text,
                "--write-media", out_mp3,
                "--write-subtitles", out_srt
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 500:
                return
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(4 * attempt)

def clean_ffmpeg_text(txt):
    txt = re.sub(r'[^\w\sáéíóúÁÉÍÓÚñÑüÜ°\-\.\,\(\)]', '', txt)
    return txt.replace(":", " -").replace("'", "").strip()

def analyze_scene_action(scene):
    text = f"{scene.get('narration', '')} {scene.get('pose_prompt', '')} {scene.get('motion_prompt', '')}".lower()

    if any(k in text for k in ["palma", "mano abierta", "talón de la mano"]):
        return "TECNICA: GOLPE DE PALMA ABIERTA", "IMPACTO: MENTON / TABIQUE", "self defense strike martial arts"
    if any(k in text for k in ["codo", "codazo"]):
        return "TECNICA: GOLPE DE CODO", "IMPACTO: SIEN / MANDIBULA", "muay thai elbow training"
    if any(k in text for k in ["rodilla", "rodillazo"]):
        return "TECNICA: GOLPE DE RODILLA", "IMPACTO: PLEXO / ZONA MEDIA", "muay thai knee kickboxing"
    if any(k in text for k in ["patada", "empeine", "tibia", "low kick"]):
        return "TECNICA: PATADA TACTICA", "IMPACTO: RODILLA / MUSLO / ZONA BAJA", "kickboxing low kick training"
    if any(k in text for k in ["puño", "recto", "jab", "gancho", "uppercut"]):
        return "TECNICA: GOLPE DE PUNO DIRECTO", "IMPACTO: MENTON / PLEXO SOLAR", "boxing punch slow motion"
    if any(k in text for k in ["bloqueo", "guardia", "desvío", "esquive", "distancia"]):
        return "TECNICA: GUARDIA Y CONTROL DE DISTANCIA", "OBJETIVO: PROTECCION Y ANGULO", "boxing defense sparring"
    if any(k in text for k in ["agarre", "sujeción", "muñeca", "cuello", "estrangul"]):
        return "TECNICA: ESCAPE DE AGARRE", "OBJETIVO: PALANCA Y SALIDA", "self defense grappling martial arts"

    return "ANALISIS TACTICO DE COMBATE", "EJECUCION Y CONTROL DE EJE", "martial arts self defense training"
def fetch_pixabay_video(query, scene_seed):
    os.makedirs(PIXABAY_VID_CACHE, exist_ok=True)
    if not PIXABAY_KEY:
        return None
    for search_q in [query, "martial arts training", "boxing sparring", "kickboxing", "self defense"]:
        q_hash = hashlib.md5(search_q.lower().encode()).hexdigest()[:10]
        cached = sorted(glob.glob(f"{PIXABAY_VID_CACHE}/{q_hash}_*.mp4"))
        if cached:
            return cached[scene_seed % len(cached)]
        try:
            time.sleep(0.8)
            params = {"key": PIXABAY_KEY, "q": search_q, "per_page": 6}
            resp = requests.get(PIXABAY_VID_BASE, params=params, headers=API_HEADERS, timeout=20)
            if resp.status_code != 200:
                continue
            downloaded = []
            for idx, hit in enumerate(resp.json().get("hits", [])[:4]):
                vids = hit.get("videos", {})
                info = vids.get("medium") or vids.get("large") or vids.get("small")
                if info and info.get("url"):
                    local_path = f"{PIXABAY_VID_CACHE}/{q_hash}_{idx}.mp4"
                    r = requests.get(info["url"], headers=CDN_HEADERS, timeout=40)
                    if r.status_code == 200 and len(r.content) > 100000:
                        with open(local_path, "wb") as f:
                            f.write(r.content)
                        downloaded.append(local_path)
            if downloaded:
                return downloaded[scene_seed % len(downloaded)]
        except Exception:
            pass
    return None

def render_all():
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
            out_v5 = f"{mod_dir}/scene_{s_num:03d}_v5.mp4"

            if os.path.exists(out_v5) and os.path.getsize(out_v5) > 80000:
                continue

            if not (os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 500 and os.path.exists(srt_path)):
                generate_tts_and_subs(scene["narration"], mp3_path, srt_path)
            duration = get_audio_duration(mp3_path) + 0.35

            v_type = scene.get("visual_type", "broll_context")
            is_tech = (v_type == "ai_technique")

            if is_tech:
                tech_title, tech_target, specific_query = analyze_scene_action(scene)
                source_video = fetch_pixabay_video(specific_query, s_num)
                if not source_video or not os.path.exists(source_video):
                    continue

                t1 = clean_ffmpeg_text(tech_title)
                t2 = clean_ffmpeg_text(tech_target)
                vf = (
                    f"setpts=1.35*PTS,"
                    f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,"
                    f"drawbox=x=40:y=35:w=960:h=96:color=black@0.78:t=fill,"
                    f"drawbox=x=40:y=35:w=10:h=96:color=#f59e0b:t=fill,"
                    f"drawtext=font='DejaVu Sans':text='{t1}':fontcolor=white:fontsize=26:x=68:y=50,"
                    f"drawtext=font='DejaVu Sans':text='{t2}':fontcolor=#f59e0b:fontsize=21:x=68:y=88,"
                    f"drawbox=x=1560:y=45:w=310:h=54:color=#0284c7@0.9:t=fill,"
                    f"drawtext=font='DejaVu Sans':text='ANALISIS EN CAMARA LENTA':fontcolor=white:fontsize=18:x=1582:y=63,"
                    f"subtitles={srt_path}:force_style='{sub_style}'"
                )
            else:
                source_video = fetch_pixabay_video(scene.get("pixabay_query", "martial arts training"), s_num)
                if not source_video or not os.path.exists(source_video):
                    continue
                vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"

            subprocess.run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", source_video, "-i", mp3_path,
                "-t", f"{duration:.2f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                out_v5
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            tag = "TECNICA + ANALISIS" if is_tech else "CONTEXTO REAL"
            print(f"  -> Escena {s_num:02d} [{tag}] lista ({duration:.1f}s)")

if __name__ == "__main__":
    render_all()
