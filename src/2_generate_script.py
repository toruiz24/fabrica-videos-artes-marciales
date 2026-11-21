import os
import json
import glob
import time
import urllib.request
from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, Field

class Scene(BaseModel):
    scene_number: int
    narration: str = Field(
        description="Narración estilo documental 100% en español rioplatense (Argentina), usando voseo natural ('fijate', 'mirá', 'desplazate', 'cubrite'). Entre 35 y 55 palabras por escena."
    )
    pixabay_query: str = Field(
        description="Búsqueda corta en inglés (2 a 3 palabras) para encontrar video real en Pixabay (ej: 'martial arts', 'boxing training', 'self defense', 'night street', 'kickboxing')."
    )
    ai_image_prompt: str = Field(
        description="Prompt detallado en inglés para generar una escena cinematográfica fotorrealista 16:9 (ej: 'cinematic documentary shot of urban self defense wrist escape technique at night, dramatic street lighting, 35mm film, photorealistic, no text')."
    )

class DocumentaryScript(BaseModel):
    module_title: str
    slug: str
    scenes: list[Scene]

SYSTEM_PROMPT = """
Sos un director y guionista argentino de documentales sobre artes marciales, biomecánica y defensa personal urbana.
Tu trabajo es transformar el texto completo del capítulo en un guion documental inmersivo de 8 a 12 minutos dividido en 24 a 32 escenas cortas y dinámicas (cada escena dura entre 12 y 20 segundos).

REGLAS IDIOMÁTICAS (ESPAÑOL RIOPLATENSE ESTRICTO):
1. Toda la narración ('narration') debe estar en español rioplatense natural (Argentina), con voseo auténtico y tono de documental serio y atrapante ("Fijate lo que pasa cuando...", "En la calle no hay árbitro...", "Si te quedás estático en esa distancia...").
2. Desarrollá todos los conceptos técnicos, tácticos y ejemplos reales del capítulo sin recortar ideas importantes.

REGLAS VISUALES (PARA AMBAS VERSIONES EN PARALELO):
1. Para CADA escena tenés que completar tanto 'pixabay_query' (para la versión con videos reales) como 'ai_image_prompt' (para la versión 100% ilustrada por IA).
2. En 'pixabay_query', usá términos simples en inglés que devuelvan buenos videos de acción, combate, entrenamiento o ciudad nocturna en Pixabay.
3. En 'ai_image_prompt', describí una fotografía cinematográfica realista 16:9 (sin texto ni letras en la imagen) que ilustre exactamente la situación o técnica que se está narrando.

FORMATO DE SALIDA (JSON PURO):
Devolvé ÚNICAMENTE un objeto JSON válido (sin ```json) con esta estructura exacta:
{
  "module_title": "Título del capítulo",
  "slug": "slug_del_capitulo",
  "scenes": [
    {
      "scene_number": 1,
      "narration": "...",
      "pixabay_query": "martial arts",
      "ai_image_prompt": "..."
    }
  ]
}
"""

def extract_json_object(text):
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

def get_openrouter_free_models():
    models = ["openrouter/free"]
    try:
        req = urllib.request.Request("https://openrouter.ai", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("data", []):
                mid = m.get("id", "")
                if mid.endswith(":free") and m.get("context_length", 0) >= 16000:
                    models.append(mid)
    except Exception:
        pass
    return models[:8]

def try_openrouter(prompt):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    client = OpenAI(
        base_url="https://openrouter.ai",
        api_key=api_key,
        default_headers={"HTTP-Referer": "https://github.com", "X-Title": "FabricaDocumental"}
    )
    for model_name in get_openrouter_free_models():
        try:
            print(f"  -> [OpenRouter] Probando {model_name}...")
            res = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt[:26000]},
                ],
                temperature=0.4,
                max_tokens=8000,
            )
            content = res.choices.message.content
            if not content:
                continue
            validated = DocumentaryScript.model_validate_json(extract_json_object(content))
            return validated.model_dump_json(indent=2)
        except Exception as e:
            print(f"  [Salto OpenRouter] {model_name}: {str(e)[:95]}...")
            time.sleep(3)
    return None

def try_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    client = genai.Client(api_key=api_key)
    for model_name in ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite"]:
        for attempt in range(1, 4):
            try:
                print(f"  -> [Google Gemini] Probando {model_name} (intento {attempt}/3)...")
                res = client.models.generate_content(
                    model=model_name,
                    contents=prompt[:30000],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=DocumentaryScript,
                        temperature=0.4,
                    ),
                )
                DocumentaryScript.model_validate_json(res.text)
                return res.text
            except Exception as e:
                err = str(e)
                print(f"  [Salto Gemini] {model_name}: {err[:95]}...")
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "404" in err:
                    break
                time.sleep(10 * attempt)
    return None

def generate_scripts():
    os.makedirs("build/scripts", exist_ok=True)
    chapter_files = sorted(glob.glob("build/chapters/*.json"))

    for filepath in chapter_files:
        with open(filepath, "r", encoding="utf-8") as f:
            chapter = json.load(f)

        out_path = f"build/scripts/{chapter['id']}_script.json"
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            print(f"Saltando (ya en caché): {chapter['title']}")
            continue

        print(f"Creando guion documental dual para: {chapter['title']}...")
        prompt = (
            f"Título del Capítulo: {chapter['title']}\n"
            f"Slug sugerido: {chapter['slug']}\n\n"
            f"Texto completo del capítulo a convertir en documental:\n{chapter['content']}"
        )

        json_text = try_openrouter(prompt) or try_gemini(prompt)
        if not json_text:
            raise RuntimeError("No se pudo generar el guion con ningún proveedor disponible.")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_text)

        print(f"  -> Guion documental listo: {out_path}")
        time.sleep(4)

if __name__ == "__main__":
    generate_scripts()
