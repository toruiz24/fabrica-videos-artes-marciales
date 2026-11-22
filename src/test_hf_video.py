import os, shutil, subprocess
from huggingface_hub import HfApi, login
from gradio_client import Client, handle_file

HF_TOKEN = os.environ["HF_TOKEN"]
login(token=HF_TOKEN)

VOICE = "es-AR-TomasNeural"
NARRATION = (
    "Fijate bien en este golpe: lanzás la palma abierta directo hacia el mentón del agresor, "
    "manteniendo el tronco completamente bloqueado a cero grados, sin rotar los hombros."
)
IMG_PROMPT = (
    "Photorealistic martial arts instructional photograph, side profile medium shot, "
    "self defense instructor in dark t-shirt executing a crisp open palm heel strike to an attacker's chin, "
    "instructor torso and shoulders completely straight and vertical without twisting, "
    "clear anatomical hands, clean modern dojo background, sharp focus, 8k, no text, no watermark"
)
VID_PROMPT = (
    "Smooth realistic martial arts movement, the instructor drives his open palm forward into the attacker's chin "
    "while keeping his torso completely straight and locked, natural impact reaction, sharp focus, steady camera"
)

def get_dur(p):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", p])
    return float(out)

def find_media(res, exts):
    if isinstance(res, str) and os.path.exists(res) and any(res.lower().endswith(e) for e in exts):
        return res
    if isinstance(res, dict):
        for k in ("video", "image", "value", "path", "url"):
            v = res.get(k)
            f = find_media(v, exts)
            if f: return f
    if isinstance(res, (list, tuple)):
        for x in res:
            f = find_media(x, exts)
            if f: return f
    return None

def generate_hd_keyframe(out_img):
    api = HfApi(token=HF_TOKEN)
    spaces = ["black-forest-labs/FLUX.1-schnell", "multimodalart/FLUX.1-merged"]
    try:
        for s in api.list_spaces(search="FLUX.1-schnell", sort="likes", limit=8):
            if s.id not in spaces: spaces.append(s.id)
    except Exception:
        pass

    for sid in spaces:
        try:
            if api.get_space_runtime(sid).stage != "RUNNING": continue
            print(f"Paso 1 (Imagen HD FLUX): {sid}...")
            c = Client(sid, verbose=False)
            named = c.view_api(return_format="dict").get("named_endpoints", {})
            for ep, info in named.items():
                if "login" in ep.lower(): continue
                params = info.get("parameters", [])
                p_prompt = next((p for p in params if "prompt" in p.get("parameter_name", "").lower()), None)
                if not p_prompt: continue
                kw = {}
                for p in params:
                    n = p.get("parameter_name", "")
                    if n == p_prompt["parameter_name"]: kw[n] = IMG_PROMPT
                    elif n.lower() == "width": kw[n] = 1280
                    elif n.lower() == "height": kw[n] = 720
                    elif p.get("parameter_has_default"): kw[n] = p.get("parameter_default")
                img = find_media(c.predict(api_name=ep, **kw), (".png", ".jpg", ".webp"))
                if img and os.path.getsize(img) > 30000:
                    shutil.copyfile(img, out_img)
                    print(f"  -> Fotograma maestro HD generado en {sid}")
                    return True
        except Exception as e:
            print(f"  [Salto FLUX] {sid}: {str(e)[:90]}")
    return False

def animate_hd_i2v(img_path, out_mp4):
    api = HfApi(token=HF_TOKEN)
    spaces = ["Wan-AI/Wan2.1", "Lightricks/ltx-video-distilled", "Lightricks/LTX-Video"]
    try:
        for q in ["Wan2.2", "Wan2.1", "LTX-Video", "image-to-video"]:
            for s in api.list_spaces(search=q, sort="likes", limit=10):
                if s.id not in spaces and not any(b in s.id.lower() for b in ("modelscope", "damo", "whisper")):
                    spaces.append(s.id)
    except Exception:
        pass

    for sid in spaces:
        try:
            if api.get_space_runtime(sid).stage != "RUNNING": continue
            print(f"Paso 2 (Animación HD I2V): {sid}...")
            c = Client(sid, verbose=False)
            named = c.view_api(return_format="dict").get("named_endpoints", {})
            for ep, info in named.items():
                if "login" in ep.lower(): continue
                params = info.get("parameters", [])
                p_img = next((p for p in params if any(w in p.get("parameter_name", "").lower() for w in ("image", "img", "input_img"))), None)
                p_txt = next((p for p in params if "prompt" in p.get("parameter_name", "").lower() and "neg" not in p.get("parameter_name", "").lower()), None)
                if not (p_img and p_txt): continue
                kw = {}
                for p in params:
                    n = p.get("parameter_name", "")
                    if n == p_img["parameter_name"]: kw[n] = handle_file(img_path)
                    elif n == p_txt["parameter_name"]: kw[n] = VID_PROMPT
                    elif "neg" in n.lower(): kw[n] = "blurry, distorted hands, extra fingers, watermark, text, low quality"
                    elif p.get("parameter_has_default"): kw[n] = p.get("parameter_default")
                vid = find_media(c.predict(api_name=ep, **kw), (".mp4", ".webm"))
                if vid and os.path.getsize(vid) > 80000:
                    shutil.copyfile(vid, out_mp4)
                    print(f"  -> ¡Clip HD animado en {sid}!")
                    return True
        except Exception as e:
            print(f"  [Salto I2V] {sid}: {str(e)[:90]}")
    return False

def main():
    os.makedirs("build/test_hf", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    img, raw, mp3, srt, out = "build/test_hf/key.png", "build/test_hf/raw.mp4", "build/test_hf/v.mp3", "build/test_hf/s.srt", "output/test_palma_ia_real.mp4"
    subprocess.run(["edge-tts", "--voice", VOICE, "--rate=+3%", "--text", NARRATION, "--write-media", mp3, "--write-subtitles", srt], check=True)
    adur = get_dur(mp3) + 0.4
    if not generate_hd_keyframe(img): raise RuntimeError("No se pudo generar el fotograma maestro HD.")
    if not animate_hd_i2v(img, raw): raise RuntimeError("No se pudo animar el clip HD.")
    spd = max(1.0, adur / max(0.5, get_dur(raw)))
    st = "FontName=DejaVu Sans,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=38"
    vf = f"setpts={spd:.2f}*PTS,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt}:force_style='{st}'"
    subprocess.run(["ffmpeg", "-y", "-i", raw, "-i", mp3, "-t", f"{adur:.2f}", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", out], check=True)
    print(f"¡Listo en HD: {out}!")

if __name__ == "__main__":
    main()
