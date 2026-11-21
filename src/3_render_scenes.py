import os
import json
import glob
import asyncio
import hashlib
import urllib.parse
import subprocess
import requests
import edge_tts

VOICE = "es-AR-TomasNeural"
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
PIXABAY_CACHE = "build/pixabay_cache"

def get_audio_duration(mp3_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(result.stdout)

async def generate_tts_and_subs(text, out_mp3, out_srt, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            communicate = edge_tts.Communicate(text, VOICE, rate="+5%")
            submaker = edge_tts.SubMaker()
            with open(out_mp3, "wb") as audio_file:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio_file.write(chunk["data"])
                    elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                        submaker.feed(chunk)
            with open(out_srt, "w", encoding="utf-8") as srt_file:
                srt_file.write(submaker.get_srt())
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 100:
                return
            raise RuntimeError("Audio vacío")
        except Exception:
            if attempt == max_retries:
                raise
            await asyncio.sleep(4 * attempt)

def fetch_pixabay_video(query, scene_seed):
    if not PIXABAY_KEY:
        return None
    os.makedirs(PIXABAY_CACHE, exist_ok=True)
    
    # Si la búsqueda específica no trae resultados, usa una genérica de artes marciales
    for search_q in [query, "martial arts"]:
        q_hash = hashlib.md5(search_q.lower().encode()).hexdigest()[:10]
        cached_files = sorted(glob.glob(f"{PIXABAY_CACHE}/{q_hash}_*.mp4"))
        if cached_files:
            return cached_files[scene_seed % len(cached_files)]

        try:
            url = f"https://pixabay.com{PIXABAY_KEY}&q={urllib.parse.quote(search_q)}&orientation=horizontal&per_page=6"
            resp = requests.get(url, timeout=15)
            hits = resp.json().get("hits", [])
            downloaded = []
            for idx, hit in enumerate(hits[:4]):
                videos = hit.get("videos", {})
                # Elegir calidad HD (large o medium)
                vid_info = videos.get("large") or videos.get("medium") or videos.get("small")
                if vid_info and vid_info.get("url"):
                    vid_url = vid_info["url"]
                    local_path = f"{PIXABAY_CACHE}/{q_hash}_{idx}.mp4"
                    r = requests.get(vid_url, timeout=30)
                    if r.status_code == 200 and len(r.content) > 50000:
                        with open(local_path, "wb") as f:
                            f.write(r.content)
                        downloaded.append(local_path)
            if downloaded:
                return downloaded[scene_seed % len(downloaded)]
        except Exception as e:
            print(f"  [Aviso Pixabay] Error buscando '{search_q}': {e}")
    return None

def generate_ai_image(prompt, out_img, seed):
    if os.path.exists(out_img) and os.path.getsize(out_img) > 15000:
        return True
    encoded = urllib.parse.quote(prompt)
    url = f"https://pollinations.ai{encoded}?width=1280&height=720&nologo=true&model=flux&seed={seed}"
    for _ in range(3):
        try:
            r = requests.get(url, timeout=45)
            if r.status_code == 200 and len(r.content) > 15000:
                with open(out_img, "wb") as f:
                    f.write(r.content)
                return True
        except Exception:
            pass
    return False

async def render_all():
    script_files = sorted(glob.glob("build/scripts/*_script.json"))
    sub_style = "FontName=DejaVu Sans,FontSize=21,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=42"

    for script_path in script_files:
        with open(script_path, "r", encoding="utf-8") as f:
            script = json.load(f)

        mod_id = os.path.basename(script_path).replace("_script.json", "")
        mod_dir = f"build/renders/{mod_id}"
        os.makedirs(mod_dir, exist_ok=True)
        print(f"Produciendo versiones duales para: {script['module_title']}")

        for scene in script["scenes"]:
            s_num = scene["scene_number"]
            mp3_path = f"{mod_dir}/scene_{s_num:03d}.mp3"
            srt_path = f"{mod_dir}/scene_{s_num:03d}.srt"
            img_path = f"{mod_dir}/scene_{s_num:03d}.jpg"
            
            mp4_pixabay = f"{mod_dir}/scene_{s_num:03d}_pixabay.mp4"
            mp4_ia = f"{mod_dir}/scene_{s_num:03d}_ia.mp4"

            need_pixabay = not (os.path.exists(mp4_pixabay) and os.path.getsize(mp4_pixabay) > 10000)
            need_ia = not (os.path.exists(mp4_ia) and os.path.getsize(mp4_ia) > 10000)

            if not need_pixabay and not need_ia:
                continue

            # 1. Generar voz argentina y subtítulos UNA SOLA VEZ
            if not (os.path.exists(mp3_path) and os.path.exists(srt_path)):
                await generate_tts_and_subs(scene["narration"], mp3_path, srt_path)
            duration = get_audio_duration(mp3_path) + 0.35

            # 2. Renderizar Versión 1: 100% Video Real (Pixabay)
            if need_pixabay:
                broll_path = fetch_pixabay_video(scene.get("pixabay_query", "martial arts"), s_num)
                if broll_path and os.path.exists(broll_path):
                    vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"
                    cmd = [
                        "ffmpeg", "-y", "-stream_loop", "-1", "-i", broll_path, "-i", mp3_path,
                        "-t", f"{duration:.2f}", "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-shortest", mp4_pixabay
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    vf = f"subtitles={srt_path}:force_style='{sub_style}'"
                    cmd = [
                        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0b0f19:s=1920x1080:r=30:d={duration:.2f}",
                        "-i", mp3_path, "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-shortest", mp4_pixabay
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # 3. Renderizar Versión 2: 100% Escenas Cinematográficas IA + Ken Burns
            if need_ia:
                has_img = generate_ai_image(scene.get("ai_image_prompt", "martial arts documentary dark moody"), img_path, s_num * 17)
                frames = int(duration * 30)
                if has_img:
                    if s_num % 2 == 0:
                        zp = f"zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30"
                    else:
                        zp = f"zoompan=z='1.12':x='(iw-iw/zoom)*(on/{max(1, frames)})':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30"
                    vf = f"scale=1920:1080,{zp},subtitles={srt_path}:force_style='{sub_style}'"
                    cmd = [
                        "ffmpeg", "-y", "-loop", "1", "-i", img_path, "-i", mp3_path,
                        "-t", f"{duration:.2f}", "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-shortest", mp4_ia
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    vf = f"subtitles={srt_path}:force_style='{sub_style}'"
                    cmd = [
                        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0b0f19:s=1920x1080:r=30:d={duration:.2f}",
                        "-i", mp3_path, "-vf", vf,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-b:a", "128k", "-shortest", mp4_ia
                    ]
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            print(f"  -> Escena {s_num:02d} lista en ambas versiones ({duration:.1f}s)")

if __name__ == "__main__":
    asyncio.run(render_all())
