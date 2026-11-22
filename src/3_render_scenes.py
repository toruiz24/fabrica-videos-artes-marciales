import os
import json
import glob
import time
import shutil
import hashlib
import subprocess
import requests
from huggingface_hub import HfApi, login
from gradio_client import Client, handle_file

HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
if HF_TOKEN:
    login(token=HF_TOKEN)

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

def find_media(res, exts):
    if isinstance(res, str) and os.path.exists(res) and any(res.lower().endswith(e) for e in exts):
        return res
    if isinstance(res, dict):
        for k in ("video", "image", "value", "path", "url"):
            f = find_media(res.get(k), exts)
            if f:
                return f
    if isinstance(res, (list, tuple)):
        for x in res:
            f = find_media(x, exts)
            if f:
                return f
    return None

def generate_hd_keyframe(pose_prompt, out_img):
    if os.path.exists(out_img) and os.path.getsize(out_img) > 30000:
        return "OK"
    if not HF_TOKEN:
        return "NO_TOKEN"

    api = HfApi(token=HF_TOKEN)
    spaces = ["black-forest-labs/FLUX.1-schnell", "multimodalart/FLUX.1-merged"]
    try:
        for s in api.list_spaces(search="FLUX.1-schnell", sort="likes", limit=8):
            if s.id not in spaces:
                spaces.append(s.id)
    except Exception:
        pass

    quota_hit = False
    for sid in spaces:
        try:
            if api.get_space_runtime(sid).stage != "RUNNING":
                continue
            c = Client(sid, verbose=False)
            named = c.view_api(return_format="dict").get("named_endpoints", {})
            for ep, info in named.items():
                if "login" in ep.lower():
                    continue
                params = info.get("parameters", [])
                p_prompt = next((p for p in params if "prompt" in p.get("parameter_name", "").lower()), None)
                if not p_prompt:
                    continue
                kw = {}
                for p in params:
                    n = p.get("parameter_name", "")
                    if n == p_prompt["parameter_name"]:
                        kw[n] = pose_prompt
                    elif n.lower() == "width":
                        kw[n] = 1280
                    elif n.lower() == "height":
                        kw[n] = 720
                    elif p.get("parameter_has_default"):
                        kw[n] = p.get("parameter_default")
                img = find_media(c.predict(api_name=ep, **kw), (".png", ".jpg", ".webp"))
                if img and os.path.getsize(img) > 30000:
                    shutil.copyfile(img, out_img)
                    return "OK"
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "exceeded" in err or "429" in err or "gpu" in err:
                quota_hit = True
            print(f"  [Aviso FLUX] {sid}: {str(e)[:80]}")
    return "QUOTA" if quota_hit else "FAIL"
def animate_hd_i2v(img_path, motion_prompt, out_mp4):
    if os.path.exists(out_mp4) and os.path.getsize(out_mp4) > 80000:
        return "OK"
    if not HF_TOKEN:
        return "NO_TOKEN"

    api = HfApi(token=HF_TOKEN)
    spaces = ["Wan-AI/Wan2.1", "Lightricks/ltx-video-distilled", "Lightricks/LTX-Video"]
    try:
        for q in ["Wan2.2", "Wan2.1", "LTX-Video", "image-to-video"]:
            for s in api.list_spaces(search=q, sort="likes", limit=12):
                if s.id not in spaces and not any(b in s.id.lower() for b in ("modelscope", "damo", "whisper", "upscale")):
                    spaces.append(s.id)
    except Exception:
        pass

    quota_hit = False
    for sid in spaces:
        try:
            if api.get_space_runtime(sid).stage != "RUNNING":
                continue
            c = Client(sid, verbose=False)
            named = c.view_api(return_format="dict").get("named_endpoints", {})
            for ep, info in named.items():
                if any(w in ep.lower() for w in ("login", "upscale", "t2v")):
                    continue
                params = info.get("parameters", [])
                p_img = next((p for p in params if any(w in p.get("parameter_name", "").lower() for w in ("image", "img", "first_frame"))), None)
                p_txt = next((p for p in params if "prompt" in p.get("parameter_name", "").lower() and "neg" not in p.get("parameter_name", "").lower()), None)
                if not (p_img and p_txt):
                    continue
                kw = {}
                for p in params:
                    n = p.get("parameter_name", "")
                    if n == p_img["parameter_name"]:
                        kw[n] = handle_file(img_path)
                    elif n == p_txt["parameter_name"]:
                        kw[n] = motion_prompt
                    elif "neg" in n.lower():
                        kw[n] = "blurry, distorted hands, extra fingers, watermark, text, low quality, static"
                    elif p.get("parameter_has_default"):
                        kw[n] = p.get("parameter_default")
                vid = find_media(c.predict(api_name=ep, **kw), (".mp4", ".webm"))
                if vid and os.path.getsize(vid) > 80000:
                    shutil.copyfile(vid, out_mp4)
                    return "OK"
        except Exception as e:
            err = str(e).lower()
            if "quota" in err or "exceeded" in err or "429" in err or "gpu" in err:
                quota_hit = True
            print(f"  [Aviso I2V] {sid}: {str(e)[:80]}")
    return "QUOTA" if quota_hit else "FAIL"

