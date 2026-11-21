import fitz
import json
import os
import re

INPUT_PDF = "input/documento.pdf"
OUTPUT_DIR = "build/chapters"

def clean_filename(title):
    clean = re.sub(r'[^\w\s-]', '', title).strip().lower()
    return re.sub(r'[-\s]+', '_', clean)[:45] or "capitulo"

def extract_modules():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    doc = fitz.open(INPUT_PDF)
    
    full_pages = [page.get_text("text") for page in doc]
    full_text = "\n".join(full_pages)

    chapter_pattern = re.compile(
        r'(?m)^[\s\-—•]*(PR[ÓO]LOGO|INTRODUCCI[ÓO]N|CAP[ÍI]TULO\s+[0-9IVXLCDM]+[^\n]*|M[ÓO]DULO\s+[0-9IVXLCDM]+[^\n]*|EP[ÍI]LOGO[^\n]*)\s*$'
    )
    matches = list(chapter_pattern.finditer(full_text))

    modules = []
    if len(matches) >= 2:
        print(f"Detectados {len(matches)} encabezados en el texto.")
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

    if len(modules) < 2:
        modules = []
        toc = [item for item in doc.get_toc() if item[0] == 1]
        if len(toc) >= 2:
            print(f"Usando índice del PDF con {len(toc)} capítulos.")
            for i, item in enumerate(toc):
                title = str(item[1]).strip()
                start_p = max(0, int(item[2]) - 1)
                end_p = max(start_p + 1, int(toc[i + 1][2]) - 1) if i + 1 < len(toc) else len(doc)
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
