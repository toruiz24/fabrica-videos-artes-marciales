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
    narration: str = Field(description="Locución didáctica en español de Argentina (voseo natural de instructor, claro y técnico). Entre 60 y 90 palabras por escena.")
    visual_type: str = Field(description="Tipo: 'biomechanics_diagram', 'tactical_sequence', 'guard_comparison', o 'key_principle'")
    headline: str = Field(description="Título corto en pantalla (máx 6 palabras)")
    html_animation_body: str = Field(description="Código HTML/SVG interno para el escenario 1920x1080 con clases 'anim-step step-1', 'step-2', 'step-3', 'step-4', 'svg-draw', 'sequence-grid', 'sequence-card' y 'principle-box'.")

class VideoScript(BaseModel):
    module_title: str
    scenes: list[Scene]

SYSTEM_PROMPT = """
Eres un maestro instructor de artes marciales y especialista en biomecánica aplicada, creando clases visuales estilo análisis táctico profesional.
Transforma el texto denso de un capítulo en un guion audiovisual de 8 a 12 minutos (genera entre 16 y 22 escenas).

REGLAS ESTRICTAS:
1. PROHIBIDO leer o resumir el texto de forma plana. Condensa la teoría mediante DEMOSTRACIONES VISUALES ANIMADAS: diagramas cenitales (vista desde arriba de pies/guardias), vectores de fuerza (flechas SVG que muestran rotación de cadera, centro de gravedad o trayectoria del golpe), y secuencias tácticas paso a paso.
2. Usa español de Argentina natural y profesional en 'narration': voseo claro ("Fijate cómo rota la cadera...", "Si desplazás el pie de apoyo...", "Observá la línea central...").
3. En 'html_animation_body', genera HTML limpio y SVG inline sobre fondo oscuro (#090d16):
   - Colores de alto contraste: Dorado/Ámbar (#f59e0b) para atacante/acción, Cian (#38bdf8) para defensor/estructura, Rojo (#ef4444) para puntos de impacto/vulnerabilidad, Verde (#10b981) para postura correcta.
   - Tipografías grandes y legibles (28px a 42px).
4. Sincronización paso a paso dentro de cada escena:
   - class="anim-step step-1" (aparece al 5%)
   - class="anim-step step-2" (aparece al 30%)
   - class="anim-step step-3" (aparece al 55%)
   - class="anim-step step-4" (aparece al 78%)
   - En líneas y flechas SVG (<path>, <line>, <circle>), usa class="svg-draw" para que se tracen solas.
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
            model="gemini-2.5-flash",
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
