"""Example: Basic usage of typed_mongo."""

from motor.motor_asyncio import AsyncIOMotorClient
from typed_mongo import MongoCollectionModel, get_registry


# Define your models
class User(MongoCollectionModel):
    __collection_name__ = "users"

    name: str
    email: str
    age: int


class Product(MongoCollectionModel):
    __collection_name__ = "products"

    name: str
    price: float
    in_stock: bool


# Models auto-register when defined
print("Registered models:")
for name in get_registry():
    print(f"  - {name}")


# Use with MongoDB
async def example():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.test_db

    # Get typed collection
    users = User.get_collection(db)

    # Insert a document
    await users.insert_one(
        {"name": "Alice", "email": "alice@example.com", "age": 30}
    )

    # Query documents
    user = await users.find_one({"name": "Alice"})
    print(f"Found user: {user}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(example())
