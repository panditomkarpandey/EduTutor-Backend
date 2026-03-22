"""
MongoDB Atlas Vector Search Index Setup
========================================
Run this script ONCE after connecting to MongoDB Atlas to create
the vector search index for the chunks collection.

Requirements:
- MongoDB Atlas M10+ cluster (Vector Search requires Atlas)
- Correct MONGODB_URI in .env

Usage:
    python setup_atlas_index.py
"""

import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

VECTOR_SEARCH_INDEX = {
    "name": "embedding_index",
    "type": "vectorSearch",
    "definition": {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": 384,
                "similarity": "cosine"
            },
            {
                "type": "filter",
                "path": "textbook_id"
            },
            {
                "type": "filter",
                "path": "subject"
            }
        ]
    }
}


async def create_vector_index():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("ERROR: MONGODB_URI not set in .env")
        return

    db_name = os.getenv("MONGODB_DB", "education_tutor")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]

    print(f"Connecting to: {db_name}")

    try:
        # List existing indexes
        existing = await db.chunks.list_search_indexes().to_list(length=20)
        existing_names = [idx["name"] for idx in existing]

        if "embedding_index" in existing_names:
            print("✅ Vector search index 'embedding_index' already exists.")
            client.close()
            return

        # Create the index
        await db.chunks.create_search_index(VECTOR_SEARCH_INDEX)
        print("✅ Vector search index 'embedding_index' created successfully!")
        print("   Note: Index may take a few minutes to become active on Atlas.")

    except Exception as e:
        print(f"❌ Error creating index: {e}")
        print("\n── Manual Setup Instructions ─────────────────────────────────")
        print("1. Go to https://cloud.mongodb.com")
        print("2. Navigate to: Atlas Search → Create Search Index")
        print("3. Select 'JSON Editor' and paste the following:")
        import json
        print(json.dumps(VECTOR_SEARCH_INDEX, indent=2))
        print("\n4. Set Collection: education_tutor.chunks")
        print("5. Click 'Create Search Index'")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(create_vector_index())
