#!/usr/bin/env python
# Auto-generated from 01_pdf_to_images.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os
from pathlib import Path
from dotenv import load_dotenv
from pdf2image import convert_from_path
from PIL import Image
import utils_cc as U

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present
Image.MAX_IMAGE_PIXELS = 1_000_000_000  # avoid decompression-bomb error

SEPARATOR = os.getenv('SEPARATOR_WORD', '@@@')
DPI = int(os.getenv('PDF_IMAGE_DPI', '200'))

# Add a local poppler/bin to PATH if present
poppler_dir = Path('../poppler/bin')
if poppler_dir.exists():
    os.environ['PATH'] += os.pathsep + str(poppler_dir.resolve())

PDF_DIR = Path('./pdf')
IMAGE_DIR = Path('./image')
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

for pdf_path in U.iter_files(PDF_DIR, ['.pdf']):
    stem = pdf_path.stem
    pages = convert_from_path(str(pdf_path), dpi=DPI)
    for i, page in enumerate(pages, start=1):
        out_name = U.page_image_name(stem, i, SEPARATOR, ext='jpeg')
        page.save(str(IMAGE_DIR / out_name), 'JPEG')
    print(f'{pdf_path.name}: {len(pages)} pages')

print('\nimages:', len(list(IMAGE_DIR.glob('*.jpeg'))))
