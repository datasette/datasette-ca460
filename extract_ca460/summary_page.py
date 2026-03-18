from typing import Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract the Summary Page of FPPC Form 460. This is a very dense financial summary page. It has \
numbered lines with Column A (this period) and Column B (calendar year total / to date). Extract \
each numbered line carefully. Use the line number as part of the key name. All dollar amounts \
should be numbers (not strings). Dates in YYYY-MM-DD format.

The page has these main sections:
- Contributions Received (lines 1-5)
- Expenditures Made (lines 6-11)
- Current Cash Statement (lines 12-16)
- Loan Guarantees Received (line 17)
- Cash Equivalents and Outstanding Debts (lines 18-19)
- Calendar Year Summary for Candidates (lines 20-22)
- Expenditures Limit Summary for State Candidates (line 22 right side)

Column A = "This Period" amounts. Column B = "Calendar Year Total / To Date" amounts."""


class ExpenditureLimitEntry(BaseModel):
    date_of_election: str = Field(description="YYYY-MM-DD")
    total_to_date: float


class SummaryPage(BaseModel):
    statement_covers_period_from: str = Field(description="YYYY-MM-DD")
    statement_covers_period_through: str = Field(description="YYYY-MM-DD")
    committee_name: str
    id_number: str

    # Contributions Received
    line_1_monetary_contributions_col_a: float
    line_1_monetary_contributions_col_b: float
    line_2_loans_received_col_a: float
    line_2_loans_received_col_b: float
    line_3_subtotal_cash_contributions_col_a: float
    line_3_subtotal_cash_contributions_col_b: float
    line_4_nonmonetary_contributions_col_a: float
    line_4_nonmonetary_contributions_col_b: float
    line_5_total_contributions_received_col_a: float
    line_5_total_contributions_received_col_b: float

    # Expenditures Made
    line_6_payments_made_col_a: float
    line_6_payments_made_col_b: float
    line_7_loans_made_col_a: float
    line_7_loans_made_col_b: float
    line_8_subtotal_cash_payments_col_a: float
    line_8_subtotal_cash_payments_col_b: float
    line_9_accrued_expenses_col_a: float
    line_9_accrued_expenses_col_b: float
    line_10_nonmonetary_adjustment_col_a: float
    line_10_nonmonetary_adjustment_col_b: float
    line_11_total_expenditures_col_a: float
    line_11_total_expenditures_col_b: float

    # Current Cash Statement
    line_12_beginning_cash_balance: float
    line_13_cash_receipts_col_a: float
    line_14_miscellaneous_increases: float
    line_15_cash_payments_col_a: float
    line_16_ending_cash_balance: float = Field(
        description="Line 12 + 13 + 14 - 15. If termination, must be zero."
    )

    # Loan Guarantees
    line_17_loan_guarantees_received_col_a: float
    line_17_loan_guarantees_received_col_b: float

    # Cash Equivalents and Outstanding Debts
    line_18_cash_equivalents: float
    line_19_outstanding_debts: float

    # Calendar Year Summary
    line_20_contributions_received: Optional[float] = Field(None, description="1/1 through 6/30")
    line_20_contributions_received_to_date: Optional[float] = None
    line_21_expenditures_made: Optional[float] = Field(None, description="1/1 through 6/30")
    line_21_expenditures_made_to_date: Optional[float] = None

    # Expenditures Limit Summary
    line_22_cumulative_expenditures_made: Optional[list[ExpenditureLimitEntry]] = None
