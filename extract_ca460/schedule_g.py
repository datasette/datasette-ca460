from typing import Optional

from pydantic import BaseModel

PROMPT = """\
Extract Schedule G - Payments Made by an Agent or Independent Contractor from FPPC Form 460. \
This lists payments made by agents/contractors on behalf of the committee. Uses the same \
3-letter expense codes as Schedule E."""


class AgentPayment(BaseModel):
    agent_or_contractor_name: str
    payee_name: str
    payee_street_address: Optional[str] = None
    payee_city_state_zip: Optional[str] = None
    expense_code: Optional[str] = None
    description_of_payment: Optional[str] = None
    amount_paid: float


class ScheduleG(BaseModel):
    line_items: list[AgentPayment]
    total: Optional[float] = None
