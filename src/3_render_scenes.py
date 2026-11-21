import os
import json
import glob
import asyncio
import subprocess
import edge_tts
from playwright.async_api import async_playwright

VOICE = "es-AR-TomasNeural"

def get_audio_duration(mp3_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", mp3_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return float(result.stdout)

async def generate_tts(text, out_mp3):
    communicate = edge_tts.Communicate(text, VOICE, rate="+6%")
    await communicate.save(out_mp3)

async def render_all():
    script_files = sorted(glob.glob("build/scripts/*_script.json"))
    template_uri = "file://" + os.path.abspath("src/template.html")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for script_path in script_files:
            with open(script_path, "r", encoding="utf-8") as f:
                script = json.load(f)

            mod_id = os.path.basename(script_path).replace("_script.json", "")
            mod_dir = f"build/renders/{mod_id}"
            os.makedirs(mod_dir, exist_ok=True)
            print(f"Renderizando módulo: {script['module_title']}")

            for scene in script["scenes"]:
                s_num = scene["scene_number"]
                mp3_path = f"{mod_dir}/scene_{s_num:03d}.mp3"
                webm_dir = f"{mod_dir}/temp_vid_{s_num:03d}"
                final_scene_mp4 = f"{mod_dir}/scene_{s_num:03d}.mp4"

                if os.path.exists(final_scene_mp4):
                    continue

                await generate_tts(scene["narration"], mp3_path)
                duration = get_audio_duration(mp3_path) + 0.6

                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    record_video_dir=webm_dir,
                    record_video_size={"width": 1920, "height": 1080}
                )
                page = await context.new_page()
                await page.goto(template_uri)
                await page.evaluate(
                    "([m, h, b]) => window.loadScene(m, h, b)",
                    [script["module_title"], scene["headline"], scene["html_animation_body"]]
                )

                steps = int(duration / 0.25)
                for step in range(steps + 1):
                    ratio = min(1.0, step / max(1, steps))
                    await page.evaluate("(r) => window.setProgress(r)", ratio)
                    await asyncio.sleep(0.25)

                video_path = await page.video.path()
                await context.close()

                subprocess.run([
                    "ffmpeg", "-y", "-i", video_path, "-i", mp3_path,
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-shortest", final_scene_mp4
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                print(f"  -> Escena {s_num:02d} lista ({duration:.1f}s)")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(render_all())
