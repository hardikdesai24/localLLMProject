import os
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')
from typing import cast
from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.base.response.schema import Response
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient

OPENAI_API_KEY   = os.environ.get("OPENAI_API_KEY")
EMBED_MODEL      = "text-embedding-3-small"
LLM_MODEL        = "gpt-4o-mini"
QDRANT_HOST      = "localhost"
QDRANT_PORT      = 6333
TOP_K            = 5

# ─────────────────────────────────────────
# ALL 14 COLLECTIONS
# ─────────────────────────────────────────
COLLECTIONS = {
    # Azure Assessment
    "1":  ("rag_defender",         "Defender for Cloud"),
    "2":  ("rag_network",          "Network Security"),
    "3":  ("rag_governance",       "Governance & Policy"),
    "4":  ("rag_finops",           "FinOps & Cost"),
    "5":  ("rag_dataplatform",     "Data Platform"),
    "6":  ("rag_operations",       "Operations & Monitoring"),
    "7":  ("rag_modernisation",    "Modernisation & PaaS"),
    "8":  ("rag_resilience",       "Resilience & BCDR"),
    "9":  ("rag_context",          "Context"),
    # Identity
    "10": ("rag_identity_mfa",     "Identity — MFA Registration (13,948 users)"),
    "11": ("rag_identity_pim",     "Identity — PIM Role Assignments"),
    "12": ("rag_identity_apps",    "Identity — High Privilege App Registrations"),
    "13": ("rag_identity_guests",  "Identity — Guest Users"),
    "14": ("rag_identity_tenant",  "Identity — Tenant Info"),
}

# ─────────────────────────────────────────
# HELPER — strip <think> blocks from output
# ─────────────────────────────────────────
def clean_response(text):
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

# ─────────────────────────────────────────
# CONFIGURE MODELS
# ─────────────────────────────────────────
print("\n[INIT] Loading models...")
print(f"       Embedding : {EMBED_MODEL} (OpenAI)")
print(f"       LLM       : {LLM_MODEL} (OpenAI)\n")

Settings.embed_model = OpenAIEmbedding(
    model=EMBED_MODEL,
    api_key=OPENAI_API_KEY
)
Settings.llm = OpenAI(
    model=LLM_MODEL,
    api_key=OPENAI_API_KEY
)

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# ─────────────────────────────────────────
# HELPER — check which collections exist
# ─────────────────────────────────────────
def get_existing_collections():
    return [c.name for c in qdrant_client.get_collections().collections]

# ─────────────────────────────────────────
# COLLECTION SELECTION MENU
# ─────────────────────────────────────────
def show_collection_menu():
    existing = get_existing_collections()
    print("=" * 65)
    print("  Available Collections")
    print("=" * 65)
    print("  --- Azure Assessment ---")
    for key in ["1","2","3","4","5","6","7","8","9"]:
        col_name, label = COLLECTIONS[key]
        status = "✅" if col_name in existing else "⏳ not ready"
        print(f"  [{key:>2}]  {status}  {label}")
    print()
    print("  --- Identity & Access ---")
    for key in ["10","11","12","13","14"]:
        col_name, label = COLLECTIONS[key]
        status = "✅" if col_name in existing else "⏳ not ready"
        print(f"  [{key:>2}]  {status}  {label}")
    print("=" * 65)

def select_collection():
    while True:
        show_collection_menu()
        print()
        choice = input("  Select collection number: ").strip()

        if choice not in COLLECTIONS:
            print("\n  ❌ Invalid choice. Please enter a number from the list.\n")
            continue

        col_name, label = COLLECTIONS[choice]
        existing = get_existing_collections()

        if col_name not in existing:
            print(f"\n  ⏳ '{label}' is not ready yet. Choose another.\n")
            continue

        return col_name, label

# ─────────────────────────────────────────
# BUILD QUERY ENGINE
# ─────────────────────────────────────────
def build_query_engine(collection_name):
    vector_store    = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index           = VectorStoreIndex.from_vector_store(
        vector_store,
        storage_context=storage_context
    )
    return index.as_query_engine(
        similarity_top_k=TOP_K,
        response_mode="compact"
    )

# ─────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────
print("=" * 65)
print("  RAG Query Engine — Azure Assessment Data")
print("  Type 'switch' to change collection")
print("  Type 'exit' to quit")
print("=" * 65)

col_name, label = select_collection()
query_engine    = build_query_engine(col_name)

print(f"\n✅ Loaded : {label}")
print(f"   Collection : {col_name}")
print(f"   Top-K      : {TOP_K} chunks per query\n")

while True:
    print()
    question = input("❓ Your question: ").strip()

    if question.lower() in ["exit", "quit", "q"]:
        print("\nGoodbye! 👋")
        break

    if question.lower() in ["switch", "change", "s"]:
        print()
        col_name, label = select_collection()
        query_engine    = build_query_engine(col_name)
        print(f"\n✅ Switched to : {label}\n")
        continue

    if not question:
        continue

    print(f"\n⏳ Searching [{label}]...\n")

    response     = query_engine.query(question)
    assert hasattr(response, "response"), "Unexpected streaming response type"
    clean_answer = clean_response(cast(Response, response).response)

    print("💬 Answer:")
    print("-" * 65)
    print(clean_answer)
    print("-" * 65)

    print(f"\n📄 Sources from [{col_name}]:")
    seen = set()
    for node in response.source_nodes:
        fname = node.metadata.get("file_name", "Unknown")
        score = round(node.score, 4) if node.score else "N/A"
        if fname not in seen:
            print(f"   - {fname}  (similarity: {score})")
            seen.add(fname)