"""No physical device transport exists in the simulation release."""

from autonomy.safety_supervisor.supervisor import physical_command


class DisabledFlightAdapter:
    mode = "disabled"

    def connect(self, *args, **kwargs):
        return physical_command(*args, **kwargs)

    def send(self, *args, **kwargs):
        return physical_command(*args, **kwargs)
