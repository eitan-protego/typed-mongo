"""Tests for MongoDB operator TypedDict definitions."""

from typed_mongo.operators import (
    ElemMatch,
    Eq,
    Exists,
    Gt,
    Gte,
    In,
    Lt,
    Lte,
    Ne,
    Nin,
    Op,
    Regex,
)


def test_eq_operator_type():
    """Test Eq operator with concrete type."""

    # Runtime construction test
    eq_query: Eq[str] = {"$eq": "test"}
    assert eq_query["$eq"] == "test"

    eq_int: Eq[int] = {"$eq": 42}
    assert eq_int["$eq"] == 42


def test_ne_operator_type():
    """Test Ne operator with concrete type."""

    ne_query: Ne[str] = {"$ne": "test"}
    assert ne_query["$ne"] == "test"


def test_in_operator_type():
    """Test In operator with list type."""

    in_query: In[str] = {"$in": ["a", "b", "c"]}
    assert len(in_query["$in"]) == 3

    in_int: In[int] = {"$in": [1, 2, 3]}
    assert in_int["$in"] == [1, 2, 3]


def test_nin_operator_type():
    """Test Nin operator with list type."""

    nin_query: Nin[str] = {"$nin": ["x", "y"]}
    assert len(nin_query["$nin"]) == 2


def test_comparison_operators():
    """Test Gt, Gte, Lt, Lte operators."""

    gt_query: Gt[int] = {"$gt": 10}
    assert gt_query["$gt"] == 10

    gte_query: Gte[int] = {"$gte": 10}
    assert gte_query["$gte"] == 10

    lt_query: Lt[int] = {"$lt": 100}
    assert lt_query["$lt"] == 100

    lte_query: Lte[int] = {"$lte": 100}
    assert lte_query["$lte"] == 100


def test_exists_operator():
    """Test Exists operator (non-generic)."""

    exists_true: Exists = {"$exists": True}
    assert exists_true["$exists"] is True

    exists_false: Exists = {"$exists": False}
    assert exists_false["$exists"] is False


def test_regex_operator():
    """Test Regex operator (non-generic)."""

    regex_query: Regex = {"$regex": "^test.*"}
    assert regex_query["$regex"] == "^test.*"


def test_elem_match_operator():
    """Test ElemMatch operator (non-generic)."""

    elem_match: ElemMatch = {"$elemMatch": {"status": "active"}}
    assert elem_match["$elemMatch"]["status"] == "active"


def test_op_union_with_raw_value():
    """Test that Op[T] includes raw T value."""

    # Op[str] should accept raw string
    value: Op[str] = "plain_value"
    assert value == "plain_value"


def test_op_union_with_eq():
    """Test that Op[T] includes Eq[T]."""

    value: Op[str] = {"$eq": "test"}
    assert value["$eq"] == "test"


def test_op_union_with_in():
    """Test that Op[T] includes In[T]."""

    value: Op[str] = {"$in": ["a", "b"]}
    assert len(value["$in"]) == 2


def test_op_union_with_comparison():
    """Test that Op[T] includes comparison operators."""

    gt_value: Op[int] = {"$gt": 10}
    assert gt_value["$gt"] == 10

    range_value: Op[int] = {"$gte": 5, "$lte": 15}
    assert range_value["$gte"] == 5


def test_op_union_with_exists():
    """Test that Op[T] includes Exists."""

    value: Op[str] = {"$exists": True}
    assert value["$exists"] is True


def test_op_union_with_regex():
    """Test that Op[T] includes Regex."""

    value: Op[str] = {"$regex": "pattern"}
    assert value["$regex"] == "pattern"


def test_practical_query_example():
    """Test a practical query example combining operators."""

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
