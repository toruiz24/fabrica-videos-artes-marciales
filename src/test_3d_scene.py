import os
import glob
import asyncio
import subprocess
from playwright.async_api import async_playwright

VOICE = "es-AR-TomasNeural"
NARRATION = (
    "Fijate bien en la mecánica de este golpe: avanzás con la palma abierta directo hacia el mentón del agresor, "
    "manteniendo el tronco completamente bloqueado a cero grados, sin telegrafiar el movimiento ni perder tu centro de gravedad. "
    "Observá ahora la repetición en cámara lenta desde el perfil."
)

def get_audio_duration(mp3_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(res.stdout)

async def run_test():
    os.makedirs("build/test_3d/frames", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    mp3_path = "build/test_3d/audio.mp3"
    srt_path = "build/test_3d/subs.srt"
    final_mp4 = "output/test_palma_abierta_3d.mp4"

    # 1. Generar locución argentina y subtítulos
    subprocess.run([
        "edge-tts", "--voice", VOICE, "--rate=+4%",
        "--text", NARRATION,
        "--write-media", mp3_path,
        "--write-subtitles", srt_path
    ], check=True)

    duration = get_audio_duration(mp3_path) + 0.5
    fps = 30
    total_frames = int(duration * fps)
    print(f"Renderizando {total_frames} cuadros 3D ({duration:.1f}s)...")

    # 2. Capturar cuadros 3D determinísticos (mucho más rápido y fluido que grabar en tiempo real)
    html_uri = "file://" + os.path.abspath("src/mannequin_3d.html")
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader"])
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.goto(html_uri)

        for frame in range(total_frames):
            ratio = frame / max(1, total_frames - 1)
            await page.evaluate("(r) => window.renderFrame(r)", ratio)
            await page.screenshot(path=f"build/test_3d/frames/f_{frame:05d}.png")

        await browser.close()

    # 3. Compilar video MP4 final con subtítulos
    sub_style = "FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=35"
    subprocess.run([
        "ffmpeg", "-y", "-framerate", str(fps),
        "-i", "build/test_3d/frames/f_%05d.png",
        "-i", mp3_path,
        "-vf", f"subtitles={srt_path}:force_style='{sub_style}'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", final_mp4
    ], check=True)

    print(f"¡Prueba 3D completada en {final_mp4}!")

if __name__ == "__main__":
    asyncio.run(run_test())
