import fitz
import json
import os
import re

INPUT_PDF = "input/documento.pdf"
OUTPUT_DIR = "build/chapters"

def clean_filename(title):
    clean = re.sub(r'[^\w\s-]', '', title).strip().lower()
    return re.sub(r'[-\s]+', '_', clean)[:45]

def extract_modules():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    doc = fitz.open(INPUT_PDF)
    
    full_pages = [page.get_text("text") for page in doc]
    full_text = "\n".join(full_pages)

    chapter_pattern = re.compile(
        r'(?m)^(?:\s*)(PRÓLOGO|INTRODUCCIÓN|CAP[ÍI]TULO\s+\d+[^\n]*|M[ÓO]DULO\s+\d+[^\n]*|EP[ÍI]LOGO[^\n]*)\s*$',
        re.IGNORECASE
    )
    matches = list(chapter_pattern.finditer(full_text))

    modules = []
    if len(matches) >= 2:
        print(f"Estructura detectada con {len(matches)} secciones reales.")
        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start_pos = match.start()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
            content = full_text[start_pos:end_pos].strip()

            if len(content) > 800:
                idx = len(modules) + 1
                modules.append({
                    "id": f"cap_{idx:02d}",
                    "slug": clean_filename(title),
                    "title": title,
                    "content": content
                })
    else:
        toc = [item for item in doc.get_toc() if item[0] == 1]
        if len(toc) >= 2:
            for i, item in enumerate(toc):
                title = item[1].strip()
                start_p = item[2] - 1
                end_p = toc[i + 1][2] - 1 if i + 1 < len(toc) else len(doc)
                content = "\n".join(full_pages[start_p:end_p]).strip()
                if len(content) > 800:
                    idx = len(modules) + 1
                    modules.append({
                        "id": f"cap_{idx:02d}",
                        "slug": clean_filename(title),
                        "title": title,
                        "content": content
                    })

    for mod in modules:
        out_file = os.path.join(OUTPUT_DIR, f"{mod['id']}.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(mod, f, ensure_ascii=False, indent=2)
        print(f"  -> {mod['id']}: {mod['title']} ({len(mod['content'])} caracteres)")

if __name__ == "__main__":
    extract_modules()
