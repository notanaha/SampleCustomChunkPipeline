# customChunkPipeline — custom chunking for Content Understanding → AI Search (push model)

Build an Azure AI Search index (`{NAME_PREFIX}-index`) that
`SampleContentUnderstandingSkill2/101_knowledge_base.ipynb` can consume **as-is**,
**without using the AI Search Indexer / Skillset**. Instead, this pipeline does its own
pre-processing and pushes documents directly to the index.

The records are compatible with the index projection in `03_pp-skillset.rest`:

| Row type | Primary field set | `snippet` | `blob_url` |
|---|---|---|---|
| text chunk | `snippet_parent_id` | markdown chunk | source PDF URL |
| image row | `image_snippet_parent_id` | verbalized text | page image URL |

Both row types share the same `snippet` / `snippet_vector` fields, so the Knowledge Base
searches them uniformly (hybrid + semantic).

## Pipeline steps

| # | Notebook | What it does | Input → Output |
|---|---|---|---|
| 00 | `00_office_to_pdf.ipynb` | Convert Excel/PowerPoint/Word/HTML → PDF and collect PDFs | `../data/*` → `./pdf/*.pdf` |
| 01 | `01_pdf_to_images.ipynb` | Render PDF → one JPEG per page | `./pdf` → `./image` |
| 02 | `02_extract_markdown.ipynb` | Extract Markdown via Content Understanding `prebuilt-documentSearch` | `./pdf` → `./markdown` |
| 03 | `03_verbalize_images.ipynb` | Verbalize page images with GPT Vision (fixed prompt + Title/Page header) | `./image` → `./verbalized` |
| 04 | `04_create_index.ipynb` | Create `{NAME_PREFIX}-index` via SDK (101-compatible schema) | — |
| 05 | `05_chunk_embed_push.ipynb` | Token chunking + embeddings + Blob upload + **sequential shard push** | the above → AI Search + `./shards` |

> **Input data**: place your source documents (`.pdf`, `.xlsx`, `.pptx`, `.docx`, `.html`) in a `data/` folder one level
> above this directory (the notebooks read from `../data`). After copying this folder elsewhere
> for publishing, create that `../data` folder and add your files before running.
> For HTML inputs, also place any images the HTML references (SVG / PNG / JPG, same or other folder)
> at the referenced relative paths so they are embedded during PDF conversion.

After step 05, run `SampleContentUnderstandingSkill2/101_knowledge_base.ipynb` unchanged
(make sure `NAME_PREFIX` and `AZURE_SEARCH_ENDPOINT` match).

## Usage

### Option A — Notebooks

Open and run the notebooks `00` → `05` in order from this folder. Each notebook reads
`../.env` and writes its working folders here (`./pdf`, `./image`, `./markdown`,
`./verbalized`, `./shards`).

### Option B — Python scripts (`script/`)

`script/` contains a `.py` equivalent of every notebook for headless / CLI runs. Each script
adds the parent folder to `sys.path` (to import `utils_cc.py`) and `chdir`s up one level, so it
behaves exactly like the notebooks regardless of where you launch it from. Run them in order:

```bash
python script/00_office_to_pdf.py
python script/01_pdf_to_images.py
python script/02_extract_markdown.py
python script/03_verbalize_images.py
python script/04_create_index.py
python script/05_chunk_embed_push.py
```

`utils_cc.py` is shared (the scripts import the one in the parent folder — no duplicate copy).
`03` is idempotent: re-running it skips images already verbalized, so an interrupted run can be
resumed safely.

## Chunking configuration (requirement)

Adjust at the top of `05`, or via `.env`:

```
CHUNK_MAX_TOKENS=8000        # chunk size (tokens)
CHUNK_OVERLAP_TOKENS=2000    # overlap (tokens)
```

`utils_cc.chunk_by_tokens(text, max_tokens, overlap_tokens)` slides a token window with the
requested overlap (`cl100k_base`, compatible with text-embedding-3-large). Embedding input is
also capped at the model limit (8191 tokens) as a safety backstop.

## Push model (no giant vector file)

`05` processes **one document at a time**, writes that document's records to
`./shards/{stem}.jsonl`, then pushes them via `upload_documents` in batches of 100.
No single huge vector JSON is produced, so it scales with the number of files, is memory/disk
friendly, and is easy to resume.

## Setup

1. `pip install -r requirements.txt`
2. Copy `sample.env` to `.env` and fill in the values
3. **poppler** (for `01`): place the binaries in `../poppler/bin` or on `PATH`
4. **Office → PDF** (for `00`, only if you process Excel/PowerPoint/Word): put LibreOffice (`soffice`) on `PATH`,
   or use Windows + Microsoft Excel/PowerPoint/Word + `pywin32`. If neither is available, convert to PDF manually
   and drop the files into `./pdf`
5. **HTML → PDF** (for `00`, only if you process `.html`/`.htm`): install the Chromium browser used by Playwright
   once with `python -m playwright install chromium`
6. `az login` (when using Entra ID authentication)

## Authentication

If `AZURE_SEARCH_API_KEY` is set it is used; otherwise Microsoft Entra ID
(`DefaultAzureCredential` / `AzureCliCredential`) is used. Azure OpenAI, Content Understanding,
and Blob Storage authenticate the same way (key or Entra ID). When using Entra ID, the following
roles are required:

- AI Search: **Search Index Data Contributor** (push), **Search Service Contributor** (index creation)
- Azure OpenAI: **Cognitive Services OpenAI User**
- Content Understanding (Foundry): **Cognitive Services User**
- Blob Storage: **Storage Blob Data Contributor**
- The index's integrated vectorizer (query-time vectorization) requires the AI Search
  **managed identity** to have **Cognitive Services OpenAI User** on the Azure OpenAI resource

## Required environment variables

See `sample.env`. Key ones: `NAME_PREFIX`, `AZURE_SEARCH_ENDPOINT`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_EMBEDDING_DEPLOYMENT` (= text-embedding-3-large / 3072),
`CHAT_DEPLOYMENT` (Vision-capable), `AI_SERVICES_SUBDOMAIN_URL` (Content Understanding),
`STORAGE_ACCOUNT_URL` or `STORAGE_CONNECTION_STRING`, `BLOB_CONTAINER_NAME`, `AZURE_TENANT_ID`.

## Files

```
customChunkPipeline/
├── 00_office_to_pdf.ipynb
├── 01_pdf_to_images.ipynb
├── 02_extract_markdown.ipynb
├── 03_verbalize_images.ipynb
├── 04_create_index.ipynb
├── 05_chunk_embed_push.ipynb
├── utils_cc.py          # shared helpers (auth, embeddings, chunking, uid, Blob)
├── requirements.txt
├── sample.env           # copy to .env
├── .gitignore
├── README.md
└── script/              # .py equivalents of the notebooks (headless runs)
    ├── 00_office_to_pdf.py ... 05_chunk_embed_push.py
```

The working folders `pdf/`, `image/`, `markdown/`, `verbalized/`, and `shards/` are created at
runtime by the notebooks and are excluded via `.gitignore` (along with `.env` and Python caches).
