from pydantic import BaseModel

PROMPT = """
Parse the scanned Form 460 summary page and return the data as a JSON object.

For statement cover periods, provide the date in the format YYYY-MM-DD.
"""


class Form460SummaryPage(BaseModel):
    name_of_filer: str
    cover_period_from: str
    cover_period_to: str
    id_number: str
    
    line_1_a_monetary_contributions: float
    line_1_b_monetary_contributions: float
    line_2_a_loans_received: float
    line_2_b_loans_received: float
    line_3_a_subtotal_cash_contributions: float
    line_3_b_subtotal_cash_contributions: float
    line_4_a_nonmonetary_contributions: float
    line_4_b_nonmonetary_contributions: float
    line_5_a_total_contributions: float
    line_5_b_total_contributions: float

    line_6_a_payments_made: float
    line_6_b_payments_made: float
    line_7_a_loans_made: float
    line_7_b_loans_made: float
    line_8_a_subtotal_cash_payments: float
    line_8_b_subtotal_cash_payments: float
    line_9_a_accrued_expenses: float
    line_9_b_accrued_expenses: float
    line_10_a_nonmonetary_adjustment: float
    line_10_b_nonmonetary_adjustment: float
    line_11_a_total_expenditures: float
    line_11_b_total_expenditures: float

    line_12_beginning_cash_balance: float
    line_13_cash_receipts: float
    line_14_misc_increase_cash: float
    line_15_cash_payments: float
    line_16_ending_cash_balance: float

    line_17_loan_guarantees_received: float

    line_18_cash_equivalents: float
    line_19_outstanding_debt: float

