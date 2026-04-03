# query.py

# IMPORTS
import re, os
from typing import cast
import requests

from dotenv import load_dotenv
from qdrant_client import QdrantClient

from llama_index.core import VectorStoreIndex, Settings, StorageContext
from llama_index.core.base.response.schema import Response
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.vector_stores.qdrant import QdrantVectorStore

# CONFIG
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
print("[DEBUG] TAVILY_API_KEY set:", bool(TAVILY_API_KEY))

MIN_SCORE = 0.30 # for node filtering
TOP_K = 5
EMBED_DIMS = 512

def clean_response(text):
    # strips <think> blocks from output
    return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

# Model Setup
print("\n[INIT] Loading models...")
print(f"       Embedding : {EMBED_MODEL}")
print(f"       LLM       : {LLM_MODEL}\n")


SYSTEM_PROMPT = """
    You are a question-answering assistant over local document collections and trusted web snippets.

    General rules:
    - Use ONLY the context provided in the prompt (local data + optional web data).
    - Do NOT use outside knowledge or assumptions.
    - Prefer precise, locally grounded numbers and statements.
    - For numeric questions (amounts, percentages, dates, growth rates, counts),
    copy the exact numbers from the context.
    - Never guess or invent numbers that are not supported by the context.
"""

Settings.embed_model = OpenAIEmbedding(
    model=EMBED_MODEL,
    api_key=OPENAI_API_KEY,
    dimensions=EMBED_DIMS,
)

Settings.llm = OpenAI(
    model=LLM_MODEL,
    api_key=OPENAI_API_KEY,
    request_timeout=360.0,
    temperature=0.0,
    system_prompt=SYSTEM_PROMPT,
)

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Retrieval Layer

def get_existing_collections():
    return [c.name for c in qdrant_client.get_collections().collections]

def show_collection_menu():
    existing = get_existing_collections()
    print("=" * 65)
    print("  Available Collections")
    print("=" * 65)
    print("  --- RAG Collections ---")
    if not existing:
        print("  (No collections found in Qdrant)\n")
        return
    for idx, name in enumerate(existing, start=1):
        print(f"  [{idx:>2}]  ✅  {name}")
    print()

def select_collection():
    while True:
        existing = get_existing_collections()
        show_collection_menu()

        if not existing:
            print("\n  ❌ No collections available in Qdrant.\n")
            raise SystemExit(1)

        choice = input("  Select collection number: ").strip()

        if not choice.isdigit():
            print("\n  ❌ Invalid choice. Please enter a number from the list.\n")
            continue

        idx = int(choice)
        if idx < 1 or idx > len(existing):
            print("\n  ❌ Invalid choice. Please enter a number from the list.\n")
            continue

        col_name = existing[idx - 1]
        label = col_name

        return col_name, label

def build_query_engine(collection_name):
    vector_store = QdrantVectorStore(client=qdrant_client, collection_name=collection_name)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)
    
    return index.as_query_engine(similarity_top_k=TOP_K,response_mode="compact")

def is_out_of_scope(local_nodes):
    if not local_nodes:
        return True
 
    scores = [sn.score or 0 for sn in local_nodes]
    max_score = max(scores)
    avg_score = sum(scores) / len(scores)
 
    print(f"[DEBUG] Relevance check → max: {max_score:.3f}, avg: {avg_score:.3f}")
    if max_score < 0.35 or avg_score< 0.30:
        return True
 
    return False

def run_query(engine, question: str):
    # run similarity search and apply MIN_SCORE gate.
    response = engine.query(question)

    for sn in response.source_nodes:
        node = sn.node
        if node.text is None:
            payload_text = node.metadata.get("text") or node.metadata.get("content")
            node.text = payload_text or ""
    
    # Original nodes
    original_nodes = response.source_nodes.copy()

    # Score-based filtering
    filtered = []
    for sn in response.source_nodes:
        if sn.score is None or sn.score < MIN_SCORE:
            continue
        filtered.append(sn)

    response.source_nodes = filtered
    return response, original_nodes

def get_primary_source_type(source_nodes) -> str:
    types = []
    for sn in source_nodes:
        st = (sn.node.metadata.get("source_type") or "").lower().strip()
        if st:
            types.append(st)

    if not types:
        return "unknown"

    return max(set(types), key=types.count)

def decide_use_web(question: str, collection_name: str, source_type: str, local_nodes) -> bool:
    source_type = (source_type or "").lower().strip()

    # Hard rule: image/excel/csv collections should stay local-only
    if source_type in {"image", "excel", "csv"}:
        print(f"[DEBUG] Web skipped: source_type={source_type} -> local-only mode")
        return False

    # If local retrieval is already strong, prefer local only
    strong_hits = any(sn.score is not None and sn.score >= 0.5 for sn in local_nodes)
    print("[DEBUG] Strong local hits present:", strong_hits)
    num_nodes = len(local_nodes)
    
    router_prompt = f"""
        You are a routing assistant.

        The user is asking about a LOCAL Qdrant collection.
        Collection name: {collection_name}
        Primary source type: {source_type}

        Local retrieval summary:
        - Number of relevant chunks:{num_nodes}
        - Strong matches present: {strong_hits}

        Decide whether web search is needed in addition to local retrieval.

        Use web if:
        - the question requires latest/current/recent information
        - OR the local data is insufficient to fully answer the question
        - or the question involves comparison with newer data not present in documents

        Do NOT use web if:
        - the answer is fully available in local data
        
        Question:
        {question}

        Answer with one word only:
        - "local_only"
        - "local_plus_web"
"""

    router_llm = Settings.llm
    res = router_llm.complete(router_prompt)
    decision = res.text.strip().lower()
    print("[DEBUG] Router raw decision:", repr(decision))

    if "local_plus_web" in decision:
        return True

    return False


