"""Example: Generate types from models."""

from pathlib import Path
from typed_mongo import MongoCollectionModel, clear_registry


# Define some models
class User(MongoCollectionModel):
    __collection_name__ = "users"

    name: str
    email: str
    age: int | None = None


class Post(MongoCollectionModel):
    __collection_name__ = "posts"

    title: str
    content: str
    author_id: str
    tags: list[str]


# Generate types programmatically
if __name__ == "__main__":
    from typed_mongo import get_registry
    from typed_mongo_gen.codegen import write_field_paths

    registry = get_registry()

    output_dir = Path(__file__).parent
    runtime_path = output_dir / "generated_types.py"
    stub_path = output_dir / "generated_types.pyi"

    write_field_paths(runtime_path, stub_path, registry)

    print(f"Generated types for {len(registry)} models:")
    for name in registry:
        print(f"  - {name}")
    print(f"\nFiles written:")
    print(f"  {runtime_path}")
    print(f"  {stub_path}")
