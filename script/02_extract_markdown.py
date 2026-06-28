#!/usr/bin/env python
# Auto-generated from 02_extract_markdown.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os
from pathlib import Path
from dotenv import load_dotenv
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.core.credentials import AzureKeyCredential
import utils_cc as U

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present

cu_endpoint = os.environ['AI_SERVICES_SUBDOMAIN_URL']
cu_key = os.getenv('AI_SERVICES_KEY')
credential = AzureKeyCredential(cu_key) if cu_key else U.get_credential()

cu_client = ContentUnderstandingClient(endpoint=cu_endpoint, credential=credential)

PDF_DIR = Path('./pdf')
MD_DIR = Path('./markdown')
MD_DIR.mkdir(parents=True, exist_ok=True)
print('CU endpoint:', cu_endpoint)

def extract_markdown(pdf_path: Path) -> str:
    with open(pdf_path, 'rb') as f:
        poller = cu_client.begin_analyze_binary(
            analyzer_id='prebuilt-documentSearch',
            binary_input=f.read(),
        )
    result = poller.result()
    # Join markdown across all returned content segments
    parts = [c.markdown for c in result.contents if getattr(c, 'markdown', None)]
    return '\n\n'.join(parts)

for pdf_path in U.iter_files(PDF_DIR, ['.pdf']):
    md_text = extract_markdown(pdf_path)
    out_path = MD_DIR / (pdf_path.stem + '.md')
    out_path.write_text(md_text, encoding='utf-8')
    print(f'{pdf_path.name}: {len(md_text)} chars -> {out_path.name}')
