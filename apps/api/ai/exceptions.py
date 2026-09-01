from dataclasses import dataclass
from datetime import datetime


@dataclass
class FoodAnalysisQuotaExceeded(Exception):
    limit: int
    used: int
    retry_at: datetime
    window_days: int = 30
    code: str = "food_analysis_quota_exceeded"

    def __post_init__(self) -> None:
        # BaseException pickles from `args`. Dataclass-generated initialization
        # does not populate it when callers use keyword arguments.
        Exception.__init__(
            self,
            self.limit,
            self.used,
            self.retry_at,
            self.window_days,
            self.code,
        )

    def __str__(self) -> str:
        return f"Food analysis quota of {self.limit} calls is exhausted until {self.retry_at}."
