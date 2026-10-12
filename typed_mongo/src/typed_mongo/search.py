"""Shared Atlas Search payloads; generated types bind paths and recursive clauses.

As with query operators, values are not correlated with a particular field's
type. MongoDB validates index configuration and mutually exclusive options.
"""

from collections.abc import Mapping
from typing import Any, Literal, NotRequired, TypedDict, cast


class SearchWildcardPath(TypedDict):
    wildcard: str


class SearchMultiPath[Path: str](TypedDict):
    value: Path
    multi: str


type SearchPath[Path: str] = (
    Path
    | SearchWildcardPath
    | SearchMultiPath[Path]
    | list[Path | SearchWildcardPath | SearchMultiPath[Path]]
)


class SearchFuzzy(TypedDict, total=False):
    maxEdits: Literal[1, 2]
    prefixLength: int
    maxExpansions: int


class _SearchScored(TypedDict, total=False):
    # shortcut: score functions remain open, deepen when their schemas are needed.
    score: dict[str, Any]


class SearchText[Path: str](_SearchScored):
    query: str | list[str]
    path: SearchPath[Path]
    fuzzy: NotRequired[SearchFuzzy]
    matchCriteria: NotRequired[Literal["any", "all"]]
    synonyms: NotRequired[str]


class SearchAutocomplete[Path: str](_SearchScored):
    query: str | list[str]
    path: Path
    fuzzy: NotRequired[SearchFuzzy]
    tokenOrder: NotRequired[Literal["any", "sequential"]]


class SearchPhrase[Path: str](_SearchScored):
    query: str | list[str]
    path: SearchPath[Path]
    slop: NotRequired[int]
    synonyms: NotRequired[str]


class SearchPattern[Path: str](_SearchScored):
    query: str | list[str]
    path: SearchPath[Path]
    allowAnalyzedField: NotRequired[bool]


class SearchQueryString[Path: str](_SearchScored):
    defaultPath: Path
    query: str


class SearchEquals[Path: str](_SearchScored):
    path: Path
    value: Any
    doesNotAffect: NotRequired[str | list[str]]


class SearchIn[Path: str](_SearchScored):
    path: SearchPath[Path]
    value: Any
    doesNotAffect: NotRequired[str | list[str]]


class SearchExists[Path: str](_SearchScored):
    path: Path


class SearchRange[Path: str](_SearchScored):
    path: Path | list[Path]
    gt: NotRequired[Any]
    gte: NotRequired[Any]
    lt: NotRequired[Any]
    lte: NotRequired[Any]
    doesNotAffect: NotRequired[str | list[str]]


class SearchNear[Path: str](_SearchScored):
    path: Path | list[Path]
    origin: Any
    pivot: float


class SearchCompound[Clause](_SearchScored, total=False):
    must: list[Clause]
    mustNot: list[Clause]
    should: list[Clause]
    filter: list[Clause]
    minimumShouldMatch: int
    doesNotAffect: str | list[str]


class SearchEmbeddedDocument[Path: str, Clause](_SearchScored):
    path: Path
    operator: Clause


class SearchHighlight[Path: str](TypedDict):
    path: SearchPath[Path]
    maxCharsToExamine: NotRequired[int]
    maxNumPassages: NotRequired[int]


class SearchCount(TypedDict, total=False):
    type: Literal["lowerBound", "total"]
    threshold: NotRequired[int]


SearchScoreSort = TypedDict(
    "SearchScoreSort",
    {"$meta": Literal["searchScore"], "order": NotRequired[Literal[1, -1]]},
)


class SearchSortOptions(TypedDict):
    order: Literal[1, -1]
    noData: NotRequired[Literal["highest", "lowest"]]


type SearchSortValue = Literal[1, -1] | SearchSortOptions | SearchScoreSort
type SearchSort[Path: str] = (
    Mapping[Path, SearchSortValue] | Mapping[str, SearchScoreSort]
)


def combine_search_sort[Path: str](
    fields: Mapping[Path, SearchSortValue], scores: Mapping[str, SearchScoreSort]
) -> SearchSort[Path]:
    """Combine checked field sorts with score sorts under arbitrary output names."""
    # A mixed mapping cannot be expressed by the union, just as with combine_ops.
    return cast(SearchSort[Path], {**fields, **scores})


class _SearchCommonOptions(TypedDict, total=False):
    index: str
    count: SearchCount
    concurrent: bool
    facet: dict[str, Any]


class SearchStageOptions[Path: str](_SearchCommonOptions, total=False):
    highlight: SearchHighlight[Path]
    scoreDetails: bool
    searchAfter: str
    searchBefore: str
    sort: SearchSort[Path]
    returnStoredSource: Literal[False]
    searchNodePreference: Mapping[Literal["key"], str]


class SearchMetaOptions[Path: str](_SearchCommonOptions, total=False):
    returnScope: Mapping[Literal["path"], Path]
    returnStoredSource: bool
