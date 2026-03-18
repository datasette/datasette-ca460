from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule A - Monetary Contributions Received from FPPC Form 460. Each row is a \
contribution from a donor. Parse all contributor rows on the page. Dates in YYYY-MM-DD format. \
The contributor code is a checkbox (IND, COM, OTH, PTY, SCC) -- pick the one that is checked."""


class ScheduleAContribution(BaseModel):
    date_received: str = Field(description="YYYY-MM-DD")
    contributor_name: str
    contributor_street_address: Optional[str] = None
    contributor_city_state_zip: str
    contributor_code: Literal["IND", "COM", "OTH", "PTY", "SCC"]
    contributor_occupation_or_business: Optional[str] = Field(
        None,
        description="If IND, their occupation and employer. If self-employed, the business name.",
    )
    amount_received_this_period: float
    cumulative_to_date_calendar_year: float
    per_election_to_date: Optional[float] = None


class ScheduleA(BaseModel):
    line_items: list[ScheduleAContribution]
    subtotal: Optional[float] = None
