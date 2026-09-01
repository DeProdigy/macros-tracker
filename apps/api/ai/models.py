from django.conf import settings
from django.db import models


class FoodAnalysisCall(models.Model):
    """One admitted attempt to use the paid food-analysis provider.

    A reservation is inserted before network work so concurrent requests cannot
    both take the final slot. `provider_called_at` records dispatch;
    `quota_debited_at` is set only when provider work counts against the paid
    allowance.

    Request and response snapshots are retained deliberately for debugging and
    a future evaluation/training dataset. Image bytes stay in R2; request JSON
    contains only the stable object key, never a presigned URL.
    """

    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="food_analysis_calls",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RESERVED)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField()
    provider_called_at = models.DateTimeField(null=True, blank=True)
    quota_debited_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    latency_ms = models.PositiveBigIntegerField(null=True, blank=True)
    provider = models.CharField(max_length=64, blank=True)
    model = models.CharField(max_length=128, blank=True)
    provider_request_id = models.CharField(max_length=255, blank=True)
    input_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    output_tokens = models.PositiveBigIntegerField(null=True, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    estimated_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    raw_response = models.TextField(blank=True)
    failure_category = models.CharField(max_length=64, blank=True)
    failure_message = models.CharField(max_length=500, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "quota_debited_at"), name="ai_call_user_quota_at"),
            models.Index(fields=("user", "created_at"), name="ai_call_user_created_at"),
        ]
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status} at {self.started_at.isoformat()}"
