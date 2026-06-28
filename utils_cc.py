"""Shared helpers for the custom-chunk RAG pipeline (customChunkPipeline).

Auth model mirrors 101_knowledge_base.ipynb: use AZURE_SEARCH_API_KEY when present,
otherwise Microsoft Entra ID via DefaultAzureCredential / AzureCliCredential.
"""
import os
import re
import hashlib
from pathlib import Path
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_random_exponential


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #
def get_credential():
    """Return a token credential. Uses AzureCliCredential scoped to the tenant
    when AZURE_TENANT_ID is set, otherwise DefaultAzureCredential."""
    from azure.identity import AzureCliCredential, DefaultAzureCredential

    tenant_id = os.getenv("AZURE_TENANT_ID")
    if tenant_id and tenant_id != "<tenant-id>":
        return AzureCliCredential(tenant_id=tenant_id)
    return DefaultAzureCredential()


def get_search_credential(credential=None):
    """AzureKeyCredential when AZURE_SEARCH_API_KEY is set, else a token credential."""
    from azure.core.credentials import AzureKeyCredential

    key = os.getenv("AZURE_SEARCH_API_KEY")
    if key:
        return AzureKeyCredential(key)
    return credential or get_credential()


# --------------------------------------------------------------------------- #
# Azure OpenAI client (embeddings + vision verbalization)
# --------------------------------------------------------------------------- #
def get_aoai_client(credential=None):
    """Return an AzureOpenAI client. Uses AZURE_OPENAI_API_KEY when present,
    otherwise Entra ID bearer tokens."""
    import openai

    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")

    if api_key:
        return openai.AzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version
        )

    from azure.identity import get_bearer_token_provider

    token_provider = get_bearer_token_provider(
        credential or get_credential(), "https://cognitiveservices.azure.com/.default"
    )
    return openai.AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version=api_version,
    )


# text-embedding-3-* hard limit is 8192 tokens; keep one token of safety margin.
MAX_EMBED_TOKENS = 8191


def _truncate_to_tokens(text: str, max_tokens: int, encoding_name: str = "cl100k_base") -> str:
    """Trim text so it encodes to at most ``max_tokens`` tokens (backstop)."""
    enc = _get_encoding(encoding_name)
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return enc.decode(tokens[:max_tokens])


@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6))
def generate_embeddings(text: str, model: str, client,
                        max_tokens: int = MAX_EMBED_TOKENS) -> List[float]:
    """Embed a single string. Empty text returns an empty list (caller should skip).

    Newlines are preserved (text-embedding-3 handles them fine); the input is
    truncated to ``max_tokens`` as a hard backstop so a boundary/whitespace
    token-count mismatch can never trigger a 400 'maximum input length' error.
    """
    text = (text or "").strip()
    if not text:
        return []
    text = _truncate_to_tokens(text, max_tokens)
    return client.embeddings.create(input=[text], model=model).data[0].embedding


# --------------------------------------------------------------------------- #
# Token-based markdown chunking
# --------------------------------------------------------------------------- #
def _get_encoding(encoding_name: str = "cl100k_base"):
    import tiktoken

    return tiktoken.get_encoding(encoding_name)


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    return len(_get_encoding(encoding_name).encode(text or ""))


def chunk_by_tokens(
    text: str,
    max_tokens: int = 8000,
    overlap_tokens: int = 2000,
    encoding_name: str = "cl100k_base",
) -> List[str]:
    """Split text into overlapping token windows.

    Each chunk has up to ``max_tokens`` tokens; consecutive chunks share
    ``overlap_tokens`` tokens. ``max_tokens`` and ``overlap_tokens`` are the
    tunable arguments requested for this pipeline.
    """
    if not text or not text.strip():
        return []
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")

    enc = _get_encoding(encoding_name)
    tokens = enc.encode(text)
    if len(tokens) <= max_tokens:
        return [text]

    step = max_tokens - overlap_tokens
    chunks: List[str] = []
    start = 0
    while start < len(tokens):
        window = tokens[start : start + max_tokens]
        chunks.append(enc.decode(window))
        if start + max_tokens >= len(tokens):
            break
        start += step
    return chunks


