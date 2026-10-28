# PX4 SITL / Gazebo evaluation

The current model is deterministic kinematics, not PX4 flight dynamics. PX4 supports
SITL and established simulator integration; Gazebo adds vehicle/environment physics
at a substantial CPU and installation cost. See the official
[PX4 simulation guide](https://docs.px4.io/main/en/simulation/).

Decision: retain a small deterministic logistics simulator for this release. Add a
separate pinned PX4/Gazebo profile with software-only network isolation, reproducible
vehicle/environment definitions and benchmark evidence in a later authorized phase.
No firmware, SITL executable, Gazebo world or physical transport has been installed
or run. Software simulation alone cannot qualify physical flight.
