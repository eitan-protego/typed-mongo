"""Tests for MongoDB operator TypedDict definitions."""



def test_import_operators():
    """Test that all operator types can be imported."""
    from typed_mongo.operators import (
        Eq,
        Ne,
        In,
        Nin,
        Gt,
        Gte,
        Lt,
        Lte,
        Range,
        Exists,
        Regex,
        ElemMatch,
        Op,
    )

    # Basic smoke test - ensure they exist
    assert Eq is not None
    assert Ne is not None
    assert In is not None
    assert Nin is not None
    assert Gt is not None
    assert Gte is not None
    assert Lt is not None
    assert Lte is not None
    assert Range is not None
    assert Exists is not None
    assert Regex is not None
    assert ElemMatch is not None
    assert Op is not None


def test_eq_operator_type():
    """Test Eq operator with concrete type."""
    from typed_mongo.operators import Eq

    # Runtime construction test
    eq_query: Eq[str] = {"$eq": "test"}
    assert eq_query["$eq"] == "test"

    eq_int: Eq[int] = {"$eq": 42}
    assert eq_int["$eq"] == 42


def test_ne_operator_type():
    """Test Ne operator with concrete type."""
    from typed_mongo.operators import Ne

    ne_query: Ne[str] = {"$ne": "test"}
    assert ne_query["$ne"] == "test"


def test_in_operator_type():
    """Test In operator with list type."""
    from typed_mongo.operators import In

    in_query: In[str] = {"$in": ["a", "b", "c"]}
    assert len(in_query["$in"]) == 3

    in_int: In[int] = {"$in": [1, 2, 3]}
    assert in_int["$in"] == [1, 2, 3]


def test_nin_operator_type():
    """Test Nin operator with list type."""
    from typed_mongo.operators import Nin

    nin_query: Nin[str] = {"$nin": ["x", "y"]}
    assert len(nin_query["$nin"]) == 2


def test_comparison_operators():
    """Test Gt, Gte, Lt, Lte operators."""
    from typed_mongo.operators import Gt, Gte, Lt, Lte

    gt_query: Gt[int] = {"$gt": 10}
    assert gt_query["$gt"] == 10

    gte_query: Gte[int] = {"$gte": 10}
    assert gte_query["$gte"] == 10

    lt_query: Lt[int] = {"$lt": 100}
    assert lt_query["$lt"] == 100

    lte_query: Lte[int] = {"$lte": 100}
    assert lte_query["$lte"] == 100


def test_range_operator():
    """Test Range operator with partial keys."""
    from typed_mongo.operators import Range

    # Range supports various combinations (total=False)
    range_full: Range = {"$gte": 10, "$lte": 100}
    assert range_full["$gte"] == 10
    assert range_full["$lte"] == 100

    range_partial: Range = {"$gt": 5}
    assert range_partial["$gt"] == 5


def test_exists_operator():
    """Test Exists operator (non-generic)."""
    from typed_mongo.operators import Exists

    exists_true: Exists = {"$exists": True}
    assert exists_true["$exists"] is True

    exists_false: Exists = {"$exists": False}
    assert exists_false["$exists"] is False


def test_regex_operator():
    """Test Regex operator (non-generic)."""
    from typed_mongo.operators import Regex

    regex_query: Regex = {"$regex": "^test.*"}
    assert regex_query["$regex"] == "^test.*"


def test_elem_match_operator():
    """Test ElemMatch operator (non-generic)."""
    from typed_mongo.operators import ElemMatch

    elem_match: ElemMatch = {"$elemMatch": {"status": "active"}}
    assert elem_match["$elemMatch"]["status"] == "active"


def test_op_union_with_raw_value():
    """Test that Op[T] includes raw T value."""
    from typed_mongo.operators import Op

    # Op[str] should accept raw string
    value: Op[str] = "plain_value"
    assert value == "plain_value"


def test_op_union_with_eq():
    """Test that Op[T] includes Eq[T]."""
    from typed_mongo.operators import Op

    value: Op[str] = {"$eq": "test"}
    assert value["$eq"] == "test"


def test_op_union_with_in():
    """Test that Op[T] includes In[T]."""
    from typed_mongo.operators import Op

    value: Op[str] = {"$in": ["a", "b"]}
    assert len(value["$in"]) == 2


def test_op_union_with_comparison():
    """Test that Op[T] includes comparison operators."""
    from typed_mongo.operators import Op

    gt_value: Op[int] = {"$gt": 10}
    assert gt_value["$gt"] == 10

    range_value: Op[int] = {"$gte": 5, "$lte": 15}
    assert range_value["$gte"] == 5


def test_op_union_with_exists():
    """Test that Op[T] includes Exists."""
    from typed_mongo.operators import Op

    value: Op[str] = {"$exists": True}
    assert value["$exists"] is True


def test_op_union_with_regex():
    """Test that Op[T] includes Regex."""
    from typed_mongo.operators import Op

    value: Op[str] = {"$regex": "pattern"}
    assert value["$regex"] == "pattern"


def test_practical_query_example():
    """Test a practical query example combining operators."""
    from typed_mongo.operators import Op

    # Simulate a field that can use various operators
    status_filter: Op[str] = {"$in": ["active", "pending"]}
    age_filter: Op[int] = {"$gte": 18, "$lt": 65}
    name_filter: Op[str] = "John"
    email_exists: Op[str] = {"$exists": True}

    assert status_filter["$in"] == ["active", "pending"]
    assert age_filter["$gte"] == 18
    assert age_filter["$lt"] == 65
    assert name_filter == "John"
    assert email_exists["$exists"] is True


def test_module_docstring():
    """Test that the module has proper documentation."""
    from typed_mongo import operators

    assert operators.__doc__ is not None
    assert "MongoDB" in operators.__doc__
    assert "operator" in operators.__doc__.lower()
