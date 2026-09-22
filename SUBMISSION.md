# Product Engineering Challenge Submission

## Candidate

* **Name:** M Anil
* **Email:** `[ma6039564340@gmail.com]`
* **GitHub:** `[https://github.com/Anil123-eng]`
* **Selected problem:** Problem 5 — Reliable AI Conversation Runtime
* **Demo video:** `[https://drive.google.com/file/d/1SjZYPiyvl4ne8LPGWRE0dyQ9oIioIVFB/view?usp=sharing]`

---

## Run the Project

### Prerequisites

* Python 3.14.x
* MySQL
* Git
* Windows PowerShell or another terminal

### Setup

Clone the repository and enter the project directory:

```powershell
cd reliable-ai-runtime
```

Create and activate the virtual environment:

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

### Database Configuration

Create a MySQL database named:

```text
reliable_ai_runtime
```

Create a `.env` file in the project root with:

```env
DB_NAME=reliable_ai_runtime
DB_USER=root
DB_PASSWORD=<your-local-mysql-password>
DB_HOST=localhost
DB_PORT=3306
```

Do not commit the `.env` file or any real credentials.

### Apply Migrations

```powershell
python manage.py migrate
```

### Verify the Project

```powershell
python manage.py check
```

Expected result:

```text
System check identified no issues (0 silenced).
```

### Run the Development Server

```powershell
python manage.py runserver
```

---

## Successful Scenario

The runtime supports a successful streamed conversation turn.

The flow is:

```text
created
   ↓
policy_checking
   ↓
running
   ↓
provider streaming
   ↓
response persisted
   ↓
completed
```

The fake provider streams multiple chunks. The runtime records operational events for the provider start, individual chunks, provider completion, and terminal state.

The assistant response is persisted only after successful provider completion.

---

## Failure Handling Scenarios

The runtime explicitly handles several failure and interruption cases.

### Policy Rejection

Blocked input is rejected before the provider is called.

```text
created
   ↓
policy_checking
   ↓
rejected
```

A `policy_rejected` event records the reason.

### Cancellation

Cancellation can occur before or during provider streaming.

```text
created
   ↓
policy_checking
   ↓
running
   ↓
cancelled
```

The provider receives a cancellation event through the provider contract.

### Timeout

If provider execution exceeds the configured runtime timeout:

```text
running
   ↓
timed_out
```

The runtime records a timeout event and transitions to the terminal state.

### Provider Failure

A provider failure after partial output results in:

```text
running
   ↓
failed
```

Partial output is retained on the run for debugging, while the failed response is not persisted as a successful assistant message.

### Terminal-State Race

Concurrent terminal transitions are protected using database row locking with `select_for_update()`.

Only one valid terminal transition can win.

No operational events are written after the terminal state.

---

## Tests

The complete runtime test suite was executed with:

```powershell
python manage.py test runtime
```

Verified result:

```text
Found 26 test(s).
System check identified no issues (0 silenced).

Benchmark terminal-state counts:
completed: 10
rejected: 10
cancelled: 10
timed_out: 10
failed: 10

Ran 26 tests
OK
```

The test suite covers:

* State-machine transitions
* Provider streaming
* Event recording
* Successful completion
* Policy rejection
* Cancellation before provider execution
* Cancellation during streaming
* Cancellation after provider completion
* Timeout handling
* Provider failure after partial output
* Ordered chunk events
* Safe operational traces
* Terminal-state protection
* Concurrent terminal-state races
* Runtime benchmark scenarios

---

## Acceptance Scenarios

### AC1 — Successful streamed turn

A normal input passes policy checks, streams through the provider, persists the successful response, and ends in `completed`.

### AC2 — Pre-response rejection

A blocked input is rejected before the provider is called.

### AC3 — Cancellation during streaming

Cancellation during provider streaming results in `cancelled` and prevents further processing.

### AC4 — Timeout

A provider that does not complete within the configured runtime deadline results in `timed_out`.

### AC5 — Provider failure after partial output

Partial output is retained for debugging, the provider failure is recorded, and the run ends in `failed`.

### AC6 — Terminal-state race

Concurrent terminal transitions are serialized using a database row lock so that only one terminal state is committed.

### AC7 — Safe operational trace

Operational events contain metadata such as event type, state, provider, error code, reason code, chunk sequence, and character count.

The actual response text is not stored in operational events.

---

## Benchmark

The focused benchmark can be run with:

```powershell
python manage.py test runtime.tests.RuntimeBenchmarkTests
```

The verified benchmark executes 50 deterministic runtime scenarios:

* 10 successful runs
* 10 rejected runs
* 10 cancelled runs
* 10 timed-out runs
* 10 provider-failure runs

