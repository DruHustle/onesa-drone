# Kinematic simulation limits

The engine commits 5 simulated seconds per wall-clock tick. It estimates distance,
route progress and battery using explicit illustrative parameters. Takeoff, parcel
release, return and landing are discrete phases. Checkpoints are replayable after a
process restart; downtime does not imply that any aircraft moved.

No aerodynamic, propulsion, collision, GNSS sensor or battery electrochemical model
is validated. Rendered buildings are scenery, not surveyed obstacles. Synthetic
restricted circles are planner constraints. The engine cannot be used for real
navigation, airworthiness or performance certification.
