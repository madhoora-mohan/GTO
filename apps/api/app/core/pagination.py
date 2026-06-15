# WHAT: Shared pagination params for list endpoints.
# WHY:  Every list endpoint (kana, kanji, vocab, sentences, components) takes
#       the same `page` / `page_size` query params and computes the same
#       OFFSET — this keeps that logic in one place.

from dataclasses import dataclass

from fastapi import Query


@dataclass
class PageParams:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


async def page_params(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PageParams:
    return PageParams(page=page, page_size=page_size)
