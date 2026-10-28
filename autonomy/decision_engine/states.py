TERMINAL = {"completed", "cancelled", "aborted"}
ACTIVE = {"taking_off", "outbound", "delivering", "returning", "landing"}
TRANSITIONS = {
    "requested": {"planned", "cancelled"},
    "planned": {"validated", "requested", "cancelled"},
    "validated": {"authorized", "requested", "cancelled"},
    "authorized": {"taking_off", "requested", "cancelled"},
    "taking_off": {"outbound", "returning", "paused"},
    "outbound": {"delivering", "returning", "paused"},
    "delivering": {"returning", "paused"},
    "returning": {"landing", "paused"},
    "landing": {"completed", "cancelled", "aborted"},
    "paused": {"returning"},
    "completed": set(),
    "cancelled": set(),
    "aborted": set(),
}


def check_transition(current, target):
    if target not in TRANSITIONS[current]:
        raise ValueError(f"Invalid mission transition: {current} → {target}")
