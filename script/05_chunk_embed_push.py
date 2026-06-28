#!/usr/bin/env python
# Auto-generated from 05_chunk_embed_push.ipynb

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_sys.path.insert(0, _os.path.dirname(_HERE))  # import utils_cc from parent (customChunkPipeline)
_os.chdir(_os.path.dirname(_HERE))       # run as if from customChunkPipeline/

import os, json
from pathlib import Path
from dotenv import load_dotenv
from azure.search.documents import SearchClient
import utils_cc as U

load_dotenv('../.env', override=True)  # ./.env (project root)
load_dotenv(override=True)  # local .env overrides if present

name_prefix = os.environ['NAME_PREFIX']
index_name = f'{name_prefix}-index'
search_endpoint = os.environ['AZURE_SEARCH_ENDPOINT']
container_name = os.environ['BLOB_CONTAINER_NAME']

embedding_deployment = os.getenv('AZURE_OPENAI_EMBEDDING_DEPLOYMENT', 'text-embedding-3-large')

# Tunable chunking parameters (override here or via .env)
CHUNK_MAX_TOKENS = int(os.getenv('CHUNK_MAX_TOKENS', '8000'))
CHUNK_OVERLAP_TOKENS = int(os.getenv('CHUNK_OVERLAP_TOKENS', '2000'))
SEPARATOR = os.getenv('SEPARATOR_WORD', '@@@')
PUSH_BATCH = 100

credential = U.get_credential()
aoai = U.get_aoai_client(credential)
blob_service = U.get_blob_service_client(credential)
search_client = SearchClient(endpoint=search_endpoint, index_name=index_name,
                             credential=U.get_search_credential(credential))

PDF_DIR = Path('./pdf')
MD_DIR = Path('./markdown')
IMAGE_DIR = Path('./image')
VERB_DIR = Path('./verbalized')
SHARD_DIR = Path('./shards')
SHARD_DIR.mkdir(parents=True, exist_ok=True)
print(f'chunk: max={CHUNK_MAX_TOKENS} overlap={CHUNK_OVERLAP_TOKENS} | index={index_name}')

def push_in_batches(records, batch=PUSH_BATCH):
    total = 0
    for i in range(0, len(records), batch):
        chunk = records[i:i + batch]
        result = search_client.upload_documents(documents=chunk)
        ok = sum(1 for r in result if r.succeeded)
        total += ok
        if ok != len(chunk):
            for r in result:
                if not r.succeeded:
                    print('  FAILED', r.key, r.error_message)
    return total

def build_text_records(stem, source_url):
    md_path = MD_DIR / f'{stem}.md'
    if not md_path.exists():
        return []
    md_text = md_path.read_text(encoding='utf-8')
    chunks = U.chunk_by_tokens(md_text, CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS)
    records = []
    for idx, chunk in enumerate(chunks):
        vector = U.generate_embeddings(chunk, embedding_deployment, aoai)
        if not vector:
            continue
        records.append({
            'uid': U.text_uid(stem, idx),
            'snippet_parent_id': U.doc_id(stem),
            'snippet': chunk,
            'blob_url': source_url,
            'snippet_vector': vector,
        })
    return records

def build_image_records(stem):
    records = []
    for verb_path in sorted(VERB_DIR.glob(f'{stem}{SEPARATOR}*.txt')):
        _, page = U.parse_page_image_name(verb_path.name, SEPARATOR)
        text = verb_path.read_text(encoding='utf-8')
        vector = U.generate_embeddings(text, embedding_deployment, aoai)
        if not vector:
            continue
        # Upload the page image and point blob_url at it
        img_name = U.page_image_name(stem, page or 0, SEPARATOR, ext='jpeg')
        img_path = IMAGE_DIR / img_name
        image_url = U.upload_file(blob_service, container_name, img_path,
                                  blob_name=img_name, content_type='image/jpeg') \
                    if img_path.exists() else ''
        records.append({
            'uid': U.image_uid(stem, page or 0),
            'image_snippet_parent_id': U.doc_id(stem),
            'snippet': text,
            'blob_url': image_url,
            'snippet_vector': vector,
        })
    return records

grand_total = 0
for pdf_path in U.iter_files(PDF_DIR, ['.pdf']):
    stem = pdf_path.stem
    print(f'\n=== {stem} ===')

    # 1) Upload source PDF once -> used as blob_url for all text chunks
    source_url = U.upload_file(blob_service, container_name, pdf_path,
                               blob_name=pdf_path.name, content_type='application/pdf')

    # 2) Build records (text chunks + verbalized images)
    records = build_text_records(stem, source_url)
    n_text = len(records)
    records += build_image_records(stem)
    n_image = len(records) - n_text
    print(f'  text chunks: {n_text} | image rows: {n_image}')

    if not records:
        continue

    # 3) Persist this document's shard (resumable, avoids one huge file)
    shard_path = SHARD_DIR / f'{stem}.jsonl'
    with open(shard_path, 'w', encoding='utf-8') as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # 4) Push this shard sequentially in batches
    pushed = push_in_batches(records)
    grand_total += pushed
    print(f'  pushed: {pushed}/{len(records)} -> shard {shard_path.name}')

print(f'\nDONE. Total documents indexed: {grand_total}')

print("docs in index:", search_client.get_document_count())

from azure.search.documents.models import VectorizableTextQuery, QueryType

query = '取引突合依頼を元に作成されるファイルはどれか？'
vq = VectorizableTextQuery(text=query, k=50, fields='snippet_vector')
results = search_client.search(
    search_text=query,
    vector_queries=[vq],
    select=['snippet', 'blob_url', 'snippet_parent_id', 'image_snippet_parent_id'],
    query_type=QueryType.SEMANTIC,
    semantic_configuration_name=os.getenv('AZURE_SEARCH_SEMANTIC_CONFIGURATION', f'{name_prefix}-semantic-configuration'),
    top=5,
)
for i, r in enumerate(results, 1):
    kind = 'image' if r.get('image_snippet_parent_id') else 'text'
    print(f"\n--- {i} [{kind}] score={r['@search.score']:.4f} reranker={r.get('@search.reranker_score')} ---")
    print('blob_url:', r.get('blob_url'))
    s = r.get('snippet', '')
    print('snippet :', (s[:300] + '...') if len(s) > 300 else s)
