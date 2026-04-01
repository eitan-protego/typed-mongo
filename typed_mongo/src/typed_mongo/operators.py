"""Declarative MongoDB operator type definitions.

Each operator is a generic TypedDict whose keys use MongoDB ``$``-operator
names.  The ``Op[T]`` union combines every operator with raw ``T`` for use
as the value type in generated query TypedDicts.

Usage — callers write plain dict literals; the type checker validates::

    filter: CaseQuery = {"summary.payer": {"$in": ["Aetna", "BCBS"]}}
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, NotRequired, TypedDict, cast

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

# --- Union of all operators ---
type NontrivialOp[T] = SelfOp[T] | ListOp[T] | Exists | Regex | ElemMatch
type Op[T] = T | NontrivialOp[T]
"""
Due to limitations of Python's type system, Op cannot match a predicate that combines
different types of operators. If you need to use both generic and non-generic operators
or combined the list-valued and self-valued operators, you will need to combine
them using the combine_ops function.
"""


# --- Aggregation expression operators (for pipeline updates) ---

type AggExprOp = Literal[
    "$add",
    "$subtract",
    "$multiply",
    "$divide",
    "$mod",
    "$concat",
    "$substr",
    "$toLower",
    "$toUpper",
    "$trim",
    "$cond",
    "$ifNull",
    "$switch",
    "$arrayElemAt",
    "$first",
    "$last",
    "$size",
    "$filter",
    "$map",
    "$mergeObjects",
    "$objectToArray",
    "$arrayToObject",
    "$toString",
    "$toInt",
    "$toDouble",
    "$toBool",
    "$type",
    "$literal",
    "$dateToString",
    "$dateFromString",
    "$abs",
    "$ceil",
    "$floor",
    "$round",
    "$max",
    "$min",
    "$avg",
    "$sum",
    "$and",
    "$or",
    "$not",
    "$eq",
    "$ne",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$in",
    "$setUnion",
    "$setIntersection",
]


def combine_ops[T](*ops: NontrivialOp[T]) -> Op[T]:
    # Cast needed: merging TypedDicts via comprehension produces dict, not a union member
    return cast(Op[T], {k: v for op in ops for k, v in op.items()})


# --- Aggregation pipeline stage types ---
# Structurally validated stages (also have model-specific codegen helpers)
# NOTE: These intentionally do NOT use closed=True because operators.py uses
# typing.TypedDict (not typing_extensions.TypedDict). PEP 728 closed/extra_items
# is only needed in codegen'd .pyi stubs which use typing_extensions.TypedDict.


GroupStage = TypedDict("GroupStage", {"$group": dict[str, Any]})

BucketStageValue = TypedDict(
    "BucketStageValue",
    {
        "groupBy": Any,
        "boundaries": list[Any],
        "default": Any,
        "output": NotRequired[dict[str, Any]],
    },
)
BucketStage = TypedDict("BucketStage", {"$bucket": BucketStageValue})


class BucketAutoStageValue(TypedDict):
    groupBy: Any
    buckets: int


BucketAutoStage = TypedDict("BucketAutoStage", {"$bucketAuto": BucketAutoStageValue})

UnwindStage = TypedDict("UnwindStage", {"$unwind": str | dict[str, Any]})

ProjectStage = TypedDict("ProjectStage", {"$project": dict[str, Any]})

LookupStageValue = TypedDict(
    "LookupStageValue",
    {
        "from": str,
        "localField": str,
        "foreignField": str,
        "as": str,
    },
)
LookupStage = TypedDict("LookupStage", {"$lookup": LookupStageValue})

# Minimally annotated stages
MatchStage = TypedDict("MatchStage", {"$match": dict[str, Any]})
SortStage = TypedDict("SortStage", {"$sort": dict[str, int]})
LimitStage = TypedDict("LimitStage", {"$limit": int})
SkipStage = TypedDict("SkipStage", {"$skip": int})
SetStage = TypedDict("SetStage", {"$set": dict[str, Any]})
AddFieldsStage = TypedDict("AddFieldsStage", {"$addFields": dict[str, Any]})
UnsetStage = TypedDict("UnsetStage", {"$unset": str | list[str]})
CountStage = TypedDict("CountStage", {"$count": str})
ReplaceRootStage = TypedDict("ReplaceRootStage", {"$replaceRoot": dict[str, Any]})
ReplaceWithStage = TypedDict("ReplaceWithStage", {"$replaceWith": dict[str, Any]})
OutStage = TypedDict("OutStage", {"$out": str | dict[str, Any]})
MergeStage = TypedDict("MergeStage", {"$merge": str | dict[str, Any]})
FacetStage = TypedDict("FacetStage", {"$facet": dict[str, list[Any]]})
GraphLookupStage = TypedDict("GraphLookupStage", {"$graphLookup": dict[str, Any]})
RedactStage = TypedDict("RedactStage", {"$redact": dict[str, Any]})
SampleStage = TypedDict("SampleStage", {"$sample": dict[str, int]})
UnionWithStage = TypedDict("UnionWithStage", {"$unionWith": str | dict[str, Any]})
SortByCountStage = TypedDict("SortByCountStage", {"$sortByCount": str | dict[str, Any]})
GeoNearStage = TypedDict("GeoNearStage", {"$geoNear": dict[str, Any]})
DensifyStage = TypedDict("DensifyStage", {"$densify": dict[str, Any]})
FillStage = TypedDict("FillStage", {"$fill": dict[str, Any]})
DocumentsStage = TypedDict("DocumentsStage", {"$documents": list[dict[str, Any]]})
SetWindowFieldsStage = TypedDict(
    "SetWindowFieldsStage", {"$setWindowFields": dict[str, Any]}
)
ChangeStreamStage = TypedDict("ChangeStreamStage", {"$changeStream": dict[str, Any]})
CollStatsStage = TypedDict("CollStatsStage", {"$collStats": dict[str, Any]})
CurrentOpStage = TypedDict("CurrentOpStage", {"$currentOp": dict[str, Any]})
IndexStatsStage = TypedDict("IndexStatsStage", {"$indexStats": dict[str, Any]})
ListSessionsStage = TypedDict("ListSessionsStage", {"$listSessions": dict[str, Any]})
PlanCacheStatsStage = TypedDict(
    "PlanCacheStatsStage", {"$planCacheStats": dict[str, Any]}
)
SearchStage = TypedDict("SearchStage", {"$search": dict[str, Any]})
SearchMetaStage = TypedDict("SearchMetaStage", {"$searchMeta": dict[str, Any]})

type AggregationStep = (
    GroupStage
    | BucketStage
    | BucketAutoStage
    | UnwindStage
    | ProjectStage
    | LookupStage
    | MatchStage
    | SortStage
    | LimitStage
    | SkipStage
    | SetStage
    | AddFieldsStage
    | UnsetStage
    | CountStage
    | ReplaceRootStage
    | ReplaceWithStage
    | OutStage
    | MergeStage
    | FacetStage
    | GraphLookupStage
    | RedactStage
    | SampleStage
    | UnionWithStage
    | SortByCountStage
    | GeoNearStage
    | DensifyStage
    | FillStage
    | DocumentsStage
    | SetWindowFieldsStage
    | ChangeStreamStage
    | CollStatsStage
    | CurrentOpStage
    | IndexStatsStage
    | ListSessionsStage
    | PlanCacheStatsStage
    | SearchStage
    | SearchMetaStage
)
