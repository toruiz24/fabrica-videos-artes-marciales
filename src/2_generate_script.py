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
        description="Locución didáctica 100% en español rioplatense (Argentina), usando voseo natural de instructor marcial (ej: 'fijate', 'mirá', 'desplazate', 'cubrite'). Entre 60 y 90 palabras por escena."
    )
    visual_type: str = Field(
        description="Tipo de escena: 'biomechanics_diagram', 'tactical_sequence', 'guard_comparison', o 'key_principle'"
    )
    headline: str = Field(
        description="Título corto en pantalla en español rioplatense (máx 6 palabras)"
    )
    html_animation_body: str = Field(
        description="Código HTML/SVG interno para el escenario 1920x1080 con todos los textos y etiquetas en español rioplatense. Usa las clases 'anim-step step-1', 'step-2', 'step-3', 'step-4', 'svg-draw', 'sequence-grid', 'sequence-card' y 'principle-box'."
    )

class VideoScript(BaseModel):
    module_title: str = Field(description="Título del módulo en español rioplatense")
    scenes: list[Scene]

SYSTEM_PROMPT = """
Sos un maestro instructor argentino de artes marciales, defensa personal urbana y biomecánica aplicada, creando clases visuales estilo análisis táctico profesional.
Transformá el texto denso de cada capítulo en un guion audiovisual de 8 a 12 minutos (generá entre 16 y 22 escenas).

REGLAS IDIOMÁTICAS (ESPAÑOL RIOPLATENSE ESTRICTO):
1. TODO el contenido —tanto la locución ('narration') como los títulos ('headline') y cada etiqueta o texto dentro de los gráficos ('html_animation_body')— debe estar escrito en español rioplatense natural (Argentina).
2. Usá voseo auténtico y profesional de instructor ("Fijate cómo rota la cadera", "Si desplazás el pie de apoyo", "Mantené la guardia alta", "Observá la línea central", "No te regales en esa distancia"). Prohibido usar "tú", "vosotros" o modismos de otros países.

REGLAS PEDAGÓGICAS Y VISUALES:
1. PROHIBIDO leer o resumir el texto de forma plana. Condensá la teoría mediante DEMOSTRACIONES VISUALES ANIMADAS: diagramas cenitales (vista desde arriba de pies, guardias y distancias), vectores de fuerza (flechas SVG que muestran rotación de cadera, centro de gravedad o trayectoria del golpe) y secuencias tácticas paso a paso.
2. En 'html_animation_body', generá HTML limpio y SVG inline sobre fondo oscuro (#090d16) con estética de análisis táctico:
   - Colores de alto contraste: Dorado/Ámbar (#f59e0b) para el atacante/amenaza, Cian (#38bdf8) para el defensor/estructura, Rojo (#ef4444) para puntos de impacto/vulnerabilidad, Verde (#10b981) para postura o salida segura.
   - Tipografías grandes y bien legibles (28px a 42px).
3. Sincronización paso a paso dentro de cada escena:
   - class="anim-step step-1" (Postura / Situación inicial - aparece al 5%)
   - class="anim-step step-2" (Lectura / Primer desplazamiento - aparece al 30%)
   - class="anim-step step-3" (Ejecución / Transferencia de peso - aparece al 55%)
   - class="anim-step step-4" (Resolución / Clave biomecánica - aparece al 78%)
   - En líneas y flechas SVG (<path>, <line>, <circle>), usá class="svg-draw" para que se tracen solas en pantalla.

FORMATO DE SALIDA OBLIGATORIO (JSON PURO):
Devolvé ÚNICAMENTE un objeto JSON válido (sin texto antes ni después, sin bloques ```json) con esta estructura exacta:
{
  "module_title": "Título del módulo",
  "scenes": [
    {
      "scene_number": 1,
      "narration": "...",
      "visual_type": "biomechanics_diagram",
      "headline": "...",
      "html_animation_body": "..."
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
                ctx = m.get("context_length", 0)
                if mid.endswith(":free") and ctx >= 16000:
                    models.append(mid)
    except Exception as e:
        print(f"  [Aviso] No se pudo consultar catálogo vivo de OpenRouter: {e}")
    return models[:8]

def try_openrouter(prompt):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
        default_headers={"HTTP-Referer": "https://github.com", "X-Title": "FabricaVideosEducativos"}
    )
    models = get_openrouter_free_models()
    for model_name in models:
        try:
            print(f"  -> [OpenRouter] Probando {model_name}...")
            # Sin response_format para que los endpoints gratuitos no devuelvan 404
            res = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt[:22000]},
                ],
                temperature=0.4,
                max_tokens=8000,
            )
            content = res.choices.message.content
            if not content:
                continue
            raw_json = extract_json_object(content)
            validated = VideoScript.model_validate_json(raw_json)
            return validated.model_dump_json(indent=2)
        except Exception as e:
            print(f"  [Salto OpenRouter] {model_name}: {str(e)[:110]}...")
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
                    contents=prompt[:28000],
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=VideoScript,
                        temperature=0.4,
                    ),
                )
                VideoScript.model_validate_json(res.text)
                return res.text
            except Exception as e:
                err = str(e)
                print(f"  [Salto Gemini] {model_name}: {err[:100]}...")
                if "429" in err or "RESOURCE_EXHAUSTED" in err or "404" in err:
                    break
                time.sleep(12 * attempt)
    return None

def generate_with_any_ai(prompt):
    result = try_openrouter(prompt)
    if result:
        return result

    result = try_gemini(prompt)
    if result:
        return result

    raise RuntimeError("Ni OpenRouter ni Google Gemini pudieron generar el guion en este momento.")

def generate_scripts():
    os.makedirs("build/scripts", exist_ok=True)
    chapter_files = sorted(glob.glob("build/chapters/*.json"))

    for filepath in chapter_files:
        with open(filepath, "r", encoding="utf-8") as f:
            chapter = json.load(f)

        out_path = f"build/scripts/{chapter['id']}_script.json"
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            print(f"Saltando (ya generado en caché): {chapter['title']}")
            continue

        print(f"Generando análisis visual marcial para: {chapter['title']}...")
        prompt = f"Título del Módulo: {chapter['title']}\n\nContenido técnico a transformar en demostración visual:\n{chapter['content']}"

        json_text = generate_with_any_ai(prompt)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_text)

        print(f"  -> Guion guardado: {out_path}")
        time.sleep(5)

if __name__ == "__main__":
    generate_scripts()
