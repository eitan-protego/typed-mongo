"""Declarative MongoDB operator type definitions.

Each operator is a generic TypedDict whose keys use MongoDB ``$``-operator
names.  The ``Op[T]`` union combines every operator with raw ``T`` for use
as the value type in generated query TypedDicts.

Usage — callers write plain dict literals; the type checker validates::

    filter: CaseQuery = {"summary.payer": {"$in": ["Aetna", "BCBS"]}}
"""

from typing import Any, TypedDict

# --- Generic operators (parameterized by field value type T) ---

type Eq[T] = TypedDict("Eq", {"$eq": T})
type Ne[T] = TypedDict("Ne", {"$ne": T})
type In[T] = TypedDict("In", {"$in": list[T]})
type Nin[T] = TypedDict("Nin", {"$nin": list[T]})
type Gt[T] = TypedDict("Gt", {"$gt": T})
type Gte[T] = TypedDict("Gte", {"$gte": T})
type Lt[T] = TypedDict("Lt", {"$lt": T})
type Lte[T] = TypedDict("Lte", {"$lte": T})
type Range[T] = TypedDict(
    "Range", {"$gte": T, "$gt": T, "$lte": T, "$lt": T}, total=False
)

# --- Non-generic operators ---

Exists = TypedDict("Exists", {"$exists": bool})
Regex = TypedDict("Regex", {"$regex": str})
ElemMatch = TypedDict("ElemMatch", {"$elemMatch": dict[str, Any]})

# --- Union of all operators ---

type Op[T] = (
    T
    | Eq[T]
    | Ne[T]
    | In[T]
    | Nin[T]
    | Gt[T]
    | Gte[T]
    | Lt[T]
    | Lte[T]
    | Range[T]
    | Exists
    | Regex
    | ElemMatch
)
