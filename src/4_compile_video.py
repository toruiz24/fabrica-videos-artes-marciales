import os
import json
import glob
import subprocess

def concat_clips(scene_files, concat_txt, output_mp4):
    if not scene_files:
        return
    with open(concat_txt, "w", encoding="utf-8") as f:
        for sf in scene_files:
            f.write(f"file '{os.path.abspath(sf)}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_txt, "-c", "copy", output_mp4
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def compile_modules():
    os.makedirs("output", exist_ok=True)
    module_dirs = sorted(glob.glob("build/renders/cap_*"))

    for mod_dir in module_dirs:
        mod_id = os.path.basename(mod_dir)
        slug = mod_id
        script_path = f"build/scripts/{mod_id}_script.json"
        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("slug"):
                    slug = f"{mod_id}_{data['slug']}"

        # 1. Compilar versión Pixabay (Videos Reales)
        pixabay_files = sorted(glob.glob(f"{mod_dir}/scene_*_pixabay.mp4"))
        if pixabay_files:
            out_pixabay = f"output/{slug}_1_PIXABAY.mp4"
            print(f"Compilando versión Pixabay: {out_pixabay} ({len(pixabay_files)} escenas)...")
            concat_clips(pixabay_files, f"{mod_dir}/concat_pixabay.txt", out_pixabay)

        # 2. Compilar versión IA (Escenas Cinematográficas)
        ia_files = sorted(glob.glob(f"{mod_dir}/scene_*_ia.mp4"))
        if ia_files:
            out_ia = f"output/{slug}_2_IA.mp4"
            print(f"Compilando versión IA: {out_ia} ({len(ia_files)} escenas)...")
            concat_clips(ia_files, f"{mod_dir}/concat_ia.txt", out_ia)

    print("¡Ambas versiones de cada capítulo han sido compiladas!")

if __name__ == "__main__":
    compile_modules()
