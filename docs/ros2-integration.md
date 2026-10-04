# ROS 2 integration plan

The transport core in `robotics/atlas_bridge` and the `rclpy`/Nav2 wrapper in `robotics/atlas_ros` are implemented. Runtime validation requires Ubuntu 24.04, ROS 2 Jazzy, Gazebo Harmonic, and Nav2. Keep the ATLAS API and dashboard on macOS if preferred; the Ubuntu guest only needs network access to the API and the same bridge key.

## Environment

Use an Ubuntu 24.04 machine or virtual machine with at least 4 CPU cores, 8 GB RAM, and hardware acceleration when available. Install ROS 2 Jazzy Desktop, Gazebo Harmonic, Nav2, TurtleBot simulation packages, `python3-httpx`, and `python3-yaml` from their documented package sources. Confirm the baseline before adding ATLAS:

```sh
source /opt/ros/jazzy/setup.bash
ros2 doctor --report
gz sim --version
ros2 pkg list | grep nav2
```

Run the standard Nav2 simulation and send one waypoint from RViz. This separates environment or graphics failures from ATLAS bridge failures.

## Build the adapter

Create a colcon workspace and link the package from this repository. Replace `/path/to/ATLAS` with the repository location visible inside Ubuntu.

```sh
mkdir -p ~/atlas_ros_ws/src
ln -s /path/to/ATLAS/robotics/atlas_ros ~/atlas_ros_ws/src/atlas_ros
cd ~/atlas_ros_ws
source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
export PYTHONPATH=/path/to/ATLAS:$PYTHONPATH
export ATLAS_TELEMETRY_API_KEY='the-same-key-used-by-the-api'
ros2 launch atlas_ros bridge.launch.py
```

Edit `robotics/atlas_ros/config/bridge.yaml` before building when the API is not on the Ubuntu host. A virtual machine normally needs the macOS host's reachable LAN or host-only address instead of `127.0.0.1`.

## Bridge contract

The first ROS adapter will represent `robot-1` and use these inputs:

| ROS source | ATLAS field |
| --- | --- |
| `/odom` (`nav_msgs/Odometry`) | `position.x`, `position.y`, event timestamp |
| `/battery_state` (`sensor_msgs/BatteryState`) | battery percentage |
| `/diagnostics` (`diagnostic_msgs/DiagnosticArray`) | sensor status |
| Nav2 action feedback | active mission progress |

The node polls `GET /api/missions?robot_id=robot-1&status=running`, submits the waypoint list through Nav2's `NavigateThroughPoses` action, and reports observations through the durable outbox. It never publishes velocity or motor commands. A mission cancelled in ATLAS cancels the Nav2 goal. A rejected or aborted Nav2 goal sends authenticated failure telemetry, fails the mission, creates a `navigation_failure` incident, and becomes available to the evidence-based investigator.

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
