from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FoodAnalysisQuotaExceeded(Exception):
    limit: int
    used: int
    retry_at: datetime
    window_days: int = 30
    code: str = "food_analysis_quota_exceeded"

    def __str__(self) -> str:
        return f"Food analysis quota of {self.limit} calls is exhausted until {self.retry_at}."
