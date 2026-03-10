#!/usr/bin/env python3
"""Packaging metadata for the legacy global CodeGuard CLI."""

from pathlib import Path

from setuptools import setup

ROOT = Path(__file__).resolve().parent
long_description = (ROOT / "README.md").read_text(encoding="utf-8")

setup(
    name="codeguard-cli",
    version="1.0.0",
    author="CodeGuard Team",
    description="Global CLI tool for CodeGuard code protection",
    long_description=long_description,
    long_description_content_type="text/markdown",
    py_modules=["codeguard_cli"],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "codeguard=codeguard_cli:main",
        ],
    },
    install_requires=[],
)