Verified terminal-state counts:

```text
completed: 10
rejected: 10
cancelled: 10
timed_out: 10
failed: 10
```

Each scenario also verifies that the final operational trace contains exactly one terminal state and that no events occur after that terminal event.

---

## Architecture

The runtime is organized around explicit responsibilities.

### ConversationRuntime

Coordinates the complete conversation lifecycle:

```text
Input
  ↓
Policy Check
  ↓
State Transition
  ↓
Provider Execution
  ↓
Partial Output Tracking
  ↓
Response Persistence
  ↓
Terminal State
```

### Policy

The current implementation contains a simple deterministic policy check.

It runs before provider execution.

### Provider

The provider is abstracted behind a streaming interface.

The project currently uses a deterministic `FakeProvider` for testing failure, cancellation, timeout, and partial-output scenarios without relying on an external AI service.

### State Machine

Allowed lifecycle transitions are explicitly defined:

```text
created → policy_checking

policy_checking → running
policy_checking → rejected

running → completed
running → cancelled
running → timed_out
running → failed
```

Terminal states cannot transition to another state.

### Persistence

The runtime stores:

* Conversation runs
* Successful conversation messages
* Operational events

Database transactions and row locking are used around state transitions.

### Operational Trace

Each run produces an ordered operational trace.

The trace is intentionally metadata-oriented rather than storing generated response text.

---

## Technology Choices

* **Python** — primary implementation language
* **Django** — application framework and database transaction support
* **MySQL** — persistent relational database
* **Django TestCase / TransactionTestCase** — unit and concurrency-oriented tests
* **FakeProvider** — deterministic provider simulation for reliability testing

---

## Important Design Decisions

### Explicit State Machine

Conversation lifecycle states are represented explicitly instead of relying on scattered boolean flags.

This makes terminal states and valid transitions easier to reason about and test.

### Persistence Boundary

Successful assistant messages are persisted only after provider completion.

This avoids treating partial or failed provider output as a successful response.

### Provider Cancellation Contract

The provider receives a cancellation event so that cancellation can be propagated into the streaming operation.

### Database Row Locking

State transitions use `select_for_update()` inside a transaction to protect against concurrent terminal-state races.

### Deterministic Failure Injection

The fake provider supports controlled failure and streaming behavior so reliability scenarios can be tested repeatedly without depending on an external service.

---

## Assumptions and Limitations

The current implementation intentionally focuses on the reliability runtime rather than a complete production AI platform.

Current limitations include:

* The provider is a deterministic fake provider.
* Policy checking is intentionally simple.
* There is no authentication or billing.
* There is no long-term conversation memory.
* There are no retrieval or agent/tool integrations.
* There is no polished chat UI.
* Cancellation is cooperative.
* Timeout detection occurs at streaming iteration boundaries.
* There is no resume-from-checkpoint functionality.
* There is no automatic retry mechanism.

These are deliberate scope boundaries for the challenge implementation.

---

## Production and Scale Considerations

A production implementation could extend this design with:

* A real streaming AI provider
* Stronger moderation and policy enforcement
* Asynchronous/background streaming workers
* Durable cancellation signalling
* End-to-end deadlines
* Database indexes and query optimization
* Structured observability and metrics
* Distributed coordination where required
* Authentication and authorization
* Rate limiting
* Carefully designed retry policies
* Secure secret management
* Provider-specific error classification
* More comprehensive integration and load testing

The core state-machine and persistence boundaries would remain useful as the runtime scales.

---

## AI Usage

AI assistance was used during development.

ChatGPT was used to help with:

* Understanding and decomposing the challenge requirements
* Exploring the runtime architecture
* Identifying reliability and concurrency edge cases
* Designing focused test scenarios
* Improving benchmark coverage
* Reviewing documentation and submission structure

The generated suggestions were reviewed, adapted to the project, implemented, and verified through the project's own tests and runtime checks.

The final implementation and submission are the candidate's responsibility.

---

## Credibility Note

The implementation was developed specifically for this product engineering challenge.

No previous production system is being claimed as evidence for this challenge implementation.

The design decisions, tests, failure scenarios, and benchmark results documented above are based on the submitted code and the verification performed against it.

---

## Verification Summary

Final local verification completed successfully:

```powershell
python manage.py check
```

Result:

```text
System check identified no issues (0 silenced).
```

Full test suite:

```powershell
python manage.py test runtime
```

Result:

```text
26 tests
OK
```

Focused benchmark:

```powershell
python manage.py test runtime.tests.RuntimeBenchmarkTests
```

Result:

```text
50 deterministic scenarios
completed: 10
rejected: 10
cancelled: 10
timed_out: 10
failed: 10
OK
```
