# Local RAG Setup — Steps 1 to 5 Summary

**System:** Windows 11 | RTX 5070 Ti (16GB) | T400 (4GB) | 64GB RAM | i5-13600K  
**Stack:** Ollama + nomic-embed-text + LlamaIndex + Qdrant (Docker)  
**LLM Model:** mychen76/qwen3_cline_roocode:14b  
**Embedding Model:** nomic-embed-text  

---

## GPU Architecture — Dual GPU Assignment

| GPU | Role | Ollama Port | Model |
|---|---|---|---|
| RTX 5070 Ti (GPU 0) | LLM Inference | 11434 | mychen76/qwen3_cline_roocode:14b |
| NVIDIA T400 (GPU 1) | Embedding Model | 11435 | nomic-embed-text |
| i5-13600K iGPU | Display Output | N/A | N/A |

### Why Separate GPUs?
- Prevents LLM and embedding model from competing for same VRAM
- T400 (4GB) is sufficient for nomic-embed-text (~274MB model)
- RTX 5070 Ti (16GB) runs the 14b model fully in VRAM — no RAM spillover
- Result: ~2x faster generation, ~100x faster prompt evaluation

### Lock Main Ollama Service to GPU 0 (RTX 5070 Ti)
```powershell
# Run PowerShell as Administrator
[System.Environment]::SetEnvironmentVariable("CUDA_VISIBLE_DEVICES", "0", "Machine")

# Restart Ollama service
Stop-Service ollama
Start-Service ollama
```

### Start Second Ollama Instance on GPU 1 (T400) for Embeddings
```powershell
# Open a NEW dedicated PowerShell window — keep it running
$env:CUDA_VISIBLE_DEVICES = "1"
$env:OLLAMA_HOST = "127.0.0.1:11435"
ollama serve
```

### Pull Embedding Model into Second Instance
```powershell
# In another PowerShell window
$env:OLLAMA_HOST = "127.0.0.1:11435"
ollama pull nomic-embed-text
```

### Verify Both Instances Are Running
```powershell
# Main LLM instance (5070 Ti)
Invoke-RestMethod http://localhost:11434/api/tags

# Embedding instance (T400)
Invoke-RestMethod http://localhost:11435/api/tags
```

> ⚠️ **Important:** The T400 Ollama instance must be manually started in a dedicated PowerShell window every time the system reboots. It does not auto-start like the main Ollama service.

---

## Step 1 — Pull Embedding Model into Ollama

```powershell
# Pull the embedding model
ollama pull nomic-embed-text

# Verify it is available
ollama list

# Quick sanity test
ollama run nomic-embed-text "test embedding"
```

✅ **Success indicator:** `nomic-embed-text` appears in `ollama list`

---

## Step 2 — Set Up Python Environment

### 2.1 Verify Python Version
```powershell
python --version
# Required: Python 3.10 or 3.11+
```

### 2.2 Create Project Folder
```powershell
mkdir C:\RAG
cd C:\RAG
```

### 2.3 Create Virtual Environment
```powershell
python -m venv rag-env
```

### 2.4 Activate Virtual Environment
```powershell
.\rag-env\Scripts\Activate.ps1
```
> ⚠️ If you get a script execution error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

### 2.5 Upgrade pip
```powershell
python -m pip install --upgrade pip
```

### 2.6 Install Core RAG Packages
```powershell
pip install llama-index llama-index-llms-ollama llama-index-embeddings-ollama llama-index-vector-stores-qdrant qdrant-client chromadb
```

```powershell
pip install pypdf docx2txt pandas tqdm openpyxl
```

### 2.7 Verify Installations
```powershell
python -c "import llama_index; import qdrant_client; print('All packages loaded successfully')"
```

✅ **Success indicator:** `All packages loaded successfully`

---

## Step 3 — Install and Run Qdrant Locally (Docker)

### 3.1 Verify Docker is Installed
```powershell
docker --version
```

### 3.2 Pull Qdrant Docker Image
```powershell
docker pull qdrant/qdrant
```

### 3.3 Create Persistent Storage Folder
```powershell
mkdir C:\RAG\qdrant_storage
```

### 3.4 Run the Qdrant Container
```powershell
docker run -d `
  --name qdrant `
  --restart unless-stopped `
  -p 6333:6333 `
  -p 6334:6334 `
  -v C:\RAG\qdrant_storage:/qdrant/storage `
  qdrant/qdrant
```

### 3.5 Verify Qdrant is Running
```powershell
curl http://localhost:6333
```
> Or open in browser: `http://localhost:6333/dashboard`

