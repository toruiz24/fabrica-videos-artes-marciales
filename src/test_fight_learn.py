import os
import re
import asyncio
import subprocess
from huggingface_hub import HfApi, hf_hub_download
from playwright.async_api import async_playwright

VOICE = "es-AR-TomasNeural"
NARRATION = (
    "Observá la mecánica exacta del golpe directo con paso adelante. "
    "El impulso nace desde el apoyo trasero, avanza en línea recta hacia el frente sin bajar la guardia y recoge rápido. "
    "Mirá ahora la repetición en cámara lenta para apreciar la transferencia de peso."
)

def has_real_audio(mp3_path):
    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 2000:
        return False
    cmd = ["ffmpeg", "-i", mp3_path, "-af", "volumedetect", "-f", "null", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    m = re.search(r"max_volume:\s*([-\d\.]+)\s*dB", res.stdout)
    return bool(m and float(m.group(1)) > -45.0)

def generate_verified_tts(text, out_mp3, out_srt):
    for attempt in range(1, 6):
        subprocess.run([
            "edge-tts", "--voice", VOICE, "--rate=+4%",
            "--text", text,
            "--write-media", out_mp3,
            "--write-subtitles", out_srt
        ], check=True)
        if has_real_audio(out_mp3) and os.path.exists(out_srt):
            return
    raise RuntimeError("No se pudo generar voz con volumen válido.")

def download_exact_strike_mocap(out_glb):
    api = HfApi()
    files = api.list_repo_files("codepawl/cmu-mocap-glb", repo_type="dataset")
    glb_files = sorted([f for f in files if f.lower().endswith(".glb")])

    # 135_02 y 135_03 = Oiduki (golpe recto frontal con paso); 13_17 / 14_01 = golpes de boxeo
    preferred = ["135_02", "135_03", "13_17", "14_01"]
    target = None
    for code in preferred:
        target = next((f for f in glb_files if code in f), None)
        if target:
            break
    if not target:
        target = glb_files[0]

    print(f"Descargando golpe exacto MoCap: {target}")
    local = hf_hub_download(repo_id="codepawl/cmu-mocap-glb", filename=target, repo_type="dataset")
    with open(local, "rb") as src, open(out_glb, "wb") as dst:
        dst.write(src.read())

async def run_pilot():
    os.makedirs("build/pilot_fl/frames", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    mp3_path = "build/pilot_fl/voice.mp3"
    srt_path = "build/pilot_fl/subs.srt"
    glb_path = "src/mocap_action.glb"
    out_mp4 = "output/test_fight_learn.mp4"

    download_exact_strike_mocap(glb_path)
    generate_verified_tts(NARRATION, mp3_path, srt_path)

    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path]
    duration = float(subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout) + 0.5
    fps = 30
    total_frames = int(duration * fps)
    print(f"Renderizando {total_frames} cuadros 3D MoCap ({duration:.1f}s)...")

    html_uri = "file://" + os.path.abspath("src/fight_learn_3d.html")
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=[
            "--enable-webgl", "--ignore-gpu-blocklist",
            "--use-gl=angle", "--use-angle=swiftshader",
            "--enable-unsafe-swiftshader", "--allow-file-access-from-files"
        ])
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(html_uri)
        await page.wait_for_function("window.sceneReady === true", timeout=30000)

        for frame in range(total_frames):
            ratio = frame / max(1, total_frames - 1)
            await page.evaluate("(r) => window.renderFrame(r)", ratio)
            await page.screenshot(path=f"build/pilot_fl/frames/f_{frame:05d}.png")

        await browser.close()

    sub_style = "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", "build/pilot_fl/frames/f_%05d.png",
        "-i", mp3_path,
        "-vf", f"subtitles={srt_path}:force_style='{sub_style}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", out_mp4
    ], check=True)
    print(f"¡Prueba Fight Learn ajustada lista en {out_mp4}!")

if __name__ == "__main__":
    asyncio.run(run_pilot())
