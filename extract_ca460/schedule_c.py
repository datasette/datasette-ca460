from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule C - Nonmonetary Contributions Received from FPPC Form 460. Each row is an \
in-kind contribution (goods/services, not cash). Parse all rows. Dates in YYYY-MM-DD format. \
Also extract the Schedule C Summary lines at the bottom."""


class NonmonetaryContribution(BaseModel):
    date_received: str = Field(description="YYYY-MM-DD")
    contributor_name: str
    contributor_street_address: Optional[str] = None
    contributor_city_state_zip: str
    contributor_code: Literal["IND", "COM", "OTH", "PTY", "SCC"]
    contributor_occupation_or_business: Optional[str] = None
    description_of_goods_or_services: str
    amount_fair_market_value: float
    cumulative_to_date_calendar_year: float
    per_election_to_date: Optional[float] = None


class ScheduleC(BaseModel):
    line_items: list[NonmonetaryContribution]
    summary_line_1_itemized_nonmonetary: float
    summary_line_2_unitemized_nonmonetary: float
    summary_line_3_total_nonmonetary: float
