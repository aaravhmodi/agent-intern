"""Draft only; this module has no mail, browser, or application submission capability."""

from openai import OpenAI

from opportunity_lite.models import Draft, Listing


def draft_message(client: OpenAI, model: str, profile: str, listing: Listing) -> Draft:
    if not profile.strip():
        raise ValueError("Write your factual background in profile.md before drafting.")
    response = client.responses.parse(
        model=model,
        instructions=(
            "Write a concise, personal message about this public listing. Use only facts in the "
            "candidate profile and listing. Do not invent skills, relationships, applications, "
            "attendance, or eligibility. For a job, ask about the role; for a conference, ask "
            "about attending or contributing. Address a team when no person is named. "
            "Return an email subject, email body, and shorter copyable message. "
            "These are drafts for human review, never sent by this program."
        ),
        input=(
            f"Candidate profile:\n{profile[:12000]}\n\n"
            f"Public listing:\n{listing.model_dump_json()}"
        ),
        text_format=Draft,
        store=False,
    )
    if response.output_parsed is None:
        raise ValueError("The model did not return a draft.")
    return Draft.model_validate(response.output_parsed.model_dump())
