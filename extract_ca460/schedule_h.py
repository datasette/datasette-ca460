from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule H - Loans Made to Others from FPPC Form 460. Each row is a loan the committee \
made to another entity. Columns (a)-(g) mirror Schedule B Part 1 but from the lender's \
perspective. Dates in YYYY-MM-DD format."""


class LoanMade(BaseModel):
    recipient_name: str
    recipient_street_address: Optional[str] = None
    recipient_city_state_zip: str
    recipient_occupation_or_business: Optional[str] = None
    col_a_outstanding_balance_beginning: float
    col_b_amount_loaned_this_period: float
    col_c_repayment_or_forgiveness_this_period: float
    col_c_paid_or_forgiven: Optional[Literal["paid", "forgiven"]] = None
    col_d_outstanding_balance_close: float
    col_e_interest_received: float
    col_e_interest_rate: Optional[str] = None
    col_f_original_amount_of_loan: float
    col_g_cumulative_loans_to_date: float
    date_due: Optional[str] = Field(None, description="YYYY-MM-DD")
    date_incurred: Optional[str] = Field(None, description="YYYY-MM-DD")


class ScheduleH(BaseModel):
    line_items: list[LoanMade]