# Web Search Layer (Tavily)
def web_search_snippets(question: str) -> str:
    # Uses Tavily Search API to get web snippets for the question. 

    if not TAVILY_API_KEY:
        print("[DEBUG] No Tavily API key set; skipping web search")
        return ""

    url = "https://api.tavily.com/search"
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": question,
        "max_results": 5,
        "search_depth": "basic",   
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=20)
        print("[DEBUG] Tavily status:", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        print("[DEBUG] Tavily results count:", len(results))
    except Exception as e:
        print(f"[WARN] Tavily search failed: {e}")
        return ""

    snippets = []
    for r in results[:3]:
        title = r.get("title", "")
        url_ = r.get("url", "")
        content = r.get("content", "")
        piece = f"Title: {title}\nURL: {url_}\nSnippet: {content}"
        snippets.append(piece)

    if snippets:
        print("[DEBUG] Web context used (non-empty snippets from Tavily)")
    else:
        print("[DEBUG] Web context empty (no usable snippets from Tavily)")

    return "\n\n".join(snippets)

# Orchestrator/ Answer Layer

def build_final_answer(question: str, local_nodes, use_web: bool = True):
    local_parts = []
    for sn in local_nodes:
        txt = (sn.node.text or "").strip()
        if txt:
            local_parts.append(txt)

    local_context = "\n\n---\n\n".join(local_parts)

    web_context = web_search_snippets(question) if use_web else ""
    if use_web and web_context:
        print("[DEBUG] Final answer context: LOCAL + WEB")
    elif use_web and not web_context:
        print("[DEBUG] Final answer context: LOCAL only (web called but empty)")
    else:
        print("[DEBUG] Final answer context: LOCAL only (web skipped)")

    prompt = f"""
        [LOCAL DATA]
        {local_context}

        User question:
        {question}

        Instructions for your answer:
        - Use ONLY the provided data.
        - Prefer LOCAL DATA whenever it contains the answer.
        - Only say exactly: "The document does not provide this information."
        when there is no relevant information at all.
        - Do NOT mention the phrases 'LOCAL DATA', 'WEB DATA', or 'context' in the answer.
        - Copy numeric values exactly from the data when you use them.
    """

    if use_web and web_context:
        prompt += f"""
            [WEB DATA]
            {web_context}

            Additional instruction:
            - Use WEB DATA only for latest / current / recent information that is clearly not available in LOCAL DATA.
        """

    llm = Settings.llm
    res = llm.complete(prompt)
    return clean_response(res.text)

# MAIN LOOP
print("=" * 65)
print("  RAG Query Engine — All Documents")
print("  Type 'switch' to change collection")
print("  Type 'exit' to quit")
print("=" * 65)

col_name, label = select_collection()
query_engine    = build_query_engine(col_name)

print(f"\n✅ Loaded : {label}")
print(f"   Collection : {col_name}")
print(f"   Top-K      : {TOP_K} chunks per query\n")
print("  Note: I only answer questions related to the loaded collection.")
print("        Off-topic questions will be rejected.\n")

while True:
    print()
    question = input("❓ Your question: ").strip()

    if question.lower() in ["exit", "quit", "q"]:
        print("\nGoodbye! 👋")
        break

    if question.lower() in ["switch", "change", "s", "c"]:
        print()
        col_name, label = select_collection()
        query_engine    = build_query_engine(col_name)
        print(f"\n✅ Switched to : {label}\n")
        continue

    if not question:
        continue

    print(f"\n⏳ Searching [{label}]...\n")

    response, raw_nodes = run_query(query_engine, question)
    if is_out_of_scope(raw_nodes):
        print("💬 Answer:")
        print("-" * 65)
        print("This question is not related to the currently selected document collection.")
        print("-" * 65)
        continue

    # web search decider
    primary_source_type = get_primary_source_type(response.source_nodes)

    # web search decider
    use_web = decide_use_web(
        question=question,
        collection_name=col_name,
        source_type=primary_source_type,
        local_nodes=response.source_nodes,
    )

    if use_web:
        print("[DEBUG] Strategy: RAG + Web (local collection + Tavily) [LLM router]")
    else:
        print("[DEBUG] Strategy: RAG-only (local collection, Tavily skipped) [LLM router]")

    final_answer = build_final_answer(question, response.source_nodes, use_web=use_web)
    
    print("💬 Answer:")
    print("-" * 65)
    print(final_answer)
    print("-" * 65)

    # print(f"\n📄 Sources from [{col_name}]:")
    # seen = set()
    # for node in response.source_nodes:
    #     fname = node.metadata.get("file_name", "Unknown")
    #     score = round(node.score, 4) if node.score else "N/A"
    #     if fname not in seen:
    #         print(f"   - {fname}  (similarity: {score})")
    #         seen.add(fname)