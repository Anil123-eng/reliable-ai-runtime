from threading import Event

import threading
from django.db import close_old_connections

from django.test import TestCase, TransactionTestCase

from .events import EventRecorder
from .models import (
    ConversationMessage,
    ConversationRun,
    OperationalEvent,
)
from .provider import FakeProvider
from .service import ConversationRuntime
from .state_machine import can_transition


class StateMachineTests(TestCase):

    def test_created_can_move_to_policy_checking(self):
        self.assertTrue(
            can_transition(
                "created",
                "policy_checking",
            )
        )

    def test_policy_can_be_rejected(self):
        self.assertTrue(
            can_transition(
                "policy_checking",
                "rejected",
            )
        )

    def test_policy_can_start_running(self):
        self.assertTrue(
            can_transition(
                "policy_checking",
                "running",
            )
        )

    def test_running_can_complete(self):
        self.assertTrue(
            can_transition(
                "running",
                "completed",
            )
        )

    def test_terminal_state_cannot_change(self):
        self.assertFalse(
            can_transition(
                "completed",
                "failed",
            )
        )

    def test_running_can_be_cancelled(self):
        self.assertTrue(
            can_transition(
                "running",
                "cancelled",
            )
        )


class ProviderTests(TestCase):

    def test_provider_returns_chunks(self):
        provider = FakeProvider(
            chunks=[
                "Hello ",
                "world",
            ]
        )

        cancel_event = Event()

        result = list(
            provider.stream(cancel_event)
        )

        self.assertEqual(
            result,
            [
                "Hello ",
                "world",
            ],
        )

    def test_provider_can_be_cancelled(self):
        provider = FakeProvider(
            chunks=[
                "Hello ",
                "world",
            ]
        )

        cancel_event = Event()
        cancel_event.set()

        result = list(
            provider.stream(cancel_event)
        )

        self.assertEqual(
            result,
            [],
        )

    def test_provider_counts_calls(self):
        provider = FakeProvider(
            chunks=["Hello"]
        )

        cancel_event = Event()

        list(
            provider.stream(cancel_event)
        )

        self.assertEqual(
            provider.call_count,
            1,
        )


class EventRecorderTests(TestCase):

    def test_events_get_ordered_sequence_numbers(self):
        run = ConversationRun.objects.create(
            id="event-test-1",
            user_input="hello",
            state="created",
        )

        recorder = EventRecorder(run)

        first = recorder.record(
            event_type="run_created",
            state="created",
        )

        second = recorder.record(
            event_type="state_change",
            state="policy_checking",
        )

        self.assertEqual(
            first.sequence,
            1,
        )

        self.assertEqual(
            second.sequence,
            2,
        )


