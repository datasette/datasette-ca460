from .page_classifier import PageClassification, PROMPT as CLASSIFIER_PROMPT
from .cover_page_part_1 import CoverPagePart1
from .cover_page_part_2 import CoverPagePart2, RelatedCommittee, PrimarilyFormedCandidate
from .summary_page import SummaryPage, ExpenditureLimitEntry
from .schedule_a import ScheduleA, ScheduleAContribution
from .schedule_b_part_1 import ScheduleBPart1, LoanReceived
from .schedule_b_part_2 import ScheduleBPart2, LoanGuarantor
from .schedule_c import ScheduleC, NonmonetaryContribution
from .schedule_d import ScheduleD, ScheduleDExpenditure
from .schedule_e import ScheduleE, ScheduleEPayment
from .schedule_f import ScheduleF, AccruedExpense
from .schedule_g import ScheduleG, AgentPayment
from .schedule_h import ScheduleH, LoanMade
from .schedule_i import ScheduleI, MiscIncrease
from .unknown import UnknownPage

from . import (
    cover_page_part_1,
    cover_page_part_2,
    summary_page,
    schedule_a,
    schedule_b_part_1,
    schedule_b_part_2,
    schedule_c,
    schedule_d,
    schedule_e,
    schedule_f,
    schedule_g,
    schedule_h,
    schedule_i,
    unknown,
)

# Map from page_type string to (prompt, model) for each page type
PAGE_TYPES: dict[str, tuple[str, type]] = {
    "cover-page-part-1": (cover_page_part_1.PROMPT, CoverPagePart1),
    "cover-page-part-2": (cover_page_part_2.PROMPT, CoverPagePart2),
    "summary-page": (summary_page.PROMPT, SummaryPage),
    "schedule-a": (schedule_a.PROMPT, ScheduleA),
    "schedule-b-part-1": (schedule_b_part_1.PROMPT, ScheduleBPart1),
    "schedule-b-part-2": (schedule_b_part_2.PROMPT, ScheduleBPart2),
    "schedule-c": (schedule_c.PROMPT, ScheduleC),
    "schedule-d": (schedule_d.PROMPT, ScheduleD),
    "schedule-e": (schedule_e.PROMPT, ScheduleE),
    "schedule-f": (schedule_f.PROMPT, ScheduleF),
    "schedule-g": (schedule_g.PROMPT, ScheduleG),
    "schedule-h": (schedule_h.PROMPT, ScheduleH),
    "schedule-i": (schedule_i.PROMPT, ScheduleI),
    "unknown": (unknown.PROMPT, UnknownPage),
}

__all__ = [
    "CLASSIFIER_PROMPT",
    "PAGE_TYPES",
    "PageClassification",
    "CoverPagePart1",
    "CoverPagePart2",
    "RelatedCommittee",
    "PrimarilyFormedCandidate",
    "SummaryPage",
    "ExpenditureLimitEntry",
    "ScheduleA",
    "ScheduleAContribution",
    "ScheduleBPart1",
    "LoanReceived",
    "ScheduleBPart2",
    "LoanGuarantor",
    "ScheduleC",
    "NonmonetaryContribution",
    "ScheduleD",
    "ScheduleDExpenditure",
    "ScheduleE",
    "ScheduleEPayment",
    "ScheduleF",
    "AccruedExpense",
    "ScheduleG",
    "AgentPayment",
    "ScheduleH",
    "LoanMade",
    "ScheduleI",
    "MiscIncrease",
    "UnknownPage",
]
