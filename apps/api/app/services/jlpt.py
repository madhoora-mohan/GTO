from sqlalchemy import case
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

# Difficulty rank — lower is easier. NULL maps to 6 (last/excluded).
JLPT_RANK = {"N5": 1, "N4": 2, "N3": 3, "N2": 4, "N1": 5}


def jlpt_order(column: ColumnElement[str | None] | InstrumentedAttribute[str | None]) -> ColumnElement[int]:
    """Case expression ordering a JLPT column easiest-first (N5..N1), NULL last."""
    return case(
        (column == "N5", 1),
        (column == "N4", 2),
        (column == "N3", 3),
        (column == "N2", 4),
        (column == "N1", 5),
        else_=6,
    )
