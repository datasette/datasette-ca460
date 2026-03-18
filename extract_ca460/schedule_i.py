from typing import Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule I - Miscellaneous Increases to Cash from FPPC Form 460. This captures \
non-contribution receipts (e.g., interest, refunds). Also extract the Schedule I Summary at \
the bottom. Dates in YYYY-MM-DD format."""


class MiscIncrease(BaseModel):
    date_received: str = Field(description="YYYY-MM-DD")
    source_name: str
    source_address: Optional[str] = None
    description_of_receipt: str
    amount_increase_to_cash: float


class ScheduleI(BaseModel):
    line_items: list[MiscIncrease]
    summary_line_1_itemized_increases: float
    summary_line_2_unitemized_increases: float
    summary_line_3_interest_on_loans: float
    summary_line_4_total_miscellaneous: float
