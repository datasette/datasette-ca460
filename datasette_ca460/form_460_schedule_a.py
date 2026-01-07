from pydantic import BaseModel
from typing import List, Optional

PROMPT = """

  Parse the given CA Form 460 Schedule into JSON.

  For any dates, provide the date in the format YYYY-MM-DD.
  If a field is not applicable, use `null` for the value.
"""


class Form460ScheduleALineItem(BaseModel):
    date_received: str
    full_name: str
    city: str
    state: str
    zipcode: str
    contributor_code: str
    occupation: str
    employer: str
    amount_this_period: float
    amount_cumulative_calendar_year: float
    amount_per_election_code: Optional[str]
    amount_per_election: Optional[float]


class Form460ScheduleA(BaseModel):
    line_items: List[Form460ScheduleALineItem]
