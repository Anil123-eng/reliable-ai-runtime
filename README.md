# Reliable AI Conversation Runtime

A reliable AI conversation runtime built with **Python, Django, and MySQL** for the Caygnus Product Engineering Challenge — **Problem 5: Reliable AI Conversation Runtime**.

The runtime manages an AI conversation from input validation through provider execution and persistence, while handling policy rejection, cancellation, timeouts, provider failures, partial output, and concurrent terminal-state transitions.

## Features

* Conversation lifecycle state machine
* Policy checking before provider execution
* Streaming provider output
* Partial-output persistence
* Policy rejection handling
* Cancellation before and during provider execution
* Runtime timeout handling
* Provider failure handling
* Structured operational event tracing
* Ordered event sequences
* Prevention of invalid terminal-state transitions
* Database persistence using Django ORM and MySQL
* Concurrency-safe state transitions using `select_for_update()`
* Automated test coverage
* Terminal-state benchmark

## Technology Stack

* **Python**
* **Django**
* **Django REST Framework**
* **MySQL**
* **mysqlclient**
* **python-dotenv**
* **Django ORM**
* **unittest / Django TestCase**

## Architecture

The runtime is organized around a small set of components:

```text
User Input
    │
    ▼
ConversationRuntime
    │
    ├── Policy Check
    │       ├── Allowed ───────► Running
    │       └── Rejected ──────► Rejected
    │
    ▼
Provider Execution
    │
    ├── Successful stream ─────► Completed
    ├── Cancellation ──────────► Cancelled
    ├── Timeout ───────────────► Timed Out
    └── Provider failure ──────► Failed
    │
    ▼
Persistence + Operational Events
```

### Main Components

#### `runtime/service.py`

Contains `ConversationRuntime`, which coordinates:

* run creation
* policy checking
* state transitions
* provider execution
* streaming chunks
* cancellation
* timeout handling
* provider failures
* successful response persistence

#### `runtime/provider.py`

Contains the `FakeProvider` used for deterministic testing.

It can simulate:

* normal streaming
* provider failures
* cancellation-aware streaming
* blocking/waiting behavior for timeout and cancellation scenarios

#### `runtime/state_machine.py`

Defines valid conversation state transitions.

Terminal states are:

```text
completed
rejected
cancelled
timed_out
failed
```

Once a run reaches a terminal state, another transition is not allowed.

#### `runtime/models.py`

Defines the database models:

* `ConversationRun`
* `ConversationMessage`
* `OperationalEvent`

#### `runtime/events.py`

Records ordered operational events for each conversation run.

The operational trace records lifecycle information without storing the generated response text inside the event trace.

## Project Structure

```text
reliable-ai-runtime/
│
├── config/
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── runtime/
│   ├── migrations/
│   ├── admin.py
│   ├── apps.py
│   ├── events.py
│   ├── models.py
│   ├── provider.py
│   ├── service.py
│   ├── state_machine.py
│   ├── tests.py
│   └── views.py
│
├── manage.py
├── requirements.txt
├── SUBMISSION.md
├── .gitignore
└── README.md
```

## Requirements

Before running the project, install:

* Python
* MySQL Server
* Git

The project was developed and tested with Python 3.14.x.

## Setup

Clone the repository:

```bash
git clone https://github.com/Anil123-eng/reliable-ai-runtime.git
cd reliable-ai-runtime
```

Create and activate a virtual environment.

### Windows PowerShell

```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Environment Variables

The application reads database configuration from a `.env` file.

Create:

```text
.env
```

with:

```env
DB_NAME=reliable_ai_runtime
DB_USER=root
DB_PASSWORD=YOUR_MYSQL_PASSWORD
DB_HOST=localhost
DB_PORT=3306
```

Replace `YOUR_MYSQL_PASSWORD` with the local MySQL password.

**Do not commit `.env` to GitHub.**

The repository's `.gitignore` excludes `.env`, the virtual environment, Python cache files, and the local SQLite database file.

## Database Setup

Create the MySQL database:

```sql
CREATE DATABASE reliable_ai_runtime;
```

Then apply Django migrations:

```powershell
python manage.py migrate
```

## Verify the Project

Run Django's system checks:

```powershell
python manage.py check
```

A successful check should report:

```text
System check identified no issues
```

## Run the Development Server

```powershell
python manage.py runserver
```

The Django development server will start locally.

## Running Tests

Run the complete runtime test suite:

```powershell
python manage.py test runtime
```

The current test suite contains **26 tests**.

The verified result is:

```text
Found 26 test(s).

