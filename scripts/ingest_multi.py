import os
import sys
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

# ─────────────────────────────────────────
# GPU ASSIGNMENT
# Embedding → T400   (port 11435)
# LLM       → 5070 Ti (port 11434)
# ─────────────────────────────────────────
EMBED_MODEL      = "nomic-embed-text"
EMBED_OLLAMA_URL = "http://localhost:11435"
LLM_MODEL        = "nemotron-3-nano:4b"
LLM_OLLAMA_URL   = "http://localhost:11434"
QDRANT_HOST      = "localhost"
QDRANT_PORT      = 6333

# ─────────────────────────────────────────
# FILE → COLLECTION MAPPING
# Each file gets its own isolated collection
# ─────────────────────────────────────────
FILE_COLLECTION_MAP = {
    "DefenderForCloud.json"        : "rag_defender",
    "NetworkSecurity.json"         : "rag_network",
    "GovernanceAndPolicy.json"     : "rag_governance",
    "FinOpsAndCost.json"           : "rag_finops",
    "DataPlatform.json"            : "rag_dataplatform",
    "OperationsAndMonitoring.json" : "rag_operations",
    "ModernisationAndPaaS.json"    : "rag_modernisation",
    "ResilienceAndBCDR.json"       : "rag_resilience",
    "Context.json"                 : "rag_context",

# Identity CSVs (processed from IdentityAccess.json)
    "identity_mfa.csv"             : "rag_identity_mfa",
    "identity_pim.csv"             : "rag_identity_pim",
    "identity_apps.csv"            : "rag_identity_apps",
    "identity_guests.csv"          : "rag_identity_guests",
    "identity_tenant.csv"          : "rag_identity_tenant",

}

# Files to skip entirely (e.g. logs)
SKIP_FILES = ["errors.log"]

DOCS_PATH = r"C:\RAG\documents"
DOCS_PATH_PROCESSED = r"C:\RAG\documents\processed"

# ─────────────────────────────────────────
# CONFIGURE MODELS
# ─────────────────────────────────────────
print("\n[INIT] Configuring models...")
print(f"       Embedding : {EMBED_MODEL} @ {EMBED_OLLAMA_URL}")
print(f"       LLM       : {LLM_MODEL} @ {LLM_OLLAMA_URL}")

Settings.embed_model = OllamaEmbedding(
    model_name=EMBED_MODEL,
    base_url=EMBED_OLLAMA_URL
)
Settings.llm = Ollama(
    model=LLM_MODEL,
    base_url=LLM_OLLAMA_URL,
    request_timeout=180.0
)

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# ─────────────────────────────────────────
# INGEST EACH FILE INTO ITS OWN COLLECTION
# ─────────────────────────────────────────
total_files = len(FILE_COLLECTION_MAP)
completed   = 0
skipped     = 0
failed      = []

print(f"\n[START] Ingesting {total_files} files into separate collections...\n")
print("=" * 60)

for filename, collection_name in FILE_COLLECTION_MAP.items():
     # CSVs are in processed folder, JSONs in main documents folder
    if filename.endswith(".csv"):
        filepath = os.path.join(DOCS_PATH_PROCESSED, filename)
    else:
        filepath = os.path.join(DOCS_PATH, filename)

    # Skip files in skip list
    if filename in SKIP_FILES:
        print(f"[SKIP]  {filename}")
        skipped += 1
        continue

    # Skip if file doesn't exist
    if not os.path.exists(filepath):
        print(f"[MISS]  {filename} — file not found, skipping")
        skipped += 1
        continue

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"[{completed+1}/{total_files}] {filename} ({file_size_mb:.1f} MB)")
    print(f"        → Collection: {collection_name}")

    try:
        # Skip if collection already exists in Qdrant
        existing = [c.name for c in qdrant_client.get_collections().collections]
        if collection_name in existing:
            print(f"        ⏭️  Already exists in Qdrant — skipping\n")
            completed += 1
            continue

        # Load single file
        reader    = SimpleDirectoryReader(input_files=[filepath])
        documents = reader.load_data()
        print(f"        → Loaded {len(documents)} document chunk(s)")

        # Connect to or create collection
        vector_store    = QdrantVectorStore(
            client=qdrant_client,
            collection_name=collection_name
        )
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        # Embed and store
        print(f"        → Embedding and indexing...")
        VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            show_progress=True
        )

        print(f"        ✅ Done\n")
        completed += 1

    except Exception as e:
        print(f"        ❌ Failed: {e}\n")
        failed.append(filename)

# ─────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────
print("=" * 60)
print(f"\n✅ Ingestion Summary:")
print(f"   Completed : {completed} collections")
print(f"   Skipped   : {skipped} files")
print(f"   Failed    : {len(failed)} files")
if failed:
    print(f"   Failed files: {', '.join(failed)}")
print(f"\nVerify at: http://localhost:6333/dashboard")