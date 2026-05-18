"""仓库根目录与 data/ 路径（相对本文件解析，不依赖当前工作目录）。"""

from __future__ import annotations

import os


def project_root() -> str:
    """项目根目录（含 data/、scripts/ 的目录）。"""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def data_raw_dir() -> str:
    return os.path.join(project_root(), "data", "raw_data")


def data_output_dir() -> str:
    return os.path.join(project_root(), "data", "output_data")


def data_dashboard_dir() -> str:
    return os.path.join(project_root(), "data", "dashboard")


def data_dashboard_csv_dir() -> str:
    return os.path.join(data_dashboard_dir(), "csv")


def data_dashboard_json_dir() -> str:
    return os.path.join(data_dashboard_dir(), "json")
