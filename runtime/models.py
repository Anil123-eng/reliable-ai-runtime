from django.db import models


class ConversationRun(models.Model):
    STATE_CHOICES = [
        ("created", "Created"),
        ("policy_checking", "Policy Checking"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
        ("timed_out", "Timed Out"),
        ("failed", "Failed"),
    ]

    id = models.CharField(max_length=100, primary_key=True)
    user_input = models.TextField()
    state = models.CharField(
        max_length=30,
        choices=STATE_CHOICES,
        default="created",
    )
    partial_output = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.id} - {self.state}"


class ConversationMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    run = models.ForeignKey(
        ConversationRun,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class OperationalEvent(models.Model):
    run = models.ForeignKey(
        ConversationRun,
        on_delete=models.CASCADE,
        related_name="events",
    )
    sequence = models.PositiveIntegerField()
    event_type = models.CharField(max_length=50)
    state = models.CharField(max_length=30, blank=True)
    provider = models.CharField(max_length=50, blank=True)
    error_code = models.CharField(max_length=100, blank=True)
    reason_code = models.CharField(max_length=100, blank=True)
    chunk_sequence = models.PositiveIntegerField(null=True, blank=True)
    character_count = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]