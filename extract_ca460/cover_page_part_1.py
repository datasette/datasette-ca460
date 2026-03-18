from typing import Literal, Optional

from pydantic import BaseModel, Field

PROMPT = """\
Extract the Cover Page (Part 1) of FPPC Form 460. This page contains the statement period, \
committee type, statement type, committee information, and treasurer information. Dates should \
be in YYYY-MM-DD format. The "Type of Recipient Committee" section has checkboxes -- pick the \
one that is checked. Similarly for "Type of Statement"."""


class CoverPagePart1(BaseModel):
    statement_covers_period_from: str = Field(description="YYYY-MM-DD")
    statement_covers_period_through: str = Field(description="YYYY-MM-DD")
    date_of_election: Optional[str] = Field(None, description="YYYY-MM-DD if applicable")
    page_number: int
    total_pages: int
    type_of_recipient_committee: Literal[
        "officeholder_candidate_controlled",
        "state_candidate_election",
        "recall",
        "general_purpose_sponsored",
        "general_purpose_small_contributor",
        "general_purpose_political_party_central",
        "primarily_formed_ballot_measure",
        "primarily_formed_ballot_measure_controlled",
        "primarily_formed_ballot_measure_sponsored",
        "primarily_formed_candidate_officeholder",
    ]
    type_of_statement: Literal[
        "preelection",
        "semi_annual",
        "termination",
        "quarterly",
        "special_odd_year_report",
        "amendment",
    ]
    committee_name: str
    id_number: str
    committee_street_address: Optional[str] = None
    committee_city: Optional[str] = None
    committee_state: Optional[str] = None
    committee_zip: Optional[str] = None
    committee_phone: Optional[str] = None
    committee_mailing_address: Optional[str] = None
    committee_mailing_city: Optional[str] = None
    committee_mailing_state: Optional[str] = None
    committee_mailing_zip: Optional[str] = None
    committee_email: Optional[str] = None
    treasurer_name: str
    treasurer_mailing_address: Optional[str] = None
    treasurer_city: Optional[str] = None
    treasurer_state: Optional[str] = None
    treasurer_zip: Optional[str] = None
    treasurer_phone: Optional[str] = None
    treasurer_email: Optional[str] = None
    assistant_treasurer_name: Optional[str] = None
    verification_executed_dates: list[str] = Field(description="YYYY-MM-DD for each signed date")
