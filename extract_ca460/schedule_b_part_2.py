from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule B Part 2 - Loan Guarantors from FPPC Form 460. Each row is a guarantor for a \
loan. Dates in YYYY-MM-DD format."""


class LoanGuarantor(BaseModel):
    guarantor_name: str
    guarantor_street_address: Optional[str] = None
    guarantor_city_state_zip: str
    guarantor_code: Optional[Literal["IND", "COM", "OTH", "PTY", "SCC"]] = None
    guarantor_occupation_or_business: Optional[str] = None
    loan_lender: str
    loan_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    amount_guaranteed_this_period: float
    cumulative_to_date: float
    calendar_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    per_election: Optional[float] = None
    balance_outstanding_to_date: float


class ScheduleBPart2(BaseModel):
    line_items: list[LoanGuarantor]
    subtotal: Optional[float] = None