class ConversationRuntimeTests(TestCase):

    def create_runtime(
        self,
        provider=None,
        run_id="test-run",
    ):
        runtime = ConversationRuntime(
            provider=provider
        )

        run = runtime.create_run(
            run_id=run_id,
            user_input="Hello",
        )

        return runtime, run

    def test_successful_run_completes(self):
        provider = FakeProvider(
            chunks=[
                "Hello ",
                "from ",
                "AI",
            ]
        )

        runtime, run = self.create_runtime(
            provider
        )

        result = runtime.run(run)

        self.assertEqual(
            result.state,
            "completed",
        )
        self.assertIsNotNone(
            result.completed_at,
        )

        self.assertEqual(
            result.partial_output,
            "Hello from AI",
        )

    def test_successful_run_calls_provider(self):
        provider = FakeProvider(
            chunks=["Hello"]
        )

        runtime, run = self.create_runtime(
            provider
        )

        runtime.run(run)

        self.assertEqual(
            provider.call_count,
            1,
        )

    def test_successful_run_persists_assistant_message(self):
        provider = FakeProvider(
            chunks=[
                "Hello ",
                "from AI",
            ]
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="persistence-test",
        )

        result = runtime.run(run)

        messages = list(
            ConversationMessage.objects
            .filter(run=result)
        )

        self.assertEqual(
            result.state,
            "completed",
        )

        self.assertEqual(
            len(messages),
            1,
        )

        self.assertEqual(
            messages[0].role,
            "assistant",
        )

        self.assertEqual(
            messages[0].content,
            "Hello from AI",
        )

    def test_rejected_input_does_not_call_provider(self):
        provider = FakeProvider(
            chunks=["Should not run"]
        )

        runtime = ConversationRuntime(
            provider=provider
        )

        run = runtime.create_run(
            run_id="reject-test",
            user_input="This contains forbidden content",
        )

        result = runtime.run(run)

        self.assertEqual(
            result.state,
            "rejected",
        )

        self.assertEqual(
            provider.call_count,
            0,
        )

        self.assertEqual(
            result.partial_output,
            "",
        )

        self.assertEqual(
            ConversationMessage.objects
            .filter(run=result)
            .count(),
            0,
        )

    def test_rejection_is_recorded(self):
        provider = FakeProvider()

        runtime = ConversationRuntime(
            provider=provider
        )

        run = runtime.create_run(
            run_id="reject-event-test",
            user_input="forbidden",
        )

        runtime.run(run)

        events = list(
            OperationalEvent.objects
            .filter(run=run)
            .order_by("sequence")
        )

        event_types = [
            event.event_type
            for event in events
        ]

        self.assertIn(
            "policy_rejected",
            event_types,
        )

        self.assertEqual(
            events[-1].state,
            "rejected",
        )

    def test_cancellation_before_provider(self):
        provider = FakeProvider(
            chunks=["Hello"]
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="cancel-before-test",
        )

        cancel_event = Event()
        cancel_event.set()

        result = runtime.run(
            run,
            cancel_event=cancel_event,
        )

        self.assertEqual(
            result.state,
            "cancelled",
        )

        self.assertEqual(
            provider.call_count,
            0,
        )

        self.assertEqual(
            ConversationMessage.objects
            .filter(run=result)
            .count(),
            0,
        )

    def test_cancellation_during_stream(self):
        class CancellingProvider:

            def __init__(self):
                self.call_count = 0

            def stream(self, cancel_event):
                self.call_count += 1

                yield "partial "

                cancel_event.set()

                yield "ignored"

        provider = CancellingProvider()

        runtime, run = self.create_runtime(
            provider,
            run_id="cancel-during-test",
        )

        result = runtime.run(
            run,
            cancel_event=Event(),
        )

        self.assertEqual(
            result.state,
            "cancelled",
        )

        self.assertEqual(
            result.partial_output,
            "partial ",
        )

        self.assertEqual(
            ConversationMessage.objects
            .filter(run=result)
            .count(),
            0,
        )

    def test_cancellation_after_provider_stops(self):
        class CancellingProvider:

            def __init__(self):
                self.call_count = 0

            def stream(self, cancel_event):
                self.call_count += 1

                yield "partial"

                cancel_event.set()

        provider = CancellingProvider()

        runtime, run = self.create_runtime(
            provider,
            run_id="cancel-after-test",
        )

        result = runtime.run(
            run,
            cancel_event=Event(),
        )

        self.assertEqual(
            result.state,
            "cancelled",
        )

        self.assertEqual(
            ConversationMessage.objects
            .filter(run=result)
            .count(),
            0,
        )

    def test_timeout_marks_run_timed_out(self):
        provider = FakeProvider(
            chunks=["Hello"],
            wait_for_release=True,
        )

        runtime = ConversationRuntime(
            provider=provider,
            timeout_seconds=0,
        )

        run = runtime.create_run(
            run_id="timeout-test",
            user_input="Hello",
        )

        result = runtime.run(run)

        self.assertEqual(
            result.state,
            "timed_out",
        )

        self.assertEqual(
            ConversationMessage.objects
            .filter(run=result)
            .count(),
            0,
        )

        events = list(
            OperationalEvent.objects
            .filter(run=run)
            .order_by("sequence")
        )

        event_types = [
            event.event_type
            for event in events
        ]

        self.assertIn(
            "timeout",
            event_types,
        )

        timeout_event = next(
            event
            for event in events
            if event.event_type == "timeout"
        )

        self.assertEqual(
            timeout_event.reason_code,
            "runtime_timeout",
        )

        self.assertEqual(
            events[-1].state,
            "timed_out",
        )

    def test_provider_failure_marks_run_failed(self):
        provider = FakeProvider(
            chunks=[
                "partial ",
                "output",
            ],
            fail_after=1,
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="failure-test",
        )

        result = runtime.run(run)

        self.assertEqual(
            result.state,
            "failed",
        )

        self.assertEqual(
            result.partial_output,
            "partial ",
        )

        self.assertEqual(
            ConversationMessage.objects
            .filter(run=result)
            .count(),
            0,
        )

    def test_provider_failure_is_recorded(self):
        provider = FakeProvider(
            chunks=[
                "partial ",
                "output",
            ],
            fail_after=1,
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="failure-event-test",
        )

        runtime.run(run)

        events = list(
            OperationalEvent.objects
            .filter(run=run)
            .order_by("sequence")
        )

        event_types = [
            event.event_type
            for event in events
        ]

        self.assertIn(
            "provider_error",
            event_types,
        )

        error_event = next(
            event
            for event in events
            if event.event_type == "provider_error"
        )

        self.assertEqual(
            error_event.error_code,
            "provider_failure",
        )

    def test_chunks_are_recorded_in_order(self):
        provider = FakeProvider(
            chunks=[
                "one",
                "two",
                "three",
            ]
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="chunk-test",
        )

        runtime.run(run)

        chunks = list(
            OperationalEvent.objects
            .filter(
                run=run,
                event_type="chunk",
            )
            .order_by("sequence")
        )

        self.assertEqual(
            len(chunks),
            3,
        )

        self.assertEqual(
            [event.chunk_sequence for event in chunks],
            [0, 1, 2],
        )

        self.assertEqual(
            [event.character_count for event in chunks],
            [3, 3, 5],
        )

    def test_trace_does_not_store_output_text(self):
        provider = FakeProvider(
            chunks=[
                "secret-looking text",
            ]
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="trace-redaction-test",
        )

        runtime.run(run)

        events = list(
            OperationalEvent.objects
            .filter(run=run)
            .order_by("sequence")
        )

        for event in events:
            self.assertNotIn(
                "secret-looking text",
                event.event_type,
            )

            self.assertNotIn(
                "secret-looking text",
                event.error_code,
            )

            self.assertNotIn(
                "secret-looking text",
                event.reason_code,
            )

    def test_no_events_are_recorded_after_terminal_event(self):
        provider = FakeProvider(
            chunks=["Hello"]
        )

        runtime, run = self.create_runtime(
            provider,
            run_id="terminal-event-test",
        )

        runtime.run(run)

        events = list(
            OperationalEvent.objects
            .filter(run=run)
            .order_by("sequence")
        )

        terminal_index = None

        for index, event in enumerate(events):
            if event.state in {
                "completed",
                "rejected",
                "cancelled",
                "timed_out",
                "failed",
            }:
                terminal_index = index
                break

        self.assertIsNotNone(
            terminal_index
        )

        for event in events[terminal_index + 1:]:
            self.fail(
                "Event found after terminal state: "
                f"{event.event_type}"
            )

     

