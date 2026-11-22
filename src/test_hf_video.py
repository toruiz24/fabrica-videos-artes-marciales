import os
import subprocess
from huggingface_hub import InferenceClient

HF_TOKEN = os.environ["HF_TOKEN"]
VOICE = "es-AR-TomasNeural"

NARRATION = (
    "Fijate bien en este golpe: lanzás la palma abierta directo hacia el mentón del agresor, "
    "manteniendo el tronco completamente bloqueado a cero grados, sin rotar los hombros."
)

VIDEO_PROMPT = (
    "Realistic martial arts instructional video, side profile medium shot of a self defense instructor "
    "striking an attacker's chin with an open palm heel strike, keeping his torso and shoulders completely straight "
    "and locked without twisting, crisp contact, realistic gym lighting, 4k photorealistic, smooth natural motion"
)

MODELS = [
    "Wan-AI/Wan2.1-T2V-1.3B",
    "Lightricks/LTX-Video",
    "Wan-AI/Wan2.1-T2V-14B",
]

def get_duration(path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", path]
    return float(subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout)

def main():
    os.makedirs("build/test_hf", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    raw_vid = "build/test_hf/raw_ai.mp4"
    mp3_path = "build/test_hf/voice.mp3"
    srt_path = "build/test_hf/subs.srt"
    final_mp4 = "output/test_palma_ia_real.mp4"

    # 1. Generar voz argentina y subtítulos
    subprocess.run([
        "edge-tts", "--voice", VOICE, "--rate=+3%",
        "--text", NARRATION,
        "--write-media", mp3_path,
        "--write-subtitles", srt_path
    ], check=True)
    audio_dur = get_duration(mp3_path) + 0.4

    # 2. Generar clip con IA en modo ahorro (1.3B / LTX)
    client = InferenceClient(token=HF_TOKEN)
    video_bytes = None
    for model_id in MODELS:
        try:
            print(f"Generando clip con modelo: {model_id}...")
            video_bytes = client.text_to_video(
                VIDEO_PROMPT,
                model=model_id,
                negative_prompt="blurry, distorted hands, extra fingers, slow motion, cartoon, 3d render, text, watermark"
            )
            if video_bytes and len(video_bytes) > 50000:
                print(f"  -> Clip generado con éxito usando {model_id}")
                break
        except Exception as e:
            print(f"  [Salto] {model_id}: {str(e)[:120]}")

    if not video_bytes:
        raise RuntimeError("No se pudo generar el clip con ninguno de los modelos.")

    with open(raw_vid, "wb") as f:
        f.write(video_bytes)

    # 3. Escalar a Full HD (1920x1080), ajustar velocidad didáctica y pegar subtítulos
    raw_dur = get_duration(raw_vid)
    speed_factor = max(1.0, audio_dur / max(0.5, raw_dur))
    sub_style = "FontName=DejaVu Sans,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=38"
    vf = f"setpts={speed_factor:.2f}*PTS,scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,subtitles={srt_path}:force_style='{sub_style}'"

    subprocess.run([
        "ffmpeg", "-y", "-i", raw_vid, "-i", mp3_path,
        "-t", f"{audio_dur:.2f}", "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-shortest", final_mp4
    ], check=True)

    print(f"¡Video listo en {final_mp4}!")

if __name__ == "__main__":
    main()