Ran 26 tests in 1.587s

OK
```

## Benchmark

Run the focused benchmark:

```powershell
python manage.py test runtime.tests.RuntimeBenchmarkTests
```

The benchmark executes 10 runs for each major terminal outcome.

Verified terminal-state counts:

```text
completed: 10
rejected: 10
cancelled: 10
timed_out: 10
failed: 10
```

The benchmark also verifies that each run has exactly one terminal event and that no events occur after the terminal state.

## Failure Handling

The runtime explicitly handles several failure scenarios.

### Policy Rejection

Blocked input is rejected before the provider is called:

```text
policy_checking
        │
        ▼
    rejected
```

### Cancellation

Cancellation can occur:

* before provider execution
* during streaming
* after the provider finishes but before completion

The runtime records the cancellation reason and moves the run to:

```text
cancelled
```

### Timeout

If provider execution exceeds the configured runtime timeout, the runtime records a timeout event and transitions to:

```text
timed_out
```

### Provider Failure

A provider failure can occur after partial output has already been received.

The partial output is preserved and the run transitions to:

```text
failed
```

### Concurrent Terminal Transitions

State changes use a database row lock:

```python
ConversationRun.objects.select_for_update()
```

This prevents competing requests from both successfully moving the same run into different terminal states.

## State Machine

The supported lifecycle is:

```text
created
   │
   ▼
policy_checking
   ├──────────────► rejected
   │
   ▼
running
   ├──────────────► completed
   ├──────────────► cancelled
   ├──────────────► timed_out
   └──────────────► failed
```

Terminal states cannot transition to another state.

## Operational Events

The runtime records structured events such as:

```text
run_created
state_change
policy_allowed
policy_rejected
provider_start
chunk
provider_complete
provider_error
cancel_requested
timeout
```

Events contain metadata such as:

* sequence number
* event type
* state
* provider
* error code
* reason code
* chunk sequence
* character count
* timestamp

The event trace does not store the generated response text.

## Important Design Decisions

### Django ORM + MySQL

Django ORM provides a straightforward persistence layer for conversation runs, messages, and operational events.

MySQL was selected as the relational database for the project.

### Explicit State Machine

Conversation states are explicitly defined rather than relying on implicit status changes.

This makes terminal states and invalid transitions easier to test and reason about.

### Deterministic Fake Provider

A deterministic fake provider makes failure and concurrency scenarios reproducible during automated testing.

### Database-Level Locking

`select_for_update()` is used when changing state so concurrent terminal transitions are serialized at the database level.

## Current Limitations

This implementation is intentionally focused on the challenge requirements.

It does not currently include:

* a production LLM provider
* automatic retry/recovery
* distributed task queues
* authentication
* billing
* long-term conversation memory
* production observability infrastructure
* a production frontend
* deployment configuration

The failure scenarios demonstrate **failure handling**, not automatic recovery or retry.

## Production Considerations

A production version could additionally include:

* idempotency keys
* durable job queues
* provider retry policies
* exponential backoff
* distributed cancellation
* structured application logging
* metrics and tracing
* rate limiting
* authentication and authorization
* stronger database constraints
* production LLM provider integration
* deployment and monitoring configuration

## Demo Video

The recorded project demonstration is available here:

https://drive.google.com/file/d/1SjZYPiyvl4ne8LPGWRE0dyQ9oIioIVFB/view?usp=sharing

## Submission

The detailed challenge submission document is available in:

```text
SUBMISSION.md
```

It contains the candidate information, setup instructions, architecture, testing results, benchmark information, tradeoffs, limitations, and AI usage disclosure.

## AI Usage

AI assistance was used during development for guidance, debugging support, test design, documentation, and review.

The implementation was reviewed and tested locally, and the candidate is responsible for the submitted code and documentation.

## Author

**M Anil**

GitHub:

https://github.com/Anil123-eng

---

**Caygnus Product Engineering Challenge — Problem 5: Reliable AI Conversation Runtime**
