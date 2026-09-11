"""Shared server-side pagination for admin list endpoints.

The admin console must never receive an unbounded slice of a table: production
already holds 71k provider sync runs and 2.7k notification deliveries, and an
earlier audit found lists that were silently capped at 100/200 rows with no
`offset`, so older rows were unreachable from the UI.

Two rules for every endpoint that adopts this helper:

* The **response keys are unchanged** (`users`, `notifications`, `runs`, ...).
  New keys (`total`, `limit`, `offset`) are additive, so an existing client that
  ignores them keeps working. A client that sent no parameters still gets the
  previous behaviour, expressed as an explicit default page.
* `limit` is always bounded by ``PageParams.MAX_LIMIT`` and `offset` is always
  non-negative, so a hostile or buggy caller cannot ask for the whole table.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Query
from sqlalchemy.orm import Query as OrmQuery


@dataclass(frozen=True)
class PageParams:
    """A validated page request."""

    limit: int
    offset: int

    #: Hard ceiling for any admin list. Chosen to match the largest existing
    #: page size in the console (the credit accounts list) so no single response
    #: grows beyond what the UI already renders comfortably.
    MAX_LIMIT = 100

    #: Default when a caller omits ``limit``. Chosen to match the largest cap the
    #: console already applied (100 rows) so an existing client that sends no
    #: parameters behaves exactly as before, while a new client can page.
    DEFAULT_LIMIT = 100

    @property
    def page(self) -> int:
        """1-based page number, for display only."""
        return (self.offset // self.limit) + 1 if self.limit else 1


def page_params(
    limit: int = Query(default=PageParams.DEFAULT_LIMIT, ge=1, le=PageParams.MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> PageParams:
    """FastAPI dependency: validated, bounded pagination parameters."""
    return PageParams(limit=limit, offset=offset)


def paginate(query: OrmQuery, page: PageParams) -> tuple[list, int]:
    """Apply a stable order-independent slice plus a matching total count.

    The caller supplies its own ``order_by``; the count is taken from the same
    filtered query, so a list and its ``total`` always describe the same set.
    """
    total = query.order_by(None).count()
    rows = query.limit(page.limit).offset(page.offset).all()
    return rows, total


def page_meta(page: PageParams, total: int) -> dict[str, int | bool]:
    """The additive pagination block returned next to every list."""
    return {
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "page": page.page,
        "has_more": page.offset + page.limit < total,
    }
