"""One-robot ROS 2 adapter from ATLAS missions to Nav2 actions."""

import math
import os
from datetime import datetime, timezone

import httpx
import rclpy
from action_msgs.msg import GoalStatus
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateThroughPoses
from nav_msgs.msg import Odometry
from rclpy.action import ActionClient
from rclpy.node import Node
from sensor_msgs.msg import BatteryState

from robotics.atlas_bridge import (
    AtlasBridge,
    MissionCommand,
    MissionCoordinator,
    TelemetryEvent,
    TelemetryOutbox,
    ros_event_id,
)


class AtlasBridgeNode(Node):
    def __init__(self):
        super().__init__("atlas_bridge")
        self.declare_parameter("api_url", "http://127.0.0.1:8000")
        self.declare_parameter("robot_id", "robot-1")
        self.declare_parameter("outbox_path", "/tmp/atlas-robot-1-outbox.db")
        self.declare_parameter("odom_topic", "/odom")
        self.declare_parameter("battery_topic", "/battery_state")
        self.declare_parameter("diagnostics_topic", "/diagnostics")
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("mission_poll_seconds", 1.0)
        self.declare_parameter("telemetry_seconds", 1.0)

        self.robot_id = self._parameter("robot_id")
        api_key = os.getenv("ATLAS_TELEMETRY_API_KEY")
        if not api_key:
            raise RuntimeError("ATLAS_TELEMETRY_API_KEY is required")
        self.http = httpx.Client(base_url=self._parameter("api_url"), timeout=5)
        self.outbox = TelemetryOutbox(self._parameter("outbox_path"))
        self.bridge = AtlasBridge(self.http, self.robot_id, api_key, self.outbox)
        self.coordinator = MissionCoordinator()
        self.navigator = ActionClient(self, NavigateThroughPoses, "navigate_through_poses")
        self.goal_handle = None
        self.latest_odom = None
        self.battery = 100.0
        self.sensor_status = "ok"
        self.sequence = 0

        self.create_subscription(Odometry, self._parameter("odom_topic"), self._odom, 10)
        self.create_subscription(
            BatteryState, self._parameter("battery_topic"), self._battery, 10
        )
        self.create_subscription(
            DiagnosticArray,
            self._parameter("diagnostics_topic"),
            self._diagnostics,
            10,
        )
        self.create_timer(
            float(self._parameter("mission_poll_seconds")), self._poll_mission
        )
        self.create_timer(float(self._parameter("telemetry_seconds")), self._telemetry)
        self.get_logger().info(f"ATLAS bridge ready for {self.robot_id}")

    def _parameter(self, name):
        return self.get_parameter(name).value

    def _odom(self, message):
        self.latest_odom = message

    def _battery(self, message):
        if math.isfinite(message.percentage) and message.percentage >= 0:
            value = message.percentage * 100 if message.percentage <= 1 else message.percentage
            self.battery = min(100.0, value)

    def _diagnostics(self, message):
        failed = any(
            status.level in (DiagnosticStatus.ERROR, DiagnosticStatus.STALE)
            for status in message.status
        )
        self.sensor_status = "failed" if failed else "ok"

    def _poll_mission(self):
        try:
            command = self.coordinator.reconcile(self.bridge.active_mission())
            self._execute(command)
        except (httpx.HTTPError, RuntimeError, ValueError) as error:
            self.get_logger().warning(f"Mission poll failed: {error}")

    def _execute(self, command: MissionCommand | None):
        if command is None:
            return
        if command.action == "cancel":
            if self.goal_handle:
                self.goal_handle.cancel_goal_async().add_done_callback(self._cancelled)
            else:
                self._execute(self.coordinator.cancelled())
            return
        if not self.navigator.server_is_ready():
            self.coordinator.active = None
            self.get_logger().warning("Nav2 action server is not ready")
            return
        goal = NavigateThroughPoses.Goal()
        goal.poses = [self._pose(waypoint) for waypoint in command.mission["waypoints"]]
        future = self.navigator.send_goal_async(goal)
        future.add_done_callback(
            lambda completed, mission=command.mission: self._goal_response(
                completed, mission
            )
        )

    def _pose(self, waypoint):
        pose = PoseStamped()
        pose.header.frame_id = self._parameter("map_frame")
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(waypoint["x"])
        pose.pose.position.y = float(waypoint["y"])
        pose.pose.orientation.w = 1.0
        return pose

    def _goal_response(self, future, mission):
        self.goal_handle = future.result()
        if not self.goal_handle.accepted:
            self.get_logger().error(f"Nav2 rejected mission {mission['id']}")
            self._mission_result(mission["id"], succeeded=False)
            return
        self.goal_handle.get_result_async().add_done_callback(
            lambda completed, mission_id=mission["id"]: self._goal_result(
                completed, mission_id
            )
        )

    def _goal_result(self, future, mission_id):
        status = future.result().status
        self._mission_result(mission_id, status == GoalStatus.STATUS_SUCCEEDED)

    def _mission_result(self, mission_id, succeeded):
        self.goal_handle = None
        self._send_telemetry(
            mission_id=mission_id,
            mission_status="completed" if succeeded else "running",
            navigation_status="ok" if succeeded else "failed",
        )
        self._execute(self.coordinator.finished(mission_id))

    def _cancelled(self, _future):
        self.goal_handle = None
        self._execute(self.coordinator.cancelled())

    def _telemetry(self):
        self._send_telemetry(
            mission_id=self.coordinator.active["id"] if self.coordinator.active else None
        )

    def _send_telemetry(
        self, mission_id=None, mission_status="running", navigation_status="ok"
    ):
        if self.latest_odom is None:
            self.bridge.flush()
            return
        stamp = self.latest_odom.header.stamp
        nanoseconds = stamp.sec * 1_000_000_000 + stamp.nanosec
        self.sequence += 1
        position = self.latest_odom.pose.pose.position
        event = TelemetryEvent(
            event_id=ros_event_id(self.robot_id, nanoseconds, self.sequence),
            robot_id=self.robot_id,
            occurred_at=datetime.fromtimestamp(
                nanoseconds / 1_000_000_000, timezone.utc
            ).isoformat(),
            x=position.x,
            y=position.y,
            battery=self.battery,
            mission_id=mission_id,
            sensor_status=self.sensor_status,
            navigation_status=navigation_status,
            mission_status=mission_status,
        )
        try:
            result = self.bridge.submit(event)
            if result.retained:
                self.get_logger().warning(
                    f"Telemetry outbox retains {result.retained} event(s)"
                )
        except (httpx.HTTPError, ValueError) as error:
            self.get_logger().warning(f"Telemetry delivery failed: {error}")

    def destroy_node(self):
        self.http.close()
        self.outbox.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = AtlasBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
