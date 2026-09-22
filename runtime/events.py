from .models import OperationalEvent


class EventRecorder:

    def __init__(self, run):
        self.run = run

    def record(
        self,
        event_type,
        state="",
        provider="",
        error_code="",
        reason_code="",
        chunk_sequence=None,
        character_count=None,
    ):
        last_event = (
            OperationalEvent.objects
            .filter(run=self.run)
            .order_by("-sequence")
            .first()
        )

        next_sequence = 1

        if last_event:
            next_sequence = last_event.sequence + 1

        return OperationalEvent.objects.create(
            run=self.run,
            sequence=next_sequence,
            event_type=event_type,
            state=state,
            provider=provider,
            error_code=error_code,
            reason_code=reason_code,
            chunk_sequence=chunk_sequence,
            character_count=character_count,
        )



    