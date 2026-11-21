import os
import json
import glob
import time
import hashlib
import urllib.parse
import subprocess
import requests

VOICE = "es-AR-TomasNeural"
PIXABAY_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
PIXABAY_VID_CACHE = "build/pixabay_videos"
PIXABAY_IMG_CACHE = "build/pixabay_photos"

API_HEADERS = {"Accept": "application/json"}
CDN_HEADERS = {"Referer": "https://pixabay.com"}
WIKI_HEADERS = {"User-Agent": "FabricaDocumentalBot/1.0 (https://github.com)"}

def get_audio_duration(mp3_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(result.stdout)

def generate_tts_and_subs(text, out_mp3, out_srt, max_retries=5):
    for attempt in range(1, max_retries + 1):
        try:
            subprocess.run([
                "edge-tts", "--voice", VOICE, "--rate=+5%",
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

def fetch_wikimedia_video(query, scene_seed):
    os.makedirs(PIXABAY_VID_CACHE, exist_ok=True)
    for search_q in [query, "martial arts", "boxing", "karate", "self defense"]:
        q_hash = "wiki_" + hashlib.md5(search_q.lower().encode()).hexdigest()[:10]
        cached = sorted(glob.glob(f"{PIXABAY_VID_CACHE}/{q_hash}_*.mp4"))
        if cached:
            return cached[scene_seed % len(cached)]
        try:
            url = (
                "https://wikimedia.org"
                f"&gsrsearch=filetype:video+{urllib.parse.quote(search_q)}&gsrnamespace=6"
                "&gsrlimit=6&prop=videoinfo&viprop=url&format=json"
            )
            resp = requests.get(url, headers=WIKI_HEADERS, timeout=20)
            pages = resp.json().get("query", {}).get("pages", {})
            downloaded = []
            for idx, page in enumerate(list(pages.values())[:4]):
                vinfo_list = page.get("videoinfo", [])
                vurl = vinfo_list[0].get("url", "") if vinfo_list else ""
                if vurl.lower().endswith((".webm", ".mp4", ".ogv")):
                    raw_path = f"{PIXABAY_VID_CACHE}/{q_hash}_{idx}.raw"
                    mp4_path = f"{PIXABAY_VID_CACHE}/{q_hash}_{idx}.mp4"
                    r = requests.get(vurl, headers=WIKI_HEADERS, timeout=45)
                    if r.status_code == 200 and len(r.content) > 100000:
                        with open(raw_path, "wb") as f:
                            f.write(r.content)
                        subprocess.run([
                            "ffmpeg", "-y", "-i", raw_path, "-t", "25",
                            "-c:v", "libx264", "-preset", "ultrafast", "-an", mp4_path
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if os.path.exists(mp4_path) and os.path.getsize(mp4_path) > 50000:
                            downloaded.append(mp4_path)
            if downloaded:
                print(f"  [Wikimedia Video OK] {len(downloaded)} clips reales para '{search_q}'")
                return downloaded[scene_seed % len(downloaded)]
        except Exception as e:
            print(f"  [Aviso Wikimedia] '{search_q}': {e}")
    return None

def fetch_pixabay_video(query, scene_seed):
    os.makedirs(PIXABAY_VID_CACHE, exist_ok=True)
    if PIXABAY_KEY:
        for search_q in [query, "martial arts", "boxing", "kickboxing", "training", "city night"]:
            q_hash = hashlib.md5(search_q.lower().encode()).hexdigest()[:10]
            cached = sorted(glob.glob(f"{PIXABAY_VID_CACHE}/{q_hash}_*.mp4"))
            if cached:
                return cached[scene_seed % len(cached)]
            try:
                url = f"https://pixabay.comapi/videos/?key={PIXABAY_KEY}&q={urllib.parse.quote(search_q)}&per_page=6"
                resp = requests.get(url, headers=API_HEADERS, timeout=20)
                if resp.status_code != 200:
                    print(f"  [Aviso Pixabay] HTTP {resp.status_code}: {resp.text[:80]}")
                    break
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
                    print(f"  [Pixabay Video OK] {len(downloaded)} clips reales para '{search_q}'")
                    return downloaded[scene_seed % len(downloaded)]
            except Exception as e:
                print(f"  [Aviso Pixabay] Error con '{search_q}': {e}")
    return fetch_wikimedia_video(query, scene_seed)
def fetch_wikimedia_photo(query, out_img, scene_seed):
    os.makedirs(PIXABAY_IMG_CACHE, exist_ok=True)
    for search_q in [query, "martial arts", "boxing", "karate", "self defense"]:
        q_hash = "wikiphoto_" + hashlib.md5(search_q.lower().encode()).hexdigest()[:10]
        cached_imgs = sorted(glob.glob(f"{PIXABAY_IMG_CACHE}/{q_hash}_*.jpg"))
        if cached_imgs:
            chosen = cached_imgs[scene_seed % len(cached_imgs)]
            with open(chosen, "rb") as src, open(out_img, "wb") as dst:
                dst.write(src.read())
            return True
        try:
            url = (
                "https://wikimedia.org"
                f"&gsrsearch=filetype:bitmap+{urllib.parse.quote(search_q)}&gsrnamespace=6"
                "&gsrlimit=6&prop=imageinfo&iiprop=url&iiurlwidth=1280&format=json"
            )
            resp = requests.get(url, headers=WIKI_HEADERS, timeout=20)
            pages = resp.json().get("query", {}).get("pages", {})
            downloaded = []
            for idx, page in enumerate(list(pages.values())[:4]):
                iinfo = page.get("imageinfo", [{}])[0]
                img_url = iinfo.get("thumburl") or iinfo.get("url", "")
                if img_url.lower().endswith((".jpg", ".jpeg", ".png")):
                    local_path = f"{PIXABAY_IMG_CACHE}/{q_hash}_{idx}.jpg"
                    r = requests.get(img_url, headers=WIKI_HEADERS, timeout=30)
                    if r.status_code == 200 and len(r.content) > 20000:
                        with open(local_path, "wb") as f:
                            f.write(r.content)
                        downloaded.append(local_path)
            if downloaded:
                chosen = downloaded[scene_seed % len(downloaded)]
                with open(chosen, "rb") as src, open(out_img, "wb") as dst:
                    dst.write(src.read())
                return True
        except Exception:
            pass
    return False

def fetch_pixabay_photo_fallback(query, out_img, scene_seed):
    os.makedirs(PIXABAY_IMG_CACHE, exist_ok=True)
    if PIXABAY_KEY:
        for search_q in [query, "martial arts", "boxing", "self defense", "street night"]:
            q_hash = hashlib.md5(search_q.lower().encode()).hexdigest()[:10]
            cached_imgs = sorted(glob.glob(f"{PIXABAY_IMG_CACHE}/{q_hash}_*.jpg"))
            if cached_imgs:
                chosen = cached_imgs[scene_seed % len(cached_imgs)]
                with open(chosen, "rb") as src, open(out_img, "wb") as dst:
                    dst.write(src.read())
                return True
            try:
                url = f"https://pixabay.com{PIXABAY_KEY}&q={urllib.parse.quote(search_q)}&image_type=photo&orientation=horizontal&per_page=6"
                resp = requests.get(url, headers=API_HEADERS, timeout=20)
                if resp.status_code != 200:
                    break
                downloaded = []
                for idx, hit in enumerate(resp.json().get("hits", [])[:4]):
                    img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                    if img_url:
                        local_path = f"{PIXABAY_IMG_CACHE}/{q_hash}_{idx}.jpg"
                        r = requests.get(img_url, headers=CDN_HEADERS, timeout=30)
                        if r.status_code == 200 and len(r.content) > 20000:
                            with open(local_path, "wb") as f:
                                f.write(r.content)
                            downloaded.append(local_path)
                if downloaded:
                    chosen = downloaded[scene_seed % len(downloaded)]
                    with open(chosen, "rb") as src, open(out_img, "wb") as dst:
                        dst.write(src.read())
                    return True
            except Exception:
                pass
    return fetch_wikimedia_photo(query, out_img, scene_seed)

def generate_ai_image(prompt, fallback_query, out_img, seed):
    if os.path.exists(out_img) and os.path.getsize(out_img) > 20000:
        return True
    encoded = urllib.parse.quote(prompt)
    url = f"https://pollinations.ai{encoded}?width=1280&height=720&nologo=true&seed={seed}"
    for attempt in range(1, 3):
        try:
            r = requests.get(url, headers=WIKI_HEADERS, timeout=45)
            if r.status_code == 200 and len(r.content) > 20000 and b"html" not in r.content[:200].lower():
                with open(out_img, "wb") as f:
                    f.write(r.content)
                return True
            print(f"  [Aviso IA Img] HTTP {r.status_code} (intento {attempt})")
        except Exception as e:
            print(f"  [Aviso IA Img] Timeout/Error (intento {attempt}): {e}")
    return fetch_pixabay_photo_fallback(fallback_query, out_img, seed)

def render_all():
    script_files = sorted(glob.glob("build/scripts/*_script.json"))
    sub_style = "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35"

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

            need_pixabay = not (os.path.exists(mp4_pixabay) and os.path.getsize(mp4_pixabay) > 50000)
            need_ia = not (os.path.exists(mp4_ia) and os.path.getsize(mp4_ia) > 50000)

            if not need_pixabay and not need_ia:
                continue

            if not (os.path.exists(mp3_path) and os.path.exists(srt_path)):
                generate_tts_and_subs(scene["narration"], mp3_path, srt_path)
            duration = get_audio_duration(mp3_path) + 0.35

            if need_pixabay:
                broll_path = fetch_pixabay_video(scene.get("pixabay_query", "martial arts"), s_num)
                if not broll_path or not os.path.exists(broll_path):
                    raise RuntimeError("No se pudo descargar ningún video de Pixabay ni Wikimedia.")
                vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"
                subprocess.run([
                    "ffmpeg", "-y", "-stream_loop", "-1", "-i", broll_path, "-i", mp3_path,
                    "-t", f"{duration:.2f}", "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", mp4_pixabay
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if need_ia:
                has_img = generate_ai_image(
                    scene.get("ai_image_prompt", "martial arts documentary"),
                    scene.get("pixabay_query", "martial arts"),
                    img_path,
                    s_num * 17
                )
                if not has_img:
                    raise RuntimeError("No se pudo obtener imagen IA ni respaldo fotográfico.")
                frames = int(duration * 30)
                if s_num % 2 == 0:
                    zp = f"zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30"
                else:
                    zp = f"zoompan=z='1.12':x='(iw-iw/zoom)*(on/{max(1, frames)})':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30"
                vf = f"scale=1920:1080,{zp},subtitles={srt_path}:force_style='{sub_style}'"
                subprocess.run([
                    "ffmpeg", "-y", "-loop", "1", "-i", img_path, "-i", mp3_path,
                    "-t", f"{duration:.2f}", "-vf", vf,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", mp4_ia
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            print(f"  -> Escena {s_num:02d} lista con video real e imagen ({duration:.1f}s)")

if __name__ == "__main__":
    render_all()
