"""Setup script for Simulflow."""

from setuptools import setup, find_packages
from pathlib import Path

here = Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="simulflow",
    version="2.0.0",
    description="Linux Desktop Extender - turn your Android tablet into a second monitor over USB",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/kachapman/simulflow",
    author="kachapman",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "PyQt6>=6.5.0",
        "qrcode>=7.4",
        "Pillow>=10.0.0",
        "zeroconf>=0.132",
    ],
    entry_points={
        "console_scripts": [
            "simulflow=simulflow.main:main",
        ],
    },
    package_data={
        "": ["assets/*.png"],
    },
    data_files=[
        ("share/applications", ["simulflow.desktop"]),
    ],
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: System :: Hardware",
        "Topic :: Utilities",
    ],
)