### 3.6 Test Qdrant from Python
```powershell
python -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='localhost', port=6333)
print('Qdrant connection successful')
print('Collections:', client.get_collections())
"
```

✅ **Success indicator:** `Qdrant connection successful` | `Collections: collections=[]`

### 3.7 Useful Docker Commands
```powershell
docker ps              # Check if container is running
docker stop qdrant     # Stop Qdrant
docker start qdrant    # Start Qdrant
docker restart qdrant  # Restart Qdrant
docker logs qdrant     # View Qdrant logs
```

---

## Step 4 — Document Ingestion & Embedding Pipeline

### 4.1 Create Folder Structure
```powershell
mkdir C:\RAG\documents
mkdir C:\RAG\documents\processed
mkdir C:\RAG\scripts
```

### 4.2 Key Lesson — One Collection Per Document Domain

> ⚠️ **Critical architectural decision:** Never mix unrelated documents in a single Qdrant collection. Large files (300MB+) will statistically bury smaller files making retrieval inaccurate. Always use one collection per domain.

### 4.3 Document to Collection Mapping

| File | Collection | Size |
|---|---|---|
| DefenderForCloud.json | rag_defender | 74 KB |
| NetworkSecurity.json | rag_network | 121 KB |
| GovernanceAndPolicy.json | rag_governance | 214 KB |
| FinOpsAndCost.json | rag_finops | 23 KB |
| DataPlatform.json | rag_dataplatform | 13 KB |
| OperationsAndMonitoring.json | rag_operations | 9 KB |
| ModernisationAndPaaS.json | rag_modernisation | 15 KB |
| ResilienceAndBCDR.json | rag_resilience | 5 KB |
| Context.json | rag_context | 5 KB |
| identity_mfa.csv | rag_identity_mfa | 2.9 MB |
| identity_pim.csv | rag_identity_pim | 2 KB |
| identity_apps.csv | rag_identity_apps | 10 KB |
| identity_guests.csv | rag_identity_guests | 13 KB |
| identity_tenant.csv | rag_identity_tenant | 1 KB |

### 4.4 Pre-Processing Large JSON Files — Convert to CSV

Raw API dumps (e.g. IdentityAccess.json at 313MB) must be pre-processed before RAG ingestion. Large raw JSON files contain thousands of null fields that generate meaningless chunks and take hours to embed.

Create `C:\RAG\scripts\convert_identity_to_csv.py`:

```python
import json
import csv
import os

INPUT_FILE  = r"C:\RAG\documents\IdentityAccess.json"
OUTPUT_DIR  = r"C:\RAG\documents\processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def flatten(obj, prefix="", max_depth=3, depth=0):
    result = {}
    if depth > max_depth or not isinstance(obj, dict):
        return result
    for key, val in obj.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"
        if val is None:
            continue
        elif isinstance(val, dict):
            nested = flatten(val, full_key, max_depth, depth+1)
            result.update(nested)
        elif isinstance(val, list):
            non_null = [str(v) for v in val if v is not None]
            if non_null:
                result[full_key] = "; ".join(non_null)
        else:
            result[full_key] = str(val)
    return result

def write_csv(records, output_path, label):
    if not records:
        print(f"  ⚠️  {label} — no records, skipping")
        return 0
    all_keys = []
    seen_keys = set()
    flat_records = []
    for record in records:
        if not isinstance(record, dict):
            continue
        flat = flatten(record)
        flat_records.append(flat)
        for k in flat.keys():
            if k not in seen_keys:
                all_keys.append(k)
                seen_keys.add(k)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        for row in flat_records:
            writer.writerow(row)
    size_kb = os.path.getsize(output_path) / 1024
    print(f"  ✅ {label} → {len(flat_records):,} rows | {size_kb:.1f} KB")
    return len(flat_records)

print("\n[1/3] Loading IdentityAccess.json...")
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)
print("      Loaded successfully!")

print("\n[2/3] Extracting sections...")
tenant = data.get("Tenant", {})
if tenant:
    write_csv([tenant], os.path.join(OUTPUT_DIR, "identity_tenant.csv"), "Tenant Info")

write_csv(data.get("PIMRoleAssignments", []),
          os.path.join(OUTPUT_DIR, "identity_pim.csv"), "PIM Role Assignments")
write_csv(data.get("GuestUsers", []),
          os.path.join(OUTPUT_DIR, "identity_guests.csv"), "Guest Users")
write_csv(data.get("MfaRegistrationDetails", []),
          os.path.join(OUTPUT_DIR, "identity_mfa.csv"), "MFA Registration Details")
write_csv(data.get("HighPrivilegeAppRegistrations", []),
          os.path.join(OUTPUT_DIR, "identity_apps.csv"), "High Privilege App Registrations")

print("\n[3/3] Summary")
for f in os.listdir(OUTPUT_DIR):
    if f.endswith(".csv"):
        size = os.path.getsize(os.path.join(OUTPUT_DIR, f)) / 1024
        print(f"    - {f} ({size:.1f} KB)")
```

