"""Sample hysteresis and deduplicated service incidents, no external messaging."""

from dataclasses import dataclass


@dataclass
class Hysteresis:
    status: str = "unknown"
    successes: int = 0
    failures: int = 0
    transitions: int = 0

    def observe(self, healthy: bool):
        if healthy:
            self.successes += 1
            self.failures = 0
            target = "healthy" if self.successes >= 3 else self.status
        else:
            self.failures += 1
            self.successes = 0
            target = "degraded" if self.failures >= 3 else self.status
        if target != self.status:
            self.status = target
            self.transitions += 1
            return True
        return False
