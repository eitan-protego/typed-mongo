"""Declarative MongoDB operator type definitions.

Each operator is a generic TypedDict whose keys use MongoDB ``$``-operator
names.  The ``Op[T]`` union combines every operator with raw ``T`` for use
as the value type in generated query TypedDicts.

Usage — callers write plain dict literals; the type checker validates::

    filter: CaseQuery = {"summary.payer": {"$in": ["Aetna", "BCBS"]}}
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypedDict, cast

# --- Generic operators (parameterized by field value type T) ---
# Unfortunately, TypedDict can either be generic (class syntax) or contain keys
# that are not valid field names (function call syntax) but not both.

type Eq[T] = Mapping[Literal["$eq"], T]
type Ne[T] = Mapping[Literal["$ne"], T]
type In[T] = Mapping[Literal["$in"], Sequence[T]]
type Nin[T] = Mapping[Literal["$nin"], Sequence[T]]
type Gt[T] = Mapping[Literal["$gt"], T]
type Gte[T] = Mapping[Literal["$gte"], T]
type Lt[T] = Mapping[Literal["$lt"], T]
type Lte[T] = Mapping[Literal["$lte"], T]
type SelfOp[T] = Mapping[Literal["$eq", "$ne", "$gt", "$gte", "$lt", "$lte"], T]
type ListOp[T] = Mapping[Literal["$in", "$nin"], Sequence[T]]


# --- Non-generic operators ---

Exists = TypedDict("Exists", {"$exists": bool})
Regex = TypedDict("Regex", {"$regex": str})
ElemMatch = TypedDict("ElemMatch", {"$elemMatch": Mapping[str, Any]})
NonGenericOp = TypedDict(
    "NonGenericOp", {"$exists": bool, "$regex": str, "$elemMatch": Mapping[str, Any]}
)
# Range: optional comparison keys (e.g. {"$gte": 10, "$lte": 100})
Range = TypedDict(
    "Range",
    {"$gte": Any, "$gt": Any, "$lt": Any, "$lte": Any},
    total=False,
)

# --- Union of all operators ---
type NontrivialOp[T] = SelfOp[T] | ListOp[T] | Exists | Regex | ElemMatch
type Op[T] = T | NontrivialOp[T]
"""
Due to limitations of Python's type system, Op cannot match a predicate that combines
different types of operators. If you need to use both generic and non-generic operators
or combined the list-valued and self-valued operators, you will need to combine
them using the combine_ops function.
"""


def combine_ops[T](*ops: NontrivialOp[T]) -> Op[T]:
    return cast(Op[T], {k: v for op in ops for k, v in op.items()})
