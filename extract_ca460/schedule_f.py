from typing import Optional

from pydantic import BaseModel

PROMPT = """\
Extract Schedule F - Accrued Expenses (Unpaid Bills) from FPPC Form 460. This tracks bills the \
committee has received but not yet paid. Uses the same 3-letter expense codes as Schedule E. \
Also extract the Schedule F Summary at the bottom. Dates in YYYY-MM-DD format."""


class AccruedExpense(BaseModel):
    payee_name: str
    payee_street_address: Optional[str] = None
    payee_city_state_zip: str
    expense_code_or_description: str
    col_a_outstanding_balance_beginning: float
    col_b_amount_incurred_this_period: float
    col_c_amount_paid_this_period: float
    col_d_outstanding_balance_close: float


class ScheduleF(BaseModel):
    line_items: list[AccruedExpense]
    summary_line_1_incurred_totals: float
    summary_line_2_paid_totals: float
    summary_line_3_net_change: float
