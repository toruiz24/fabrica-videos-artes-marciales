import os
import json
import glob
import time
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

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
"""

def generate_scripts():
    os.makedirs("build/scripts", exist_ok=True)
    chapter_files = sorted(glob.glob("build/chapters/*.json"))

    for filepath in chapter_files:
        with open(filepath, "r", encoding="utf-8") as f:
            chapter = json.load(f)

        out_path = f"build/scripts/{chapter['id']}_script.json"
        if os.path.exists(out_path):
            continue

        print(f"Generando análisis visual marcial para: {chapter['title']}...")
        prompt = f"Título del Módulo: {chapter['title']}\n\nContenido técnico a transformar en demostración visual:\n{chapter['content'][:28000]}"

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=VideoScript,
                temperature=0.4,
            ),
        )

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(response.text)

        time.sleep(10)

if __name__ == "__main__":
    generate_scripts()
