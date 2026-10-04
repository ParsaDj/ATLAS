from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from pathlib import Path


def generate_launch_description():
    config = Path(get_package_share_directory("atlas_ros")) / "config" / "bridge.yaml"
    return LaunchDescription(
        [
            Node(
                package="atlas_ros",
                executable="bridge_node",
                name="atlas_bridge",
                output="screen",
                parameters=[str(config)],
            )
        ]
    )
