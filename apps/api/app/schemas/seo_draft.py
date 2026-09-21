from pydantic import BaseModel


class SeoDraftOut(BaseModel):
    id: str
    product_id: str | None
    finding_id: str | None
    url: str | None
    draft_type: str
    draft_description: str | None
    draft_seo_title: str | None
    draft_meta_description: str | None
    status: str

    @classmethod
    def from_orm_draft(cls, draft) -> "SeoDraftOut":
        return cls(
            id=str(draft.id),
            product_id=str(draft.product_id) if draft.product_id else None,
            finding_id=str(draft.finding_id) if draft.finding_id else None,
            url=draft.url,
            draft_type=draft.draft_type,
            draft_description=draft.draft_description,
            draft_seo_title=draft.draft_seo_title,
            draft_meta_description=draft.draft_meta_description,
            status=draft.status,
        )
