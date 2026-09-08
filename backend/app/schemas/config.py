from pydantic import BaseModel


class ConfigRead(BaseModel):
    text_change_threshold: float
    visual_change_threshold: float
    structure_change_threshold: float
    max_baselines_per_target: int = 20