class TerminalStateRaceTests(TransactionTestCase):
    reset_sequences = True

    def test_only_one_terminal_state_wins(self):
        run = ConversationRun.objects.create(
            id="race-test",
            user_input="Hello",
            state="running",
        )

        runtime = ConversationRuntime()

        results = []
        errors = []

        barrier = threading.Barrier(2)

        def try_transition(new_state):
            close_old_connections()

            try:
                barrier.wait()

                runtime.change_state(
                    run,
                    new_state,
                )

                results.append(new_state)

            except ValueError:
                errors.append(new_state)

            finally:
                close_old_connections()

        thread_one = threading.Thread(
            target=try_transition,
            args=("cancelled",),
        )

        thread_two = threading.Thread(
            target=try_transition,
            args=("timed_out",),
        )

        thread_one.start()
        thread_two.start()

        thread_one.join()
        thread_two.join()

        run.refresh_from_db()

        self.assertIn(
            run.state,
            {
                "cancelled",
                "timed_out",
            },
        )

        self.assertEqual(
            len(results),
            1,
        )

        self.assertEqual(
            len(errors),
            1,
        )


class RuntimeBenchmarkTests(TransactionTestCase):

    def assert_terminal_trace(self, run, expected_state):
        terminal_states = {
            "completed",
            "rejected",
            "cancelled",
            "timed_out",
            "failed",
        }

        events = list(
            OperationalEvent.objects
            .filter(run=run)
            .order_by("sequence")
        )

        terminal_events = [
            event
            for event in events
            if event.state in terminal_states
        ]

        # Exactly one terminal event
        self.assertEqual(
            len(terminal_events),
            1,
        )

        # Correct terminal state
        self.assertEqual(
            terminal_events[0].state,
            expected_state,
        )

        # Terminal event must be the final event
        self.assertEqual(
            events[-1].state,
            expected_state,
        )

        # No events after terminal event
        terminal_sequence = terminal_events[0].sequence

        events_after_terminal = [
            event
            for event in events
            if event.sequence > terminal_sequence
        ]

        self.assertEqual(
            events_after_terminal,
            [],
        )

    def test_runtime_benchmark(self):
        iterations = 10

        outcomes = {
            "completed": 0,
            "rejected": 0,
            "cancelled": 0,
            "timed_out": 0,
            "failed": 0,
        }

        # -------------------------------------------------
        # 1. Successful runs
        # -------------------------------------------------

        for index in range(iterations):

            provider = FakeProvider(
                chunks=["Hello"]
            )

            runtime = ConversationRuntime(
                provider=provider,
            )

            run = runtime.create_run(
                run_id=f"benchmark-success-{index}",
                user_input="Hello",
            )

            result = runtime.run(run)

            self.assertEqual(
                result.state,
                "completed",
            )

            self.assertEqual(
                provider.call_count,
                1,
            )

            self.assertEqual(
                ConversationMessage.objects.filter(
                    run=run,
                    role="assistant",
                ).count(),
                1,
            )

            self.assert_terminal_trace(
                run,
                "completed",
            )

            outcomes[result.state] += 1

        # -------------------------------------------------
        # 2. Rejected runs
        # -------------------------------------------------

        for index in range(iterations):

            provider = FakeProvider()

            runtime = ConversationRuntime(
                provider=provider,
            )

            run = runtime.create_run(
                run_id=f"benchmark-rejected-{index}",
                user_input="This contains forbidden content",
            )

            result = runtime.run(run)

            self.assertEqual(
                result.state,
                "rejected",
            )

            # Provider must never be called
            self.assertEqual(
                provider.call_count,
                0,
            )

            # No successful assistant response
            self.assertEqual(
                ConversationMessage.objects.filter(
                    run=run,
                    role="assistant",
                ).count(),
                0,
            )

            self.assert_terminal_trace(
                run,
                "rejected",
            )

            outcomes[result.state] += 1

        # -------------------------------------------------
        # 3. Cancelled during streaming
        # -------------------------------------------------

         
        for index in range(iterations):

            class CancellingProvider:

                def __init__(self):
                    self.call_count = 0
                    self.consumed_chunks = 0

                def stream(self, runtime_cancel_event):
                    self.call_count += 1

                    # First chunk is streamed successfully.
                    self.consumed_chunks += 1
                    yield "Hello"

                    # Simulate cancellation during streaming.
                    runtime_cancel_event.set()

                    # Provider stops immediately.
                    return

            provider = CancellingProvider()

            runtime = ConversationRuntime(
                provider=provider,
            )

            run = runtime.create_run(
                run_id=f"benchmark-cancelled-{index}",
                user_input="Hello",
            )

            result = runtime.run(run)

            self.assertEqual(
                result.state,
                "cancelled",
            )

            self.assertEqual(
                provider.call_count,
                1,
            )

            # Only the first chunk should be consumed.
            self.assertEqual(
                provider.consumed_chunks,
                1,
            )

            # No successful assistant response.
            self.assertEqual(
                ConversationMessage.objects.filter(
                    run=run,
                    role="assistant",
                ).count(),
                0,
            )

            self.assert_terminal_trace(
                run,
                "cancelled",
            )

            outcomes[result.state] += 1

        # -------------------------------------------------
        # 4. Timed-out runs
        # -------------------------------------------------

        for index in range(iterations):

            provider = FakeProvider(
                chunks=["Hello"],
                wait_for_release=True,
            )

            runtime = ConversationRuntime(
                provider=provider,
                timeout_seconds=0,
            )

            run = runtime.create_run(
                run_id=f"benchmark-timeout-{index}",
                user_input="Hello",
            )

            result = runtime.run(run)

            self.assertEqual(
                result.state,
                "timed_out",
            )

            # No successful assistant response
            self.assertEqual(
                ConversationMessage.objects.filter(
                    run=run,
                    role="assistant",
                ).count(),
                0,
            )

            self.assert_terminal_trace(
                run,
                "timed_out",
            )

            outcomes[result.state] += 1

        # -------------------------------------------------
        # 5. Provider failure after partial output
        # -------------------------------------------------

        for index in range(iterations):

            provider = FakeProvider(
                chunks=[
                    "Hello ",
                    "world",
                ],
                fail_after=1,
            )

            runtime = ConversationRuntime(
                provider=provider,
            )

            run = runtime.create_run(
                run_id=f"benchmark-failed-{index}",
                user_input="Hello",
            )

            result = runtime.run(run)

            self.assertEqual(
                result.state,
                "failed",
            )

            # Partial output may exist,
            # but it must not become a successful assistant message.
            self.assertEqual(
                ConversationMessage.objects.filter(
                    run=run,
                    role="assistant",
                ).count(),
                0,
            )

            self.assert_terminal_trace(
                run,
                "failed",
            )

            outcomes[result.state] += 1

        # -------------------------------------------------
        # Verify benchmark counts
        # -------------------------------------------------

        self.assertEqual(
            outcomes["completed"],
            iterations,
        )

        self.assertEqual(
            outcomes["rejected"],
            iterations,
        )

        self.assertEqual(
            outcomes["cancelled"],
            iterations,
        )

        self.assertEqual(
            outcomes["timed_out"],
            iterations,
        )

        self.assertEqual(
            outcomes["failed"],
            iterations,
        )

        # Report terminal-state counts
        print(
            "\nBenchmark terminal-state counts:"
        )

        for state, count in outcomes.items():
            print(
                f"{state}: {count}"
            )