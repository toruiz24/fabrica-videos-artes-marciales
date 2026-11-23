import os
import re
import json
import glob
import time
import shutil
import hashlib
import asyncio
import subprocess
import requests
from playwright.async_api import async_playwright

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
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 100:
                return
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(4 * attempt)

def infer_technique_config(scene):
    text = f"{scene.get('narration', '')} {scene.get('pose_prompt', '')} {scene.get('motion_prompt', '')}".lower()

    weapon = "fist"
    w_label = "GOLPE DE PUÑO"
    if any(k in text for k in ["palma", "palm", "mano abierta", "talón de la mano"]):
        weapon, w_label = "palm", "GOLPE DE PALMA ABIERTA"
    elif any(k in text for k in ["codo", "elbow", "codazo"]):
        weapon, w_label = "elbow", "GOLPE DE CODO"
    elif any(k in text for k in ["rodilla", "knee", "rodillazo"]):
        weapon, w_label = "knee", "GOLPE DE RODILLA"
    elif any(k in text for k in ["patada", "kick", "empeine", "tibia", "pie"]):
        weapon, w_label = "kick", "PATADA TÁCTICA"
    elif any(k in text for k in ["bloqueo", "guardia", "desvío", "defensa", "esquive"]):
        weapon, w_label = "block", "GUARDIA Y DESVÍO"

    target = "chin"
    t_label = "AL MENTÓN"
    if any(k in text for k in ["nariz", "tabique", "nose"]):
        target, t_label = "nose", "AL TABIQUE NASAL"
    elif any(k in text for k in ["garganta", "cuello", "tráquea", "throat"]):
        target, t_label = "throat", "A LA GARGANTA"
    elif any(k in text for k in ["plexo", "estómago", "abdomen", "boca del estómago", "solar"]):
        target, t_label = "solar_plexus", "AL PLEXO SOLAR"
    elif any(k in text for k in ["ingle", "genital", "testículo", "zona baja", "groin"]):
        target, t_label = "groin", "A LA ZONA BAJA"
    elif any(k in text for k in ["rodilla", "pierna", "muslo", "canilla"]):
        target, t_label = "knee", "A LA RODILLA"

    trajectory = "straight"
    if any(k in text for k in ["ascendente", "desde abajo", "uppercut", "subiendo"]):
        trajectory = "uppercut"
    elif any(k in text for k in ["circular", "gancho", "hook", "lateral"]):
        trajectory = "hook"

    torso_lock = any(k in text for k in ["sin torcer", "bloqueado", "cero grados", "recto", "eje", "sin rotar"]) or weapon == "palm"

    raw_narr = re.sub(r'\s+', ' ', scene.get("narration", "")).strip()
    subtitle = (raw_narr[:78] + "...") if len(raw_narr) > 80 else raw_narr

    return {
        "title": f"{w_label} {t_label}",
        "subtitle": subtitle,
        "weapon": weapon,
        "target": target,
        "trajectory": trajectory,
        "torsoLock": torso_lock
    }

def fetch_pixabay_video(query, scene_seed):
    os.makedirs(PIXABAY_VID_CACHE, exist_ok=True)
    if not PIXABAY_KEY:
        return None
    for search_q in [query, "martial arts training", "boxing gym", "self defense", "focus silhouette"]:
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
async def render_fitness_animation(page, config, duration, mp3_path, srt_path, out_mp4):
    frames_dir = "build/fitness_frames"
    if os.path.exists(frames_dir):
        shutil.rmtree(frames_dir)
    os.makedirs(frames_dir, exist_ok=True)

    fps = 30
    total_frames = max(60, int(duration * fps))
    await page.evaluate("(cfg) => window.setConfig(cfg)", config)

    for frame in range(total_frames):
        ratio = frame / max(1, total_frames - 1)
        await page.evaluate("(r) => window.renderFrame(r)", ratio)
        await page.screenshot(path=f"{frames_dir}/f_{frame:05d}.png")

    sub_style = "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", f"{frames_dir}/f_%05d.png",
        "-i", mp3_path,
        "-t", f"{duration:.2f}",
        "-vf", f"subtitles={srt_path}:force_style='{sub_style}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        out_mp4
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def render_all():
    script_files = sorted(glob.glob("build/scripts/*_script.json"))
    sub_style = "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35"
    html_uri = "file://" + os.path.abspath("src/fitness_animator.html")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(html_uri)

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
                final_scene_mp4 = f"{mod_dir}/scene_{s_num:03d}.mp4"
                tech_flag = f"{mod_dir}/scene_{s_num:03d}_fitness.done"

                v_type = scene.get("visual_type", "broll_context")
                is_tech = (v_type == "ai_technique")

                # Si es escena de contexto ya hecha, la conserva; si es técnica vieja, la reemplaza por el animador biomecánico
                if os.path.exists(final_scene_mp4) and os.path.getsize(final_scene_mp4) > 80000:
                    if not is_tech or os.path.exists(tech_flag):
                        continue

                if not (os.path.exists(mp3_path) and os.path.exists(srt_path)):
                    generate_tts_and_subs(scene["narration"], mp3_path, srt_path)
                duration = get_audio_duration(mp3_path) + 0.35

                if is_tech:
                    cfg = infer_technique_config(scene)
                    await render_fitness_animation(page, cfg, duration, mp3_path, srt_path, final_scene_mp4)
                    with open(tech_flag, "w") as tf:
                        tf.write("ok")
                    print(f"  -> Escena {s_num:02d} [TÉCNICA BIOMECÁNICA: {cfg['title']}] lista ({duration:.1f}s)")
                else:
                    source_video = fetch_pixabay_video(scene.get("pixabay_query", "martial arts training"), s_num)
                    if not source_video or not os.path.exists(source_video):
                        print(f"  [Aviso] Sin video disponible para escena {s_num}, saltando...")
                        continue

                    vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"
                    subprocess.run([
                        "ffmpeg", "-y", "-stream_loop", "-1", "-i", source_video, "-i", mp3_path,
                        "-t", f"{duration:.2f}", "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k",
                        final_scene_mp4
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"  -> Escena {s_num:02d} [CONTEXTO REAL] lista ({duration:.1f}s)")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(render_all())
