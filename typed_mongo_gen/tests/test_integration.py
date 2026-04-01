"""Integration tests for the full generation pipeline."""

import subprocess
import sys
from pathlib import Path
from textwrap import dedent


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

    # Verify update types are generated
    assert 'ProductUpdate = TypedDict("ProductUpdate"' in stub_content
    assert "ProductNumericFields" in stub_content
    assert "type ProductRefPath = Literal[" in stub_content
    assert '"$price",' in stub_content  # RefPath should have $-prefixed paths
    assert '"$set": ProductFields,' in stub_content
    assert '"$inc": ProductNumericFields,' in stub_content
    assert "type ProductPipelineStage = " in stub_content

    # Verify runtime has update type aliases
    assert "ProductUpdate" in runtime_content
    assert "ProductNumericFields" in runtime_content

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


_MODELS_SOURCE = dedent("""\
    from typed_mongo import MongoCollectionModel
    from pydantic import Field

    class Widget(MongoCollectionModel):
        __collection_name__ = "widgets"
        id: str = Field(serialization_alias="_id")
        name: str
""")


def test_run_after_commands(tmp_path: Path):
    """--run-after commands should be invoked with generated file paths."""
    models_file = tmp_path / "models.py"
    models_file.write_text(_MODELS_SOURCE)

    output_file = tmp_path / "types.py"
    marker = tmp_path / "ran.txt"

    # Use a script that writes its args to a file so we can verify
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "typed_mongo_gen.cli",
            str(models_file),
            "--output",
            str(output_file),
            "--run-after",
            f"python3 -c \"import sys; open('{marker}', 'w').write('\\n'.join(sys.argv[1:]))\"",
        ],
        cwd=Path(__file__).parent.parent.parent,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert marker.exists()
    args = marker.read_text().strip().split("\n")
    assert str(output_file.resolve()) in args[0]
    assert str(output_file.with_suffix(".pyi").resolve()) in args[1]


def test_pyproject_config_jobs(tmp_path: Path):
    """Jobs defined in pyproject.toml should run when no sources provided."""
    models_file = tmp_path / "models.py"
    models_file.write_text(_MODELS_SOURCE)

    output_file = tmp_path / "types.py"

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(dedent(f"""\
        [tool.typed-mongo-gen]

        [[tool.typed-mongo-gen.jobs]]
        sources = ["{models_file}"]
        output = "{output_file}"
    """))

    result = subprocess.run(
        [sys.executable, "-m", "typed_mongo_gen.cli"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output_file.exists()
    assert output_file.with_suffix(".pyi").exists()
    assert "Widget" in output_file.with_suffix(".pyi").read_text()


def test_pyproject_config_defaults(tmp_path: Path):
    """Default args in pyproject.toml should apply to all jobs."""
    models_file = tmp_path / "models.py"
    models_file.write_text(_MODELS_SOURCE)

    output_file = tmp_path / "types.py"
    marker = tmp_path / "ran.txt"

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(dedent(f"""\
        [tool.typed-mongo-gen.defaults]
        run_after = ["python3 -c \\"import sys; open('{marker}', 'w').write('ok')\\""]

        [[tool.typed-mongo-gen.jobs]]
        sources = ["{models_file}"]
        output = "{output_file}"
    """))

    result = subprocess.run(
        [sys.executable, "-m", "typed_mongo_gen.cli"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert marker.exists()


def test_pyproject_no_config_no_sources(tmp_path: Path):
    """Running with no sources and no pyproject config should error."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nname = 'test'\n")

    result = subprocess.run(
        [sys.executable, "-m", "typed_mongo_gen.cli"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "No [tool.typed-mongo-gen] config found" in result.stderr