Run it:
```powershell
python scripts\convert_identity_to_csv.py
```

**Size reduction achieved:**
```
IdentityAccess.json  313,000 KB (raw)
identity_mfa.csv       2,940 KB (clean)
Reduction: 99.1% smaller ✅
```

### 4.5 Multi-Collection Ingestion Script

Create `C:\RAG\scripts\ingest_multi.py`:

```python
import os
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

# GPU ASSIGNMENT
EMBED_MODEL      = "nomic-embed-text"
EMBED_OLLAMA_URL = "http://localhost:11435"   # T400
LLM_MODEL        = "mychen76/qwen3_cline_roocode:14b"
LLM_OLLAMA_URL   = "http://localhost:11434"   # RTX 5070 Ti
QDRANT_HOST      = "localhost"
QDRANT_PORT      = 6333

DOCS_PATH           = r"C:\RAG\documents"
DOCS_PATH_PROCESSED = r"C:\RAG\documents\processed"

FILE_COLLECTION_MAP = {
    # Azure Assessment JSON files
    "DefenderForCloud.json"        : "rag_defender",
    "NetworkSecurity.json"         : "rag_network",
    "GovernanceAndPolicy.json"     : "rag_governance",
    "FinOpsAndCost.json"           : "rag_finops",
    "DataPlatform.json"            : "rag_dataplatform",
    "OperationsAndMonitoring.json" : "rag_operations",
    "ModernisationAndPaaS.json"    : "rag_modernisation",
    "ResilienceAndBCDR.json"       : "rag_resilience",
    "Context.json"                 : "rag_context",
    # Identity CSVs (processed folder)
    "identity_mfa.csv"             : "rag_identity_mfa",
    "identity_pim.csv"             : "rag_identity_pim",
    "identity_apps.csv"            : "rag_identity_apps",
    "identity_guests.csv"          : "rag_identity_guests",
    "identity_tenant.csv"          : "rag_identity_tenant",
}

SKIP_FILES = ["errors.log"]

print("\n[INIT] Configuring models...")
Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=EMBED_OLLAMA_URL)
Settings.llm = Ollama(model=LLM_MODEL, base_url=LLM_OLLAMA_URL, request_timeout=180.0)

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

total_files = len(FILE_COLLECTION_MAP)
completed = 0
skipped = 0
failed = []

print(f"\n[START] Ingesting {total_files} files into separate collections...\n")
print("=" * 60)

for filename, collection_name in FILE_COLLECTION_MAP.items():
    # Route to correct folder based on file type
    if filename.endswith(".csv"):
        filepath = os.path.join(DOCS_PATH_PROCESSED, filename)
    else:
        filepath = os.path.join(DOCS_PATH, filename)

    if filename in SKIP_FILES:
        print(f"[SKIP]  {filename}")
        skipped += 1
        continue

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

        reader    = SimpleDirectoryReader(input_files=[filepath])
        documents = reader.load_data()
        print(f"        → Loaded {len(documents)} document chunk(s)")

        vector_store    = QdrantVectorStore(client=qdrant_client, collection_name=collection_name)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        print(f"        → Embedding and indexing...")
        VectorStoreIndex.from_documents(documents, storage_context=storage_context, show_progress=True)

        print(f"        ✅ Done\n")
        completed += 1

    except Exception as e:
        print(f"        ❌ Failed: {e}\n")
        failed.append(filename)

print("=" * 60)
print(f"\n✅ Ingestion Summary:")
print(f"   Completed : {completed} collections")
print(f"   Skipped   : {skipped} files")
print(f"   Failed    : {len(failed)} files")
print(f"\nVerify at: http://localhost:6333/dashboard")
```

Run it:
```powershell
cd C:\RAG
python scripts\ingest_multi.py
```

> 💡 **Smart skip logic:** If a collection already exists in Qdrant it is automatically skipped — safe to re-run without duplicating vectors.

### 4.6 Verify Collections in Qdrant

