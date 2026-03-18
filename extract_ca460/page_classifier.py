from typing import Literal

from pydantic import BaseModel

PROMPT = """\
Classify this page from a California FPPC Form 460 (Recipient Committee Campaign Statement). \
Look at the schedule label in the top-left corner and the header area to determine the page type."""


class PageClassification(BaseModel):
    page_type: Literal[
        "cover-page-part-1",
        "cover-page-part-2",
        "summary-page",
        "schedule-a",
        "schedule-b-part-1",
        "schedule-b-part-2",
        "schedule-c",
        "schedule-d",
        "schedule-e",
        "schedule-f",
        "schedule-g",
        "schedule-h",
        "schedule-i",
        "unknown",
    ]
