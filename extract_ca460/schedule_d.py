from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule D - Summary of Expenditures Supporting/Opposing Other Candidates, Measures, \
and Committees from FPPC Form 460. Each row is an expenditure made to support or oppose another \
candidate/measure/committee. The "type of payment" is a checkbox (Monetary Contribution, \
Nonmonetary Contribution, Independent Expenditure). Dates in YYYY-MM-DD format. Also extract \
the 3 summary lines at bottom."""


class ScheduleDExpenditure(BaseModel):
    date: str = Field(description="YYYY-MM-DD")
    candidate_measure_or_committee_name: str
    office_district_or_jurisdiction: Optional[str] = None
    support_or_oppose: Literal["support", "oppose"]
    type_of_payment: Literal[
        "monetary_contribution",
        "nonmonetary_contribution",
        "independent_expenditure",
    ]
    description: Optional[str] = None
    amount_this_period: float
    cumulative_to_date_calendar_year: float
    per_election_to_date: Optional[float] = None


class ScheduleD(BaseModel):
    line_items: list[ScheduleDExpenditure]
    summary_line_1_itemized: float
    summary_line_2_unitemized: float
    summary_line_3_total: float
