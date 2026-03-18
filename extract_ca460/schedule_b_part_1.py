from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule B Part 1 - Loans Received from FPPC Form 460. This page has loan detail rows \
at the top and a Schedule B Summary at the bottom. Dates in YYYY-MM-DD format. For each loan \
row, columns (a) through (g) map to the fields below. The "paid or forgiven" field is a \
checkbox. The summary has 3 numbered lines."""


class LoanReceived(BaseModel):
    lender_name: str
    lender_street_address: Optional[str] = None
    lender_city_state_zip: str
    lender_code: Optional[Literal["IND", "COM", "OTH", "PTY", "SCC"]] = None
    lender_occupation_or_business: Optional[str] = None
    col_a_outstanding_balance_beginning: float
    col_b_amount_received_this_period: float
    col_c_amount_paid_or_forgiven: float
    col_c_paid_or_forgiven: Optional[Literal["paid", "forgiven"]] = None
    col_d_outstanding_balance_close: float
    col_e_interest_paid_this_period: float
    col_e_interest_rate: Optional[str] = None
    col_f_original_amount_of_loan: float
    col_g_cumulative_contributions_to_date: float
    date_due: Optional[str] = Field(None, description="YYYY-MM-DD")
    date_incurred: Optional[str] = Field(None, description="YYYY-MM-DD")


class ScheduleBPart1(BaseModel):
    line_items: list[LoanReceived]
    summary_line_1_loans_received_this_period: float
    summary_line_2_loans_paid_or_forgiven: float
    summary_line_3_net_change: float = Field(description="May be negative")
