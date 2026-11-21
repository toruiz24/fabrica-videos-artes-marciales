import fitz
import json
import os

INPUT_PDF = "input/documento.pdf"
OUTPUT_DIR = "build/chapters"

def extract_modules():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    doc = fitz.open(INPUT_PDF)
    toc = doc.get_toc()
    modules = []
    level_1_toc = [item for item in toc if item[0] == 1]

    if len(level_1_toc) >= 2:
        print(f"Índice detectado con {len(level_1_toc)} capítulos.")
        for i, item in enumerate(level_1_toc):
            title = item[1]
            start_page = item[2] - 1
            end_page = level_1_toc[i+1][2] - 1 if i + 1 < len(level_1_toc) else len(doc)
            text = "".join(doc[p].get_text("text") + "\n" for p in range(start_page, end_page))
            if len(text.strip()) > 500:
                modules.append({"id": f"mod_{i+1:02d}", "title": title, "content": text})
    else:
        print("Sin índice claro. Dividiendo por bloques de lectura...")
        chunk_size = 14000
        current_text = ""
        mod_idx = 1
        for page in doc:
            current_text += page.get_text("text") + "\n"
            if len(current_text) >= chunk_size:
                modules.append({"id": f"mod_{mod_idx:02d}", "title": f"Módulo {mod_idx}", "content": current_text})
                current_text = ""
                mod_idx += 1
        if len(current_text.strip()) > 500:
            modules.append({"id": f"mod_{mod_idx:02d}", "title": f"Módulo {mod_idx}", "content": current_text})

    for mod in modules:
        with open(os.path.join(OUTPUT_DIR, f"{mod['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(mod, f, ensure_ascii=False, indent=2)

    print(f"Total de módulos generados: {len(modules)}")

if __name__ == "__main__":
    extract_modules()
