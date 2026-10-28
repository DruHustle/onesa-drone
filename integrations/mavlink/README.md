# MAVLink boundary

No socket, UDP listener, serial transport, message encoder, arm, mode or waypoint
upload is implemented. `edge.boundary.DisabledFlightAdapter` rejects connection and
send attempts. MAVLink support requires separately authorized development, signed
message validation, device identity provisioning and isolated SITL-only qualification
before any hardware work. It is excluded from this release's execution path.
