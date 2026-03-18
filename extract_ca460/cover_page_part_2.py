from typing import Literal, Optional

from pydantic import BaseModel

PROMPT = """\
Extract Cover Page Part 2 of FPPC Form 460. This contains Sections 5-7: officeholder/candidate \
info, ballot measure committee info, and primarily formed candidate/officeholder committee info. \
Many fields may be empty."""


class RelatedCommittee(BaseModel):
    committee_name: Optional[str] = None
    id_number: Optional[str] = None
    treasurer_name: Optional[str] = None
    controlled_committee: Optional[bool] = None
    committee_address: Optional[str] = None
    committee_city: Optional[str] = None
    committee_state: Optional[str] = None
    committee_zip: Optional[str] = None
    committee_phone: Optional[str] = None


class PrimarilyFormedCandidate(BaseModel):
    name: Optional[str] = None
    office_sought: Optional[str] = None
    support_or_oppose: Optional[Literal["support", "oppose"]] = None


class CoverPagePart2(BaseModel):
    officeholder_candidate_name: Optional[str] = None
    office_sought_or_held: Optional[str] = None
    jurisdiction: Optional[str] = None
    residential_business_address: Optional[str] = None
    residential_city: Optional[str] = None
    residential_state: Optional[str] = None
    residential_zip: Optional[str] = None
    ballot_measure_name: Optional[str] = None
    ballot_number_or_letter: Optional[str] = None
    ballot_jurisdiction: Optional[str] = None
    ballot_support_or_oppose: Optional[Literal["support", "oppose"]] = None
    controlling_officeholder_name: Optional[str] = None
    controlling_office_sought_or_held: Optional[str] = None
    controlling_district_number: Optional[str] = None
    related_committees: list[RelatedCommittee]
    primarily_formed_candidates: list[PrimarilyFormedCandidate]
