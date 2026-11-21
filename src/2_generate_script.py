import os
import json
import glob
import time
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
Devolvé ÚNICAMENTE un objeto JSON válido (sin bloques de markdown ```json) con exactamente esta estructura:
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

def clean_json_text(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text

def try_gemini(prompt):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    client = genai.Client(api_key=api_key)
    for model_name in ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"]:
        try:
            print(f"  -> [Google Gemini] Probando {model_name}...")
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
            print(f"  [Salto Gemini] {model_name} no disponible: {str(e)[:90]}...")
    return None

def try_openai_compatible(provider_name, base_url, api_key, models, prompt, max_chars=24000):
    if not api_key:
        return None
    client = OpenAI(base_url=base_url, api_key=api_key)
    for model_name in models:
        for attempt in range(1, 3):
            try:
                print(f"  -> [{provider_name}] Probando {model_name} (intento {attempt})...")
                res = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt[:max_chars]},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.4,
                    max_tokens=8000,
                )
                raw_json = clean_json_text(res.choices[0].message.content)
                validated = VideoScript.model_validate_json(raw_json)
                return validated.model_dump_json(indent=2)
            except Exception as e:
                err = str(e)
                print(f"  [Salto {provider_name}] {model_name}: {err[:100]}...")
                if "429" in err or "401" in err or "403" in err or "404" in err or "413" in err:
                    break
                time.sleep(8)
    return None

def generate_with_any_ai(prompt):
    # 1. Intentar OpenRouter primero
    result = try_openai_compatible(
        provider_name="OpenRouter",
        base_url="https://openrouter.ai",
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        models=[
            "openrouter/free",
            "nvidia/nemotron-3.5-lightning:free",
            "nvidia/nemotron-3-ultra-550b-a55b:free",
            "google/gemma-4-31b-it:free",
        ],
        prompt=prompt,
        max_chars=24000,
    )
    if result:
        return result

    # 2. Intentar Google Gemini
    result = try_gemini(prompt)
    if result:
        return result

    # 3. Intentar GitHub Models (integrado gratis en Actions)
    result = try_openai_compatible(
        provider_name="GitHub Models",
        base_url="https://github.ai",
        api_key=os.environ.get("GITHUB_TOKEN"),
        models=["openai/gpt-4o-mini", "meta/Llama-3.3-70B-Instruct", "deepseek/DeepSeek-V3"],
        prompt=prompt,
        max_chars=14000,
    )
    if result:
        return result

    raise RuntimeError("Ningún proveedor de IA pudo generar el guion. Revisá tus claves o límites diarios.")

def generate_scripts():
    os.makedirs("build/scripts", exist_ok=True)
    chapter_files = sorted(glob.glob("build/chapters/*.json"))

    for filepath in chapter_files:
        with open(filepath, "r", encoding="utf-8") as f:
            chapter = json.load(f)

        out_path = f"build/scripts/{chapter['id']}_script.json"
        if os.path.exists(out_path) and os.path.getsize(out_path) > 100:
            print(f"Saltando (ya generado previamente): {chapter['title']}")
            continue

        print(f"Generando análisis visual marcial para: {chapter['title']}...")
        prompt = f"Título del Módulo: {chapter['title']}\n\nContenido técnico a transformar en demostración visual:\n{chapter['content']}"

        json_text = generate_with_any_ai(prompt)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_text)

        print(f"  -> Guion guardado: {out_path}")
        time.sleep(6)

if __name__ == "__main__":
    generate_scripts()
