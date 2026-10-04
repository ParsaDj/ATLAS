from glob import glob
from setuptools import find_packages, setup


package_name = "atlas_ros"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools", "httpx"],
    zip_safe=True,
    maintainer="ATLAS Maintainer",
    maintainer_email="maintainer@example.invalid",
    description="ROS 2 and Nav2 adapter for ATLAS.",
    license="Apache-2.0",
    entry_points={"console_scripts": ["bridge_node = atlas_ros.node:main"]},
)
