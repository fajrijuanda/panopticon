import chromadb
from chromadb.config import Settings
import uuid

class MemoryStream:
    def __init__(self, db_path="./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        # Using default all-MiniLM-L6-v2 embedding model built into Chroma,
        # or we can pass a specific model mapped to Ollama.
        self.collection = self.client.get_or_create_collection("agent_memories")

    def insert_memory(self, agent_id: str, text: str):
        mem_id = str(uuid.uuid4())
        self.collection.add(
            documents=[text],
            metadatas=[{"agent_id": agent_id}],
            ids=[mem_id]
        )

    def retrieve_context(self, agent_id: str, queryText: str, k: int = 5):
        # Only retrieve memories belonging to this agent
        results = self.collection.query(
            query_texts=[queryText],
            n_results=k,
            where={"agent_id": agent_id}
        )
        if not results['documents']:
            return []
        
        return results['documents'][0]

# Singleton instance
memory_db = MemoryStream()