```powershell
python -c "
from qdrant_client import QdrantClient
client = QdrantClient(host='localhost', port=6333)
cols = client.get_collections().collections
print('Collections ready in Qdrant:')
for c in cols:
    info = client.get_collection(c.name)
    print(f'  ✅ {c.name} — {info.points_count:,} vectors')
"
```

✅ **Success indicator:** All 14 collections listed as GREEN in Qdrant dashboard at `http://localhost:6333/dashboard`

---

## Step 5 — Query Engine

### 5.1 How the Query Engine Works

```
User Question
      │
      ▼
Embed question via nomic-embed-text (T400)
      │
      ▼
Search selected Qdrant collection
      │
      ▼
Retrieve Top-K most similar chunks
      │
      ▼
Send chunks + question to LLM (RTX 5070 Ti)
      │
      ▼
LLM generates grounded answer
      │
      ▼
Display answer + source citations
```

### 5.2 Create query.py

Create `C:\RAG\scripts\query.py`:

```python
import os
import re
from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import StorageContext
from qdrant_client import QdrantClient

# GPU ASSIGNMENT
EMBED_MODEL      = "nomic-embed-text"
EMBED_OLLAMA_URL = "http://localhost:11435"   # T400
LLM_MODEL        = "mychen76/qwen3_cline_roocode:14b"
LLM_OLLAMA_URL   = "http://localhost:11434"   # RTX 5070 Ti
QDRANT_HOST      = "localhost"
QDRANT_PORT      = 6333
TOP_K            = 3   # chunks per query (increase to 5 for richer answers)

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

def clean_response(text):
    # Strip <think> reasoning blocks from Qwen3 model output
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

print("\n[INIT] Loading models...")
Settings.embed_model = OllamaEmbedding(model_name=EMBED_MODEL, base_url=EMBED_OLLAMA_URL)
Settings.llm = Ollama(model=LLM_MODEL, base_url=LLM_OLLAMA_URL, request_timeout=360.0)

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

def get_existing_collections():
    return [c.name for c in qdrant_client.get_collections().collections]

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
            print("\n  ❌ Invalid choice.\n")
            continue
        col_name, label = COLLECTIONS[choice]
        if col_name not in get_existing_collections():
            print(f"\n  ⏳ '{label}' is not ready yet.\n")
            continue
        return col_name, label

def build_query_engine(collection_name):
    vector_store    = QdrantVectorStore(client=qdrant_client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index           = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)
    return index.as_query_engine(similarity_top_k=TOP_K, response_mode="compact")

print("=" * 65)
print("  RAG Query Engine — Azure Assessment Data")
print("  Type 'switch' to change collection | 'exit' to quit")
print("=" * 65)

col_name, label = select_collection()
query_engine    = build_query_engine(col_name)
print(f"\n✅ Loaded : {label} | Top-K : {TOP_K}\n")

while True:
    print()
    question = input("❓ Your question: ").strip()

    if question.lower() in ["exit", "quit", "q"]:
        print("\nGoodbye! 👋")
        break

    if question.lower() in ["switch", "change", "s"]:
        col_name, label = select_collection()
        query_engine    = build_query_engine(col_name)
        print(f"\n✅ Switched to : {label}\n")
        continue

    if not question:
        continue

    print(f"\n⏳ Searching [{label}]...\n")
    response     = query_engine.query(question)
    clean_answer = clean_response(response.response)

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
```

### 5.3 Run the Query Engine
```powershell
cd C:\RAG
.\rag-env\Scripts\Activate.ps1
python scripts\query.py
```

### 5.4 Query Engine Commands

| Command | Action |
|---|---|
| Type your question | Search selected collection and get answer |
| `switch` | Show collection menu and change collection |
| `exit` or `quit` | Exit the query engine |

### 5.5 Verified Working Queries

| Collection | Question | Result |
|---|---|---|
| Defender for Cloud | Which services have the Standard tier enabled? | ✅ Listed all 14 services accurately |
| Network Security | Are there any open inbound ports that pose a security risk? | ✅ Identified TCP 443, 8080, 5701 with context |
| FinOps & Cost | Which resources are identified as idle or underutilized? | ✅ Correctly reported empty arrays — no hallucination |

### 5.6 Identity Data — Direct Query for Counting and Lookups

RAG is not suitable for counting or specific user lookups across 13,948 records. Use pandas directly:

