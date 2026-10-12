"""Integration tests for the full generation pipeline."""

import subprocess
import sys
import json
import runpy
from pathlib import Path
from textwrap import dedent

from typed_mongo_gen.codegen import write_field_paths


def test_search_pipeline_type_checking(tmp_path: Path):
    """Check actual generated stubs, including errors nested inside compounds."""
    models_file = tmp_path / "models.py"
    models_file.write_text(
        dedent("""\
        from pydantic import BaseModel, Field
        from typed_mongo import MongoCollectionModel

        class Details(BaseModel):
            title: str = Field(serialization_alias="displayTitle")

        class Product(MongoCollectionModel):
            __collection_name__ = "products"
            name: str
            price: float
            details: Details
    """)
    )
    models = runpy.run_path(str(models_file), run_name="models")
    write_field_paths(
        tmp_path / "generated.py",
        tmp_path / "generated.pyi",
        {"Product": models["Product"]},
    )

    (tmp_path / "valid.py").write_text(
        dedent("""\
        from typing import Literal, assert_type
        from models import Product
        from generated import ProductCollection, ProductPath, ProductPipelineStage, ProductSearchStage, ProductSearchMetaStage, ProductSearchCompound, ProductSearchRange, ProductSearchSort, product_aggregation_step
        from typed_mongo import TypedCursor
        from typed_mongo.search import combine_search_sort

        sort_fields: dict[ProductPath, Literal[1, -1]] = {"price": 1}
        stage: ProductSearchStage = {"$search": {
            "index": "products",
            "compound": {
                "must": [{"text": {"query": ["phone", "mobile"], "path": "details.displayTitle",
                    "fuzzy": {"maxEdits": 2, "prefixLength": 1}, "matchCriteria": "any"}}],
                "filter": [{"range": {"path": "price", "gte": 10, "lt": 100}}],
                "mustNot": [{"equals": {"path": "name", "value": "retired"}}],
                "should": [{"compound": {"should": [{"exists": {"path": "name"}}]}}],
                "minimumShouldMatch": 1,
            },
            "highlight": {"path": ["name", {"wildcard": "details.*"}]},
            "count": {"type": "lowerBound", "threshold": 100},
            "sort": combine_search_sort(sort_fields, {"score": {"$meta": "searchScore", "order": -1}}),
            "searchAfter": "token", "scoreDetails": True, "concurrent": True,
            "returnStoredSource": False,
        }}
        pipeline: list[ProductPipelineStage] = [stage, {"$limit": 10}]
        autocomplete: ProductSearchStage = {"$search": {"autocomplete": {"path": "name", "query": "ph", "tokenOrder": "sequential"}}}
        multi: ProductSearchStage = {"$search": {"text": {"path": {"value": "name", "multi": "english"}, "query": "phone"}}}
        phrase: ProductSearchStage = {"$search": {"phrase": {"path": ["name", "details.displayTitle"], "query": "mobile phone", "slop": 1}}}
        inclusion: ProductSearchStage = {"$search": {"in": {"path": ["name"], "value": ["phone"]}}}
        metadata: ProductSearchMetaStage = {"$searchMeta": {"exists": {"path": "name"}, "count": {"type": "total"}}}
        default_count: ProductSearchStage = {"$search": {"exists": {"path": "name"}, "count": {"threshold": 100}}}
        scoped_metadata: ProductSearchMetaStage = {"$searchMeta": {"exists": {"path": "name"}, "returnScope": {"path": "details"}, "returnStoredSource": True}}
        bounds: ProductSearchRange = {"path": "price"}
        bounds["gte"] = 10
        compound: ProductSearchCompound = {"filter": [{"range": bounds}]}
        compound.get("filter", []).append({"exists": {"path": "name"}})
        sort: ProductSearchSort = {"price": -1, "name": 1}

        async def search(collection: ProductCollection) -> None:
            cursor = await collection.aggregate(pipeline)
            assert_type(cursor, TypedCursor[Product, ProductPath])
            await collection.aggregate([], [product_aggregation_step(metadata)])
    """)
    )
    invalid_queries = [
        '{"text": {"path": "nmae", "query": "phone"}}',
        '{"text": {"path": "name", "query": 42}}',
        '{"text": {"path": "name"}}',
        '{"compound": {"filter": [{"exists": {"path": "missing"}}]}}',
        '{"text": {"path": "details.title", "query": "phone"}}',
        '{"autocomplete": {"path": "name", "query": "ph", "tokenOrder": "invalid"}}',
        '{"text": {"path": "name", "query": "phone", "fuzzy": {"maxEdits": 3}}}',
        '{"text": {"path": "name", "query": "phone"}, "sort": {"missing": 1}}',
        '{"text": {"path": "name", "query": "phone"}, "returnStoredSource": True}',
        '{"text": {"path": "name", "query": "phone"}, "index": 1}',
        '{"txet": {"path": "name", "query": "phone"}}',
        '{"text": {"path": "name", "query": "phone"}, "returnScope": {"path": "details"}}',
    ]
    (tmp_path / "invalid.py").write_text(
        "from generated import ProductSearchStage, ProductPipelineStage, ProductSearchMetaStage\n"
        + "\n".join(
            f'bad{i}: ProductSearchStage = {{"$search": {query}}}'
            for i, query in enumerate(invalid_queries)
        )
        + '\nmetadata_pipeline: ProductPipelineStage = {"$searchMeta": {"exists": {"path": "name"}}}'
        + '\ninvalid_metadata: ProductSearchMetaStage = {"$searchMeta": {"exists": {"path": "missing"}}}'
        + '\nmetadata_sort: ProductSearchMetaStage = {"$searchMeta": {"exists": {"path": "name"}, "sort": {"price": 1}}}'
        + '\nmetadata_scope: ProductSearchMetaStage = {"$searchMeta": {"exists": {"path": "name"}, "returnScope": {"path": "missing"}}}'
    )
    config = tmp_path / "pyrightconfig.json"
    config.write_text(
        json.dumps(
            {
                "include": ["valid.py", "invalid.py", "generated.pyi"],
                "pythonVersion": "3.12",
                "typeCheckingMode": "standard",
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "basedpyright",
            "--outputjson",
            "--pythonpath",
            sys.executable,
            "--project",
            str(config),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    report = json.loads(result.stdout)
    diagnostics = report["generalDiagnostics"]
    unexpected = [d for d in diagnostics if Path(d["file"]).name != "invalid.py"]
    assert not unexpected, unexpected
    rejected_lines = {
        d["range"]["start"]["line"] for d in diagnostics if d["severity"] == "error"
    }
    assert rejected_lines == set(range(1, len(invalid_queries) + 5)), diagnostics


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
        check=False,
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
    assert '"name": StrOp,' in stub_content
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
        check=False,
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


def test_formatter_commands(tmp_path: Path):
    """--formatter commands should be invoked with generated file paths."""
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
            "--formatter",
            f"python3 -c \"import sys; open('{marker}', 'w').write('\\n'.join(sys.argv[1:]))\"",
        ],
        cwd=Path(__file__).parent.parent.parent,
        check=False,
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
    pyproject.write_text(
        dedent(f"""\
        [tool.typed-mongo-gen]

        [[tool.typed-mongo-gen.jobs]]
        sources = ["{models_file}"]
        output = "{output_file}"
    """)
    )

    result = subprocess.run(
        [sys.executable, "-m", "typed_mongo_gen.cli"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
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
    pyproject.write_text(
        dedent(f"""\
        [tool.typed-mongo-gen.defaults]
        formatter = ["python3 -c \\"import sys; open('{marker}', 'w').write('ok')\\""]

        [[tool.typed-mongo-gen.jobs]]
        sources = ["{models_file}"]
        output = "{output_file}"
    """)
    )

    result = subprocess.run(
        [sys.executable, "-m", "typed_mongo_gen.cli"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
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
        check=False,
    )

    assert result.returncode == 1
    assert "No [tool.typed-mongo-gen] config found" in result.stderr
