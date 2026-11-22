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
        description="Narración documental 100% en español rioplatense (Argentina), con voseo natural ('fijate', 'mirá', 'desplazate', 'cubrite'). Entre 35 y 55 palabras por escena."
    )
    scene_type: str = Field(
        description="Elegí 'ai_technique' ONLY cuando la escena enseñe una ejecución física o movimiento concreto (golpe, bloqueo, agarre, postura, desplazamiento). Elegí 'broll_context' para introducción, psicología, entorno urbano, prevención o análisis teórico (máximo 7 escenas 'ai_technique' por capítulo)."
    )
    initial_pose_prompt: str = Field(
        description="Si scene_type es 'ai_technique': fotografía fotorrealista 16:9 de la POSTURA INICIAL antes de lanzar el golpe o defensa (dos personas frente a frente en guardia lista, ángulos claros, sin texto ni marcas de agua)."
    )
    motion_action_prompt: str = Field(
        description="Si scene_type es 'ai_technique': descripción física precisa del MOVIMIENTO que ocurre desde esa postura inicial (ej: 'the instructor explosively thrusts his open palm forward into the attacker chin keeping torso straight without twisting, causing head snap back')."
    )
    pixabay_query: str = Field(
        description="Búsqueda corta en inglés (2 a 3 palabras) para video real de contexto (ej: 'martial arts', 'boxing training', 'night street', 'self defense')."
    )

class DocumentaryScript(BaseModel):
    module_title: str
    slug: str
    scenes: list[Scene]

SYSTEM_PROMPT = """
Sos un director técnico y guionista argentino de documentales sobre artes marciales y defensa personal urbana.
Tu tarea es convertir el texto completo del capítulo en un guion documental estructurado en escenas cortas y dinámicas (12 a 18 segundos cada una), cubriendo todas las ideas del capítulo sin resumir de más.

REGLAS IDIOMÁTICAS (ESPAÑOL RIOPLATENSE ESTRICTO):
- Toda la narración ('narration') va en español rioplatense natural (Argentina), con voseo auténtico y tono serio de documental.

REGLAS DE DIRECCIÓN VISUAL (CUIDADO DE CUPO GPU):
1. Clasificá cada escena en 'ai_technique' o 'broll_context'.
2. Usá 'ai_technique' ÚNICAMENTE en las escenas clave donde se demuestra una mecánica física o técnica corporal concreta (entre 4 y 7 escenas por capítulo).
3. En 'initial_pose_prompt' describí SIEMPRE la postura inicial lista para actuar (nunca el golpe ya terminado), en plano medio lateral o 3/4 nítido, estilo fotografía realista 8k sin texto.
4. En 'motion_action_prompt' describí exactamente el movimiento físico que se ejecuta en el video y la reacción de impacto.
5. Para todas las demás escenas teóricas, estratégicas o de contexto urbano, usá 'broll_context' con un 'pixabay_query' simple en inglés.

FORMATO DE SALIDA (JSON PURO):
Devolvé ÚNICAMENTE un objeto JSON válido (sin ```json) con esta estructura exacta:
{
  "module_title": "Título del capítulo",
  "slug": "slug_del_capitulo",
  "scenes": [
    {
      "scene_number": 1,
      "narration": "...",
      "scene_type": "ai_technique",
      "initial_pose_prompt": "...",
      "motion_action_prompt": "...",
      "pixabay_query": "martial arts"
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
                temperature=0.35,
                max_tokens=8000,
            )
            content = res.choices[0].message.content
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
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash"]:
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
                        temperature=0.35,
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

        print(f"Creando guion documental técnico para: {chapter['title']}...")
        prompt = (
            f"Título del Capítulo: {chapter['title']}\n"
            f"Slug sugerido: {chapter['slug']}\n\n"
            f"Texto completo del capítulo:\n{chapter['content']}"
        )

        json_text = try_openrouter(prompt) or try_gemini(prompt)
        if not json_text:
            raise RuntimeError("No se pudo generar el guion con ningún proveedor disponible.")

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_text)

        print(f"  -> Guion listo: {out_path}")
        time.sleep(4)

if __name__ == "__main__":
    generate_scripts()
