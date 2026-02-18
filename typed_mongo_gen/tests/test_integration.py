"""Integration tests for the full generation pipeline."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from typed_mongo import clear_registry


@pytest.fixture(autouse=True)
def clean_registry():
    """Clear registry before and after each test."""
    clear_registry()
    yield
    clear_registry()


def test_end_to_end_generation(tmp_path: Path):
    """Test complete flow: define models -> run CLI -> verify output."""
    # Create a test models file
    models_file = tmp_path / "models.py"
    models_file.write_text(
        dedent("""
        from typed_mongo import MongoCollectionModel
        from pydantic import Field

        class Product(MongoCollectionModel):
            __collection_name__ = "products"

            id: str = Field(serialization_alias="_id")
            name: str
            price: float
            in_stock: bool

        class Order(MongoCollectionModel):
            __collection_name__ = "orders"

            id: str = Field(serialization_alias="_id")
            product_id: str
            quantity: int
            total: float
    """)
    )

    output_file = tmp_path / "types.py"
    stub_file = tmp_path / "types.pyi"

    # Run the CLI
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "typed_mongo_gen.cli",
            str(models_file),
            "--output",
            str(output_file),
        ],
        cwd=Path(__file__).parent.parent.parent,  # typed_mongo_gen root
        capture_output=True,
        text=True,
    )

    # Verify success
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert output_file.exists()
    assert stub_file.exists()

    # Verify runtime file content
    runtime_content = output_file.read_text()
    assert "type ProductPath = str" in runtime_content
    assert "type OrderPath = str" in runtime_content
    assert "ProductQuery = dict[str, Any]" in runtime_content
    assert "OrderQuery = dict[str, Any]" in runtime_content

    # Verify stub file content
    stub_content = stub_file.read_text()
    assert "type ProductPath = Literal[" in stub_content
    assert '"_id",' in stub_content  # serialization_alias
    assert '"name",' in stub_content
    assert '"price",' in stub_content
    assert 'ProductQuery = TypedDict("ProductQuery"' in stub_content
    assert '"name": Op[str],' in stub_content
    assert '"price": Op[float],' in stub_content

    # Verify generated code compiles
    compile(stub_content, "<test>", "exec")

    # Verify both models are included
    assert "Product" in stub_content
    assert "Order" in stub_content


def test_cli_errors_on_empty_registry(tmp_path: Path):
    """CLI should exit with error if no models found."""
    # Create a file with no MongoCollectionModel subclasses
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("# No models here\n")

    output_file = tmp_path / "types.py"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "typed_mongo_gen.cli",
            str(empty_file),
            "--output",
            str(output_file),
        ],
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "No MongoCollectionModel subclasses found" in result.stderr
    assert not output_file.exists()
