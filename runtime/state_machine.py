TERMINAL_STATES = {
    "completed",
    "rejected",
    "cancelled",
    "timed_out",
    "failed",
}


def is_terminal(state):
    return state in TERMINAL_STATES


def can_transition(current_state, new_state):
    if is_terminal(current_state):
        return False

    allowed_transitions = {
        "created": {"policy_checking"},
        "policy_checking": {"running", "rejected"},
        "running": {
            "completed",
            "cancelled",
            "timed_out",
            "failed",
        },
    }

    return new_state in allowed_transitions.get(current_state, set())