# --------------------------------------------------------------------------- #
# Stable, URL-safe document keys (Azure Search keys allow only [A-Za-z0-9_\-=])
# --------------------------------------------------------------------------- #
def doc_id(stem: str) -> str:
    """Deterministic short id for a document stem (handles non-ASCII filenames)."""
    return "cc" + hashlib.sha1(stem.encode("utf-8")).hexdigest()[:16]


def text_uid(stem: str, chunk_index: int) -> str:
    return f"{doc_id(stem)}_t{chunk_index:04d}"


def image_uid(stem: str, page_number: int) -> str:
    return f"{doc_id(stem)}_i{page_number:04d}"


# --------------------------------------------------------------------------- #
# Filename <-> page helpers
# --------------------------------------------------------------------------- #
def page_image_name(stem: str, page_number: int, separator: str, ext: str = "jpeg") -> str:
    return f"{stem}{separator}{page_number:02d}.{ext}"


def parse_page_image_name(filename: str, separator: str):
    """Return (stem, page_number) parsed from a page-image/verbalized filename."""
    base = Path(filename).stem
    if separator not in base:
        return base, None
    stem, _, page = base.rpartition(separator)
    try:
        return stem, int(page)
    except ValueError:
        return base, None


# --------------------------------------------------------------------------- #
# Blob storage (upload page images / source docs, return URL for blob_url)
# --------------------------------------------------------------------------- #
def _account_url_from_resource_id(conn: str) -> Optional[str]:
    """Extract a blob endpoint from a ``ResourceId=/subscriptions/.../storageAccounts/<name>/;``
    style connection string (managed-identity form used in this repo)."""
    m = re.search(r"storageAccounts/([^/;]+)", conn or "")
    if m:
        return f"https://{m.group(1)}.blob.core.windows.net"
    return None


def get_blob_service_client(credential=None):
    """Resolve a BlobServiceClient.

    Priority:
    1. A genuine connection string (AccountKey / SAS) -> key auth.
    2. STORAGE_ACCOUNT_URL (Entra ID).
    3. ResourceId=... connection string -> derive account URL + Entra ID.
    """
    from azure.storage.blob import BlobServiceClient

    account_url = os.getenv("STORAGE_ACCOUNT_URL")
    conn = os.getenv("STORAGE_CONNECTION_STRING", "")

    # 1) Real connection string with embedded credentials
    if conn and ("AccountKey=" in conn or "SharedAccessSignature=" in conn):
        return BlobServiceClient.from_connection_string(conn)

    # 2) Explicit account URL + Entra ID
    if account_url and account_url != "https://<storage-account>.blob.core.windows.net":
        return BlobServiceClient(account_url=account_url, credential=credential or get_credential())

    # 3) ResourceId=... form -> derive account URL, use Entra ID
    derived = _account_url_from_resource_id(conn)
    if derived:
        return BlobServiceClient(account_url=derived, credential=credential or get_credential())

    raise ValueError(
        "Could not resolve storage account. Set STORAGE_ACCOUNT_URL, or provide a "
        "STORAGE_CONNECTION_STRING (AccountKey/SAS or ResourceId=... form)."
    )


def upload_blob(blob_service_client, container_name: str, blob_name: str,
                data: bytes, content_type: Optional[str] = None,
                overwrite: bool = True) -> str:
    """Upload bytes and return the blob URL (used for the blob_url field)."""
    from azure.storage.blob import ContentSettings

    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    cs = ContentSettings(content_type=content_type) if content_type else None
    blob_client.upload_blob(data, overwrite=overwrite, content_settings=cs)
    return blob_client.url


def upload_file(blob_service_client, container_name: str, local_path,
                blob_name: Optional[str] = None, content_type: Optional[str] = None) -> str:
    local_path = Path(local_path)
    blob_name = blob_name or local_path.name
    with open(local_path, "rb") as f:
        return upload_blob(blob_service_client, container_name, blob_name, f.read(),
                           content_type=content_type)


# --------------------------------------------------------------------------- #
# Misc
# --------------------------------------------------------------------------- #
def iter_files(directory, suffixes):
    directory = Path(directory)
    if not directory.exists():
        return []
    suffixes = tuple(s.lower() for s in suffixes)
    return sorted(p for p in directory.iterdir()
                  if p.is_file() and p.suffix.lower() in suffixes)
