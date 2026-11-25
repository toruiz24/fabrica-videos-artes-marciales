import os
import re
import json
import glob
import subprocess

RENDERS_DIR = "build/renders"
CHAPTERS_DIR = "build/chapters"
OUTPUT_DIR = "output"

def clean_text(txt):
    txt = re.sub(r'[^\w\sáéíóúÁÉÍÓÚñÑüÜ\-\.\,\(\)\/]', '', txt)
    return txt.replace(":", " -").replace("'", "").strip()

def create_credits_clip(mod_dir, out_credits_mp4):
    credit_files = sorted(glob.glob(f"{mod_dir}/scene_*_credit.json"))
    seen = {}
    for cf in credit_files:
        try:
            with open(cf, "r", encoding="utf-8") as f:
                data = json.load(f)
                uploader = data.get("uploader", "").strip()
                title = data.get("title", "").strip()
                if uploader and uploader not in seen:
                    seen[uploader] = title
        except Exception:
            pass

    lines = ["CREDITOS Y FUENTES AUDIOVISUALES (YOUTUBE)", ""]
    if seen:
        for up, tit in list(seen.items())[:10]:
            entry = clean_text(f"- Canal: {up} | {tit}")[:82]
            lines.append(entry)
    else:
        lines.append("- Material de archivo y demostraciones de entrenamiento en HD")

    filters = ["color=c=#070b14:s=1920x1080:d=5:r=30"]
    y_pos = 160
    for idx, line in enumerate(lines):
        if not line:
            y_pos += 30
            continue
        size = 34 if idx == 0 else 22
        color = "#f59e0b" if idx == 0 else "white"
        filters.append(
            f"drawtext=font='DejaVu Sans':text='{line}':fontcolor={color}:fontsize={size}:x=120:y={y_pos}"
        )
        y_pos += 52

    vf = ",".join(filters)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", vf,
        "-t", "5",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        out_credits_mp4
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def compile_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    mod_dirs = sorted(glob.glob(f"{RENDERS_DIR}/*"))

    for mod_dir in mod_dirs:
        if not os.path.isdir(mod_dir):
            continue

        mod_id = os.path.basename(mod_dir)
        scenes = sorted(glob.glob(f"{mod_dir}/scene_[0-9][0-9][0-9]_yt.mp4"))
        if not scenes:
            print(f"Sin escenas listas para {mod_id}, saltando...")
            continue

        credits_mp4 = os.path.join(mod_dir, "credits_end.mp4")
        create_credits_clip(mod_dir, credits_mp4)
        all_clips = scenes + [credits_mp4]

        slug = mod_id
        chap_json = os.path.join(CHAPTERS_DIR, f"{mod_id}.json")
        if os.path.exists(chap_json):
            with open(chap_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                slug = f"{mod_id}_{data.get('slug', '')}".rstrip("_")

        out_mp4 = os.path.join(OUTPUT_DIR, f"{slug}.mp4")
        print(f"Compilando {out_mp4} ({len(scenes)} escenas + créditos)...")

        inputs = []
        filter_parts = []
        concat_inputs = ""

        for idx, clip_path in enumerate(all_clips):
            inputs.extend(["-i", clip_path])
            filter_parts.append(
                f"[{idx}:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{idx}];"
                f"[{idx}:a]aresample=44100:async=1,aformat=channel_layouts=stereo[a{idx}];"
            )
            concat_inputs += f"[v{idx}][a{idx}]"

        filter_complex = "".join(filter_parts) + f"{concat_inputs}concat=n={len(all_clips)}:v=1:a=1[outv][outa]"

        cmd = [
            "ffmpeg", "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            out_mp4
        ]

        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"  -> Listo: {out_mp4}")

if __name__ == "__main__":
    compile_all()