def fetch_pixabay_video(query, scene_seed):
    os.makedirs(PIXABAY_VID_CACHE, exist_ok=True)
    if not PIXABAY_KEY:
        return None
    for search_q in [query, "martial arts", "boxing", "kickboxing", "training", "city night"]:
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
        print(f"Produciendo capítulo: {script['module_title']}")

        for scene in script["scenes"]:
            s_num = scene["scene_number"]
            mp3_path = f"{mod_dir}/scene_{s_num:03d}.mp3"
            srt_path = f"{mod_dir}/scene_{s_num:03d}.srt"
            key_img = f"{mod_dir}/scene_{s_num:03d}_key.png"
            raw_ai = f"{mod_dir}/scene_{s_num:03d}_raw_ai.mp4"
            final_mp4 = f"{mod_dir}/scene_{s_num:03d}.mp4"

            if os.path.exists(final_mp4) and os.path.getsize(final_mp4) > 50000:
                continue

            if not (os.path.exists(mp3_path) and os.path.exists(srt_path)):
                generate_tts_and_subs(scene["narration"], mp3_path, srt_path)
            duration = get_audio_duration(mp3_path) + 0.35

            if scene.get("scene_type") == "ai_technique":
                res_img = generate_hd_keyframe(scene.get("initial_pose_prompt", ""), key_img)
                if res_img == "QUOTA":
                    print("⏸️ Cupo diario de ZeroGPU alcanzado en FLUX. Guardando progreso para reanudar automáticamente...")
                    return
                if res_img == "OK":
                    res_vid = animate_hd_i2v(key_img, scene.get("motion_action_prompt", ""), raw_ai)
                    if res_vid == "QUOTA":
                        print("⏸️ Cupo diario de ZeroGPU alcanzado en I2V. Guardando progreso para reanudar automáticamente...")
                        return
                    if res_vid == "OK":
                        raw_dur = get_audio_duration(raw_ai)
                        spd = max(1.0, duration / max(0.5, raw_dur))
                        vf = f"setpts={spd:.2f}*PTS,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"
                        subprocess.run([
                            "ffmpeg", "-y", "-i", raw_ai, "-i", mp3_path,
                            "-t", f"{duration:.2f}", "-vf", vf,
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "128k", "-shortest", final_mp4
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print(f"  -> Escena {s_num:02d} [Técnica IA HD] lista ({duration:.1f}s)")
                        continue

            broll = fetch_pixabay_video(scene.get("pixabay_query", "martial arts"), s_num)
            if not broll or not os.path.exists(broll):
                raise RuntimeError("No se pudo obtener video real de respaldo en Pixabay.")

            vf = f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"
            subprocess.run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", broll, "-i", mp3_path,
                "-t", f"{duration:.2f}", "-vf", vf,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-shortest", final_mp4
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"  -> Escena {s_num:02d} [Contexto HD] lista ({duration:.1f}s)")

if __name__ == "__main__":
    render_all()
