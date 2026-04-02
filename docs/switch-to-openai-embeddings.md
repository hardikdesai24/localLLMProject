# Switching to OpenAI Managed Embeddings

This guide covers how to replace the local Ollama embedding model (`nomic-embed-text`) with OpenAI's managed embedding API in both the ingest and query scripts.

> **Important:** Existing Qdrant collections must be rebuilt. The local model produces 768-dimensional vectors; OpenAI's models produce 1536 or 3072 dimensions. These are incompatible — old collections cannot be reused.

---

## 1. Install the package

```bash
pip install llama-index-embeddings-openai
```

---

## 2. Set your OpenAI API key

```powershell
# PowerShell (session only)
$env:OPENAI_API_KEY = "sk-..."
```

Or add it permanently via **System Properties → Environment Variables**.

---

## 3. Update `scripts/ingest_multi.py`

### Replace the import

```python
# Remove:
from llama_index.embeddings.ollama import OllamaEmbedding

# Add:
from llama_index.embeddings.openai import OpenAIEmbedding
```

### Replace the embedding config constants

```python
# Remove:
EMBED_MODEL      = "nomic-embed-text"
EMBED_OLLAMA_URL = "http://localhost:11435"

# Add:
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMBED_MODEL    = "text-embedding-3-small"
```

### Replace the `Settings.embed_model` assignment

```python
# Remove:
Settings.embed_model = OllamaEmbedding(
    model_name=EMBED_MODEL,
    base_url=EMBED_OLLAMA_URL
)

# Add:
Settings.embed_model = OpenAIEmbedding(
    model=EMBED_MODEL,
    api_key=OPENAI_API_KEY
)
```

---

## 4. Update `scripts/query.py`

Apply the same three changes as above (the code is identical in both files).

---

## 5. Drop existing Qdrant collections

Open the Qdrant dashboard at `http://localhost:6333/dashboard` and delete all existing collections, or use the Python client:

```python
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
for col in client.get_collections().collections:
    client.delete_collection(col.name)
    print(f"Deleted: {col.name}")
```

---

## 6. Re-run ingestion

```bash
python scripts/ingest_multi.py
```

All collections will be re-embedded using OpenAI and stored in Qdrant with the new vector dimensions.

---

## Model options

| Model | Dimensions | Speed | Cost (per 1M tokens) |
|---|---|---|---|
| `text-embedding-3-small` | 1536 | Fast | ~$0.02 |
| `text-embedding-3-large` | 3072 | Slower | ~$0.13 |
| `text-embedding-ada-002` | 1536 | Fast | ~$0.10 |

`text-embedding-3-small` is recommended — best speed/cost ratio for RAG workloads.
