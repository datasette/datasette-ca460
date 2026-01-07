from pydantic import BaseModel
from enum import Enum

PROMPT = """
Given the top portion of a scanned page of a California Form 460 Campaign Statement, 
identify the what type of page it is. 

Use the text from the image to determine the page type.

Return your prediction as the following JSON object:

- `page_type`: The type of page, one of:
  - `cover_page`: "Recipient Committee Campaign Statement Cover Page"
  - `cover_page_2`: "Recipient Committee Campaign Statement Cover Page — Part 2"
  - `campaign_disclosure_summary_page`: "Campaign Disclosure Statement Summary Page"
  - `schedule_a`: "Schedule A Monetary Contributions Received"
  - `schedule_a_continuation`:  "Schedule A (Continuation Sheet) Monetary Contributions Received"
  - `schedule_b_part1_loans_received`: "Schedule B – Part 1 Loans Received"
  - `schedule_b_part2_loan_guarantors`: "Schedule B – Part 2 Loan Guarantors"
  - `schedule_c_nonmonetary_contributions`: "Schedule C Nonmonetary Contributions Received"
  - `schedule_d_summary_expenditures`: "Schedule D Summary of Expenditures Supporting/Opposing Other Candidates, Measures and Committees"
  - `schedule_d_summary_expenditures_continuation`: "Schedule D (Continuation Sheet) Summary of Expenditures Supporting/Opposing Other Candidates, Measures and Committees" 
  - `schedule_e_payments_made`: "Schedule E Payments Made"
  - `schedule_e_payments_made_continuation`: "Schedule E (Continuation Sheet) Payments Made" 
  - `schedule_f_accrued_expenses`: "Schedule F Accrued Expenses (Unpaid Bills)"
  - `schedule_f_accrued_expenses_continuation`: "Schedule F (Continuation Sheet) Accrued Expenses (Unpaid Bills)"
"""


class Form460PageTypeEnum(str, Enum):
    campaign_statement_cover_page = "cover_page"
    campaign_statement_cover_page2 = "cover_page_2"
    campaign_disclosure_summary_page = "campaign_disclosure_summary_page"
    schedule_a = "schedule_a"
    schedule_a_continuation = "schedule_a_continuation"
    schedule_b_part1_loans_received = "schedule_b_part1_loans_received"
    schedule_b_part2_loan_guarantors = "schedule_b_part2_loan_guarantors"
    schedule_c_nonmonetary_contributions = "schedule_c_nonmonetary_contributions"
    schedule_d_summary_expenditures = "schedule_d_summary_expenditures"
    schedule_d_summary_expenditures_continuation = (
        "schedule_d_summary_expenditures_continuation"
    )
    schedule_e_payments_made = "schedule_e_payments_made"
    schedule_e_payments_made_continuation = "schedule_e_payments_made_continuation"
    schedule_f_accrued_expenses = "schedule_f_accrued_expenses"
    schedule_f_accrued_expenses_continuation = (
        "schedule_f_accrued_expenses_continuation"
    )
    unknown = "unknown"
    # skip g
    # skip h
    # skip i


class Form460PageTypeModel(BaseModel):
    # extracted_text: str
    page_type: Form460PageTypeEnum = Form460PageTypeEnum.campaign_statement_cover_page
