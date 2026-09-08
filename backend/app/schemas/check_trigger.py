from pydantic import BaseModel


class CheckTriggerResponse(BaseModel):
    target_id: str
    accepted: bool