```powershell
# Count MFA registration status
python -c "
import pandas as pd
df = pd.read_csv(r'C:\RAG\documents\processed\identity_mfa.csv')
not_mfa = df[df['IsMfaRegistered'] == False]
print(f'Total users     : {len(df)}')
print(f'MFA registered  : {len(df) - len(not_mfa)}')
print(f'Not registered  : {len(not_mfa)}')
"

# Specific user lookup
python -c "
import pandas as pd
df = pd.read_csv(r'C:\RAG\documents\processed\identity_mfa.csv')
user = df[df['UserPrincipalName'].str.lower() == 'hdesai@mhemail.org']
print(user.to_string() if len(user) > 0 else 'User not found')
"
```

---

## Key Lessons Learned

| Lesson | Detail |
|---|---|
| Never mix large and small files in one collection | 313MB file buried all smaller files |
| Raw API dumps are not RAG-ready | Pre-process to remove nulls and flatten structure |
| RAG is for knowledge queries not counting queries | Use pandas for analytics, RAG for insights |
| tqdm time display is MM:SS not HH:MM | `[06:32<36:14]` = 6 mins elapsed, 36 mins remaining |
| CSV is better than raw JSON for tabular identity data | 313MB → 3MB after conversion |
| Separate collections per domain is mandatory | Clean retrieval, no cross-domain pollution |

---

## Final Folder Structure

```
C:\RAG\
│
├── rag-env\                    ← Python virtual environment
├── qdrant_storage\             ← Qdrant persistent vector data (never delete)
├── documents\
│   ├── DefenderForCloud.json
│   ├── NetworkSecurity.json
│   ├── GovernanceAndPolicy.json
│   ├── FinOpsAndCost.json
│   ├── DataPlatform.json
│   ├── OperationsAndMonitoring.json
│   ├── ModernisationAndPaaS.json
│   ├── ResilienceAndBCDR.json
│   ├── Context.json
│   ├── IdentityAccess.json     ← Raw (do not ingest directly)
│   └── processed\
│       ├── identity_mfa.csv
│       ├── identity_pim.csv
│       ├── identity_apps.csv
│       ├── identity_guests.csv
│       └── identity_tenant.csv
└── scripts\
    ├── ingest_multi.py         ← Multi-collection ingestion
    ├── convert_identity_to_csv.py ← JSON to CSV converter
    └── query.py                ← Interactive query engine
```

---

## Startup Checklist (After Every Reboot)

```powershell
# 1. Start T400 Ollama instance (embedding — manual step)
# Open a dedicated PowerShell window and run:
$env:CUDA_VISIBLE_DEVICES = "1"
$env:OLLAMA_HOST = "127.0.0.1:11435"
ollama serve

# 2. In main PowerShell window — activate venv
cd C:\RAG
.\rag-env\Scripts\Activate.ps1

# 3. Verify Qdrant is running (auto-starts with Docker)
curl http://localhost:6333

# 4. Verify main Ollama instance (auto-starts as Windows service)
ollama list

# 5. Run query engine
python scripts\query.py
```

## Shutdown Checklist

```powershell
# 1. Exit query engine
exit

# 2. Deactivate venv
deactivate

# 3. Close T400 Ollama PowerShell window (Ctrl+C then close)

# 4. Normal Windows shutdown — Docker stops Qdrant automatically
shutdown /s /t 0
```

---

## Qdrant Collections Summary (After Full Ingestion)

| Collection | Source File | Vectors | Status |
|---|---|---|---|
| rag_defender | DefenderForCloud.json | 35 | ✅ Green |
| rag_network | NetworkSecurity.json | 40 | ✅ Green |
| rag_governance | GovernanceAndPolicy.json | 84 | ✅ Green |
| rag_finops | FinOpsAndCost.json | ~10 | ✅ Green |
| rag_dataplatform | DataPlatform.json | ~6 | ✅ Green |
| rag_operations | OperationsAndMonitoring.json | ~4 | ✅ Green |
| rag_modernisation | ModernisationAndPaaS.json | ~7 | ✅ Green |
| rag_resilience | ResilienceAndBCDR.json | ~2 | ✅ Green |
| rag_context | Context.json | ~2 | ✅ Green |
| rag_identity_mfa | identity_mfa.csv | 1,549 | ✅ Green |
| rag_identity_pim | identity_pim.csv | 2 | ✅ Green |
| rag_identity_apps | identity_apps.csv | 7 | ✅ Green |
| rag_identity_guests | identity_guests.csv | 10 | ✅ Green |
| rag_identity_tenant | identity_tenant.csv | 1 | ✅ Green |

---

*Next: Step 6 — Chainlit Web UI | Step 7 — Delta Ingestion & Deduplication*
