from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_settings
from app.core.config import Settings
from app.schemas.config import ConfigRead

router = APIRouter(tags=["config"], dependencies=[Depends(get_current_user)])

AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/config", response_model=ConfigRead)
async def get_config(settings: AppSettings) -> ConfigRead:
    return ConfigRead(
        text_change_threshold=settings.TEXT_CHANGE_THRESHOLD,
        visual_change_threshold=settings.VISUAL_CHANGE_THRESHOLD,
        structure_change_threshold=settings.STRUCTURE_CHANGE_THRESHOLD,
        max_baselines_per_target=settings.MAX_BASELINES_PER_TARGET,
    )

