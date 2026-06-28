#!/usr/bin/env python
# Auto-generated from 03_verbalize_images.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os, base64
from pathlib import Path
from dotenv import load_dotenv
import utils_cc as U

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present

SEPARATOR = os.getenv('SEPARATOR_WORD', '@@@')
CHAT_DEPLOYMENT = os.environ['CHAT_DEPLOYMENT']

credential = U.get_credential()
aoai = U.get_aoai_client(credential)

IMAGE_DIR = Path('./image')
VERB_DIR = Path('./verbalized')
VERB_DIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = (
    "You are tasked with verbalizing diagrams, flowcharts, architecture diagrams, tables, and structured figures embedded in business documents. Describe the visual content so that a search system can later retrieve information about processes, data flows, system interactions, layouts, labels, table fields, and relationships. Focus on information that is visually represented in the image. Identify the diagram title or section title if visible. Then describe the diagram in Japanese using a structured and precise style. When the image is a flowchart, system diagram, or architecture diagram, extract the main areas, lanes, systems, organizations, or actors and their relative positions, the processing flow in reading order from left to right and top to bottom unless arrows indicate a different order, arrows, connectors, interfaces, protocols, labels, direction of data or operation flow, important boxes, steps, databases, files, screens, external systems, legends, colors, line styles, numbered markers, conditions, notes, exceptions, batch processing, real-time processing, and manual operations if shown. When the image contains tables or specifications, extract table titles, column headers, row labels, field names, digit positions, codes, values, conditions, notes, differences between table sections, and any highlighted, colored, underlined, or emphasized values. Do not invent information that is not visible. If text is unreadable, state that it is unreadable. Preserve important business terms, system names, code values, numbers, and Japanese labels exactly as much as possible. The output must be written in Japanese."
)

def verbalize_image(image_path: Path) -> str:
    b64 = base64.b64encode(image_path.read_bytes()).decode('utf-8')
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': [
            {'type': 'text', 'text': 'Please describe this image.'},
            {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{b64}'}},
        ]},
    ]
    resp = aoai.chat.completions.create(model=CHAT_DEPLOYMENT, messages=messages)
    return resp.choices[0].message.content or ''

def build_header(doc_filename: str, page_number, verbalized: str) -> str:
    return (
        f'Title: \n{doc_filename}\n'
        f'Page: \n{page_number}\n'
        f'Verbalized text: \n{verbalized}'
    )

for image_path in U.iter_files(IMAGE_DIR, ['.jpeg', '.jpg', '.png']):
    stem, page = U.parse_page_image_name(image_path.name, SEPARATOR)
    doc_filename = f'{stem}.pdf'  # source document name
    verbalized = verbalize_image(image_path)
    text = build_header(doc_filename, page, verbalized)
    out_name = f'{stem}{SEPARATOR}{(page or 0):02d}.txt'
    (VERB_DIR / out_name).write_text(text, encoding='utf-8')
    print(f'{image_path.name}: {len(verbalized)} chars -> {out_name}')

# Resume: skip images whose verbalized output already exists (non-empty)
# Run CELL 1 (imports/clients) and CELL 2 (verbalize_image / build_header) first, then this cell.
remaining = []
for image_path in U.iter_files(IMAGE_DIR, ['.jpeg', '.jpg', '.png']):
    stem, page = U.parse_page_image_name(image_path.name, SEPARATOR)
    out_name = f'{stem}{SEPARATOR}{(page or 0):02d}.txt'
    out_path = VERB_DIR / out_name
    if out_path.exists() and out_path.stat().st_size > 0:
        continue
    remaining.append((image_path, stem, page, out_name))

print(f'remaining to verbalize: {len(remaining)}')
for image_path, stem, page, out_name in remaining:
    doc_filename = f'{stem}.pdf'  # source document name
    verbalized = verbalize_image(image_path)
    text = build_header(doc_filename, page, verbalized)
    (VERB_DIR / out_name).write_text(text, encoding='utf-8')
    print(f'{image_path.name}: {len(verbalized)} chars -> {out_name}')
print('DONE (resume)')
