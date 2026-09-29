# ROS 2 integration plan

The transport core is already implemented in `robotics/atlas_bridge` and runs without ROS. The remaining work requires Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, and Nav2. Keep the ATLAS API and dashboard on macOS if preferred; the Ubuntu guest only needs network access to the API and the same bridge key.

## Environment

Use an Ubuntu 24.04 machine or virtual machine with at least 4 CPU cores, 8 GB RAM, and hardware acceleration when available. Install ROS 2 Jazzy Desktop, Gazebo Harmonic, Nav2, TurtleBot simulation packages, `python3-httpx`, and `python3-yaml` from their documented package sources. Confirm the baseline before adding ATLAS:

```sh
source /opt/ros/jazzy/setup.bash
ros2 doctor --report
gz sim --version
ros2 pkg list | grep nav2
```

Run the standard Nav2 simulation and send one waypoint from RViz. This separates environment or graphics failures from ATLAS bridge failures.

## Bridge contract

The first ROS adapter will represent `robot-1` and use these inputs:

| ROS source | ATLAS field |
| --- | --- |
| `/odom` (`nav_msgs/Odometry`) | `position.x`, `position.y`, event timestamp |
| `/battery_state` (`sensor_msgs/BatteryState`) | battery percentage |
| `/diagnostics` (`diagnostic_msgs/DiagnosticArray`) | sensor status |
| Nav2 action feedback | active mission progress |

The node will poll `GET /api/missions?robot_id=robot-1&status=running`, submit the waypoint list through Nav2's `NavigateThroughPoses` action, and report observations through the durable outbox. It will never publish velocity or motor commands. A mission cancelled in ATLAS must cancel the Nav2 goal; a Nav2 abort must produce failure evidence rather than silently retrying forever.

Configure the adapter with the API URL, robot ID, bridge key, outbox path, topic names, map frame, and polling intervals. Secrets belong in the runtime environment rather than ROS parameters printed by diagnostics.

## Acceptance sequence

1. Start ATLAS and confirm `/health`.
2. Start Gazebo, Nav2, and one simulated robot.
3. Start the bridge and confirm idle authenticated telemetry appears for `robot-1`.
4. Create and approve a waypoint mission in the dashboard.
5. Confirm the Nav2 goal matches the approved waypoints.
6. Confirm position and battery data appear in ATLAS during execution.
7. Stop the API briefly, generate telemetry, restart it, and verify the outbox drains without duplicate records.
8. Cancel a second mission and verify the active Nav2 goal is cancelled.

Do not expand to five simulated robots until this sequence passes reproducibly for one robot.
