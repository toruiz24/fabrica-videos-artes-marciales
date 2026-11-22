import os, shutil, subprocess
from huggingface_hub import HfApi, login
from gradio_client import Client

HF_TOKEN = os.environ["HF_TOKEN"]
login(token=HF_TOKEN)

VOICE = "es-AR-TomasNeural"
NARRATION = (
    "Fijate bien en este golpe: lanzás la palma abierta directo hacia el mentón del agresor, "
    "manteniendo el tronco completamente bloqueado a cero grados, sin rotar los hombros."
)
PROMPT = (
    "Realistic martial arts instructional video, side profile medium shot of a self defense instructor "
    "striking an attacker's chin with an open palm heel strike, torso completely straight and locked "
    "without twisting, crisp contact, realistic gym lighting, photorealistic, smooth motion"
)

def get_dur(p):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", p])
    return float(out)

def find_video(res):
    if isinstance(res, str) and os.path.exists(res): return res
    if isinstance(res, dict):
        for k in ("video", "value", "path", "url"):
            v = res.get(k)
            if isinstance(v, str) and os.path.exists(v): return v
            if isinstance(v, dict) and os.path.exists(str(v.get("path", ""))): return v["path"]
    if isinstance(res, (list, tuple)):
        for x in res:
            f = find_video(x)
            if f: return f
    return None

def run_zerogpu(out_mp4):
    api = HfApi(token=HF_TOKEN)
    spaces = []
    for query in ["Wan2.2", "Wan2.1", "LTX-Video", "HunyuanVideo", "text-to-video"]:
        try:
            for s in api.list_spaces(search=query, sort="likes", limit=15):
                if s.id not in spaces and not any(w in s.id.lower() for w in ("whisper", "image-to", "i2v", "audio")):
                    spaces.append(s.id)
        except Exception:
            pass

    for sid in spaces:
        try:
            if api.get_space_runtime(sid).stage != "RUNNING":
                continue
            print(f"Probando Space activo: {sid}...")
            c = Client(sid, verbose=False)
            named = c.view_api(return_format="dict").get("named_endpoints", {})
            for ep, info in named.items():
                if "login" in ep.lower():
                    continue
                params = info.get("parameters", [])
                prompt_param = next((p for p in params if "prompt" in p.get("parameter_name", "").lower() and "neg" not in p.get("parameter_name", "").lower()), None)
                if not prompt_param:
                    continue
                kw = {}
                for p in params:
                    n = p.get("parameter_name", "")
                    if n == prompt_param["parameter_name"]:
                        kw[n] = PROMPT
                    elif "neg" in n.lower():
                        kw[n] = "blurry, distorted hands, cartoon, 3d, text, watermark"
                    elif p.get("parameter_has_default"):
                        kw[n] = p.get("parameter_default")
                print(f"  -> Generando en {sid} ({ep})...")
                vid = find_video(c.predict(api_name=ep, **kw))
                if vid and os.path.getsize(vid) > 50000:
                    shutil.copyfile(vid, out_mp4)
                    print(f"  -> ¡Clip generado gratis en {sid}!")
                    return True
        except Exception as e:
            print(f"  [Salto] {sid}: {str(e)[:100]}")
    return False

def main():
    os.makedirs("build/test_hf", exist_ok=True)
    os.makedirs("output", exist_ok=True)
    raw, mp3, srt, out = "build/test_hf/raw.mp4", "build/test_hf/v.mp3", "build/test_hf/s.srt", "output/test_palma_ia_real.mp4"
    subprocess.run(["edge-tts", "--voice", VOICE, "--rate=+3%", "--text", NARRATION, "--write-media", mp3, "--write-subtitles", srt], check=True)
    adur = get_dur(mp3) + 0.4
    if not run_zerogpu(raw): raise RuntimeError("Ningún Space ZeroGPU con generación de video estuvo libre en este momento.")
    spd = max(1.0, adur / max(0.5, get_dur(raw)))
    st = "FontName=DejaVu Sans,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=38"
    vf = f"setpts={spd:.2f}*PTS,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt}:force_style='{st}'"
    subprocess.run(["ffmpeg", "-y", "-i", raw, "-i", mp3, "-t", f"{adur:.2f}", "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", out], check=True)
    print(f"¡Listo: {out}!")

if __name__ == "__main__":
    main()
