from pydantic import BaseModel


class BaselineApproveRequest(BaseModel):
    snapshot_id: str
