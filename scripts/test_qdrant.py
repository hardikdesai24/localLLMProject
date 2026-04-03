# test_qdrant.py
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)

res, next_offset = client.scroll(
    collection_name="sample_512",
    limit=100,          
    with_payload=True,
)

for idx, point in enumerate(res, start=1):
    print(f"--- POINT {idx}  id={point.id} ---")
    print("metadata:", point.payload)
    print("\nTEXT:\n")
    print(point.payload.get("text", ""))   # full text, no truncation
    print("-" * 80)