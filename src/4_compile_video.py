import os
import json
import glob
import subprocess

RENDERS_DIR = "build/renders"
CHAPTERS_DIR = "build/chapters"
OUTPUT_DIR = "output"

def compile_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    mod_dirs = sorted(glob.glob(f"{RENDERS_DIR}/*"))

    for mod_dir in mod_dirs:
        if not os.path.isdir(mod_dir):
            continue

        mod_id = os.path.basename(mod_dir)
        scenes = sorted(glob.glob(f"{mod_dir}/scene_[0-9][0-9][0-9]_v5.mp4"))
        if not scenes:
            print(f"Sin escenas nuevas para {mod_id}, saltando...")
            continue

        slug = mod_id
        chap_json = os.path.join(CHAPTERS_DIR, f"{mod_id}.json")
        if os.path.exists(chap_json):
            with open(chap_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                slug = f"{mod_id}_{data.get('slug', '')}".rstrip("_")

        out_mp4 = os.path.join(OUTPUT_DIR, f"{slug}.mp4")
        print(f"Compilando {out_mp4} ({len(scenes)} escenas sincronizadas)...")

        inputs = []
        filter_parts = []
        concat_inputs = ""

        for idx, scene_path in enumerate(scenes):
            inputs.extend(["-i", scene_path])
            filter_parts.append(
                f"[{idx}:v]fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,"
                f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{idx}];"
                f"[{idx}:a]aresample=44100:async=1,aformat=channel_layouts=stereo[a{idx}];"
            )
            concat_inputs += f"[v{idx}][a{idx}]"

        filter_complex = "".join(filter_parts) + f"{concat_inputs}concat=n={len(scenes)}:v=1:a=1[outv][outa]"

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
