import os
import glob
import subprocess

def compile_modules():
    os.makedirs("output", exist_ok=True)
    module_dirs = sorted(glob.glob("build/renders/mod_*"))

    for mod_dir in module_dirs:
        mod_id = os.path.basename(mod_dir)
        scene_files = sorted(glob.glob(f"{mod_dir}/scene_*.mp4"))
        if not scene_files:
            continue

        concat_txt = f"{mod_dir}/concat_list.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for sf in scene_files:
                f.write(f"file '{os.path.abspath(sf)}'\n")

        final_mp4 = f"output/{mod_id}_clase_completa.mp4"
        print(f"Compilando video final: {final_mp4} ({len(scene_files)} escenas)...")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_txt, "-c", "copy", final_mp4
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("¡Todos los módulos han sido compilados exitosamente!")

if __name__ == "__main__":
    compile_modules()
