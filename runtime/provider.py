class ProviderError(Exception):
    pass


class FakeProvider:
    def __init__(
        self,
        chunks=None,
        fail_after=None,
        wait_for_release=False,
    ):
        self.chunks = chunks or [
            "Hello ",
            "from ",
            "the ",
            "AI ",
            "runtime.",
        ]

        self.fail_after = fail_after
        self.wait_for_release = wait_for_release

        self.call_count = 0
        self.consumed_chunks = 0

    def stream(self, cancel_event):
        self.call_count += 1

        for index, chunk in enumerate(self.chunks):
            if cancel_event.is_set():
                return

            if self.fail_after is not None:
                if index == self.fail_after:
                    raise ProviderError(
                        "Fake provider failed"
                    )

            if self.wait_for_release:
                # Deterministic provider controlled by the test.
                # The runtime can decide that the run has timed out
                # without depending on an arbitrary sleep.
                while not cancel_event.is_set():
                    yield None

            if cancel_event.is_set():
                return

            self.consumed_chunks += 1
            yield chunk