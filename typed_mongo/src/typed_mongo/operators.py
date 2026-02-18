"""Declarative MongoDB operator type definitions.

Each operator is a generic TypedDict whose keys use MongoDB ``$``-operator
names.  The ``Op[T]`` union combines every operator with raw ``T`` for use
as the value type in generated query TypedDicts.

Usage — callers write plain dict literals; the type checker validates::

    filter: CaseQuery = {"summary.payer": {"$in": ["Aetna", "BCBS"]}}
"""

from typing import Any, Literal, TypedDict, cast

# --- Generic operators (parameterized by field value type T) ---
# Unfortunately, TypedDict can either be generic (class syntax) or contain keys
# that are not valid field names (function call syntax) but not both.

type Eq[T] = dict[Literal["$eq"], T]
type Ne[T] = dict[Literal["$ne"], T]
type In[T] = dict[Literal["$in"], list[T]]
type Nin[T] = dict[Literal["$nin"], list[T]]
type Gt[T] = dict[Literal["$gt"], T]
type Gte[T] = dict[Literal["$gte"], T]
type Lt[T] = dict[Literal["$lt"], T]
type Lte[T] = dict[Literal["$lte"], T]
type SelfOp[T] = dict[Literal["$eq", "$ne", "$gt", "$gte", "$lt", "$lte"], T]
type ListOp[T] = dict[Literal["$in", "$nin"], list[T]]


# --- Non-generic operators ---

Exists = TypedDict("Exists", {"$exists": bool})
Regex = TypedDict("Regex", {"$regex": str})
ElemMatch = TypedDict("ElemMatch", {"$elemMatch": dict[str, Any]})
NonGenericOp = TypedDict(
    "NonGenericOp", {"$exists": bool, "$regex": str, "$elemMatch": dict[str, Any]}
)

# --- Union of all operators ---
type NontrivialOp[T] = SelfOp[T] | ListOp[T] | NonGenericOp
type Op[T] = T | NontrivialOp[T]
"""
Due to limitations of Python's type system, Op cannot match a predicate that combines
different types of operators. If you need to use both generic and non-generic operators
or combined the list-valued and self-valued operators, you will need to combine
them using the combine_ops function.
"""


def combine_ops[T](*ops: NontrivialOp[T]) -> Op[T]:
    return cast(Op[T], {k: v for op in ops for k, v in op.items()})
