from pydantic import BaseModel

PROMPT = """\
Unknown or unrecognized page type from a Form 460."""


class UnknownPage(BaseModel):
    raw_text: str
