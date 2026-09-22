from threading import Event
from time import monotonic
from django.utils import timezone

from django.db import transaction

from .events import EventRecorder
from .models import ConversationMessage, ConversationRun
from .provider import FakeProvider, ProviderError
from .state_machine import can_transition


class ConversationRuntime:

    def __init__(
        self,
        provider=None,
        timeout_seconds=5,
    ):
        self.provider = provider or FakeProvider()
        self.timeout_seconds = timeout_seconds

    def create_run(self, run_id, user_input):
        run = ConversationRun.objects.create(
            id=run_id,
            user_input=user_input,
            state="created",
        )

        recorder = EventRecorder(run)

        recorder.record(
            event_type="run_created",
            state="created",
        )

        return run

    def check_policy(self, user_input):
        blocked_words = ["forbidden"]

        text = user_input.lower()

        for word in blocked_words:
            if word in text:
                return False

        return True

    def change_state(self, run, new_state):
        with transaction.atomic():
          locked_run = (
            ConversationRun.objects
            .select_for_update()
            .get(pk=run.pk)
          )

          if not can_transition(
            locked_run.state,
            new_state,
          ):
            raise ValueError(
                f"Invalid state transition: "
                f"{locked_run.state} -> {new_state}"
            )

          locked_run.state = new_state

          locked_run.save(
            update_fields=["state"]
          )

          run.state = new_state

        recorder = EventRecorder(run)

        recorder.record(
        event_type="state_change",
        state=new_state,
    )

    def persist_successful_response(self, run, output):
        ConversationMessage.objects.create(
            run=run,
            role="assistant",
            content=output,
        )

    def run(self, run, cancel_event=None):
        if cancel_event is None:
            cancel_event = Event()

        recorder = EventRecorder(run)

        # 1. Policy check
        self.change_state(
            run,
            "policy_checking",
        )

        allowed = self.check_policy(
            run.user_input
        )

        if not allowed:
            recorder.record(
                event_type="policy_rejected",
                state="policy_checking",
                reason_code="blocked_input",
            )

            self.change_state(
                run,
                "rejected",
            )

            return run

        recorder.record(
            event_type="policy_allowed",
            state="policy_checking",
        )

        # 2. Start provider
        self.change_state(
            run,
            "running",
        )

        if cancel_event.is_set():
            recorder.record(
                event_type="cancel_requested",
                state="running",
                reason_code="cancelled_before_provider",
            )

            self.change_state(
                run,
                "cancelled",
            )

            return run

        recorder.record(
            event_type="provider_start",
            state="running",
            provider="fake",
        )

        output = ""
        chunk_sequence = 0
        start_time = monotonic()

        try:
            # 3. Stream provider output
            for chunk in self.provider.stream(
                cancel_event
            ):
                # Timeout check
                if (
                    monotonic() - start_time
                    >= self.timeout_seconds
                ):
                    cancel_event.set()

                    recorder.record(
                        event_type="timeout",
                        state="running",
                        reason_code="runtime_timeout",
                    )

                    self.change_state(
                        run,
                        "timed_out",
                    )

                    return run

                # Cancellation check
                if cancel_event.is_set():
                    recorder.record(
                        event_type="cancel_requested",
                        state="running",
                        reason_code="cancelled_during_stream",
                    )

                    self.change_state(
                        run,
                        "cancelled",
                    )

                    return run

                # Ignore empty/non-text provider signals.
                if chunk is None:
                    continue

                output += chunk

                run.partial_output = output

                run.save(
                    update_fields=[
                        "partial_output"
                    ]
                )

                recorder.record(
                    event_type="chunk",
                    state="running",
                    provider="fake",
                    chunk_sequence=chunk_sequence,
                    character_count=len(chunk),
                )

                chunk_sequence += 1

            # 4. Check cancellation after provider stops
            if cancel_event.is_set():
                recorder.record(
                    event_type="cancel_requested",
                    state="running",
                    reason_code="cancelled_after_stream",
                )

                self.change_state(
                    run,
                    "cancelled",
                )

                return run

            # 5. Provider successfully completed
            recorder.record(
                event_type="provider_complete",
                state="running",
                provider="fake",
            )

            # 6. Persistence boundary.
            #
            # The assistant message is only persisted after
            # the provider has completed successfully.
            self.persist_successful_response(
                run,
                output,
            )

            # 7. The run becomes completed only after the
            # successful response has been persisted.
            run.completed_at = timezone.now()

            run.save(
              update_fields=[
                "completed_at"
              ]
            )
            self.change_state(
                run,
                "completed",
            )

        except ProviderError:
            # Keep any partial output.
            run.partial_output = output

            run.save(
                update_fields=[
                    "partial_output"
                ]
            )

            # Provider failure is recorded before the terminal
            # failed state.
            recorder.record(
                event_type="provider_error",
                state="running",
                provider="fake",
                error_code="provider_failure",
            )

            self.change_state(
                run,
                "failed",
            )

        return run