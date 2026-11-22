import os
import json
import glob
import subprocess

def compile_modules():
    os.makedirs("output", exist_ok=True)
    script_files = sorted(glob.glob("build/scripts/*_script.json"))

    for script_path in script_files:
        with open(script_path, "r", encoding="utf-8") as f:
            script = json.load(f)

        mod_id = os.path.basename(script_path).replace("_script.json", "")
        mod_dir = f"build/renders/{mod_id}"
        expected_scenes = len(script.get("scenes", []))
        ready_files = sorted(glob.glob(f"{mod_dir}/scene_[0-9][0-9][0-9].mp4"))

        if expected_scenes == 0 or len(ready_files) < expected_scenes:
            print(f"⏳ Capítulo {mod_id} en progreso ({len(ready_files)}/{expected_scenes} escenas listas). Se completará en la próxima renovación de cupo.")
            continue

        slug = f"{mod_id}_{script['slug']}" if script.get("slug") else mod_id
        out_mp4 = f"output/{slug}.mp4"
        concat_txt = f"{mod_dir}/concat.txt"

        with open(concat_txt, "w", encoding="utf-8") as f:
            for rf in ready_files:
                f.write(f"file '{os.path.abspath(rf)}'\n")

        print(f"Compilando capítulo completo: {out_mp4} ({len(ready_files)} escenas)...")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_txt, "-c", "copy", out_mp4
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("¡Revisión y compilación finalizada!")

if __name__ == "__main__":
    compile_modules()
