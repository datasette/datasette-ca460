from typing import Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract Schedule E - Payments Made from FPPC Form 460. Each row is a payment/expenditure. The \
"CODE" column uses standardized 3-letter expense codes (CMP, CNS, CTB, CVC, FIL, FND, IND, \
LEG, LIT, MBR, MTG, OFC, PET, PHO, POL, POS, PRO, PRT, RAD, RFD, SAL, TEL, TRC, TRS, TSF, \
VOT, WEB). If a code is used, the "description" column may be blank. If no code, the payee \
described the payment in the description. Parse all rows on the page."""


class ScheduleEPayment(BaseModel):
    payee_name: str
    payee_street_address: Optional[str] = None
    payee_city_state_zip: str
    expense_code: Optional[str] = Field(
        None, description="3-letter code like FND, LIT, etc. Null if described instead."
    )
    description_of_payment: Optional[str] = Field(
        None, description="Free text description. Null if code used instead."
    )
    amount_paid: float


class ScheduleE(BaseModel):
    line_items: list[ScheduleEPayment]
    subtotal: Optional[float] = None
