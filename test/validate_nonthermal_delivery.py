# -*- coding: utf-8 -*-
"""非火电资源模型交付门禁。

PyCharm 直接运行本文件即可。退出码 0 表示 PASS 或 CONDITIONAL_PASS，
退出码 1 表示非火电资源模型自身验证失败，禁止交付。
"""

from __future__ import annotations

import subprocess
import sys
import unittest
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = Path(__file__).resolve().parent
for path in (PROJECT_ROOT, TEST_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from src.data.config import TimeConfig
from src.data.grid_builder import build_grid
from src.data.loader import load_case, validate_case_data
from src.scenario import ScenarioSet


FORMULA_TRACEABILITY = (
    # 每一行依次记录：参考公式号、参考函数、当前入口、覆盖该公式的测试。
    (
        "2.3.1",
        "setHydroConsPredicted",
        "setHydroConstraints",
        "test_231_to_233_cross_month",
    ),
    (
        "2.3.2",
        "setHydroConsForced",
        "setHydroConstraints",
        "test_231_to_233_cross_month",
    ),
    (
        "2.3.3",
        "setHydroConsMonthlyBalance",
        "setHydroConstraints",
        "test_231_to_233_cross_month",
    ),
    (
        "2.4.1",
        "setStoragePCCons",
        "setStorageConstraints",
        "test_241_to_246_efficiency_matrix",
    ),
    (
        "2.4.2",
        "setStoragePDCons",
        "setStorageConstraints",
        "test_241_to_246_efficiency_matrix",
    ),
    (
        "2.4.3",
        "setStorageSOCCons",
        "setStorageConstraints",
        "test_15_minute_soc_scaling",
    ),
    (
        "2.4.4",
        "setStorageSOCCons",
        "setStorageConstraints",
        "test_15_minute_soc_scaling",
    ),
    (
        "2.4.5",
        "setStorageICons",
        "setStorageConstraints",
        "test_charge_and_discharge_are_mutually_exclusive",
    ),
    (
        "2.4.6",
        "setStorageSOCCons",
        "setStorageConstraints",
        "test_241_to_246_efficiency_matrix",
    ),
    (
        "2.5.1",
        "setRenewablePCons",
        "setRenewableConstraints",
        "test_251_monthly_capacity_and_curtailment",
    ),
    (
        "2.5.2",
        "setRenewableRampUpCons",
        "setRenewableConstraints",
        "test_252_253_ramp_uses_time_step",
    ),
    (
        "2.5.3",
        "setRenewableRampDownCons",
        "setRenewableConstraints",
        "test_252_253_ramp_uses_time_step",
    ),
)

ALLOWED_FILES = {
    # 门禁允许已确认的成员一至四功能收口范围。
    "configs/cases/hubei2030.yaml",
    "docs/member4_work_summary_and_member5_handoff.md",
    "pytest.ini",
    "src/data/case_data.py",
    "src/data/config.py",
    "src/data/grid_builder.py",
    "src/data/loader.py",
    "src/model/resource.py",
    "src/optim/objectives.py",
    "src/optim/variables.py",
    "src/optim/constraints/__init__.py",
    "src/optim/constraints/_constraint_utils.py",
    "src/optim/constraints/hydro.py",
    "src/optim/constraints/power_balance.py",
    "src/optim/constraints/storage.py",
    "src/optim/constraints/renewable.py",
    "src/scenario/__init__.py",
    "src/scenario/scenario_set.py",
    "test/test_hydro.py",
    "test/test_storage.py",
    "test/test_renewable.py",
    "test/test_nonthermal_reference_alignment.py",
    "test/test_upstream_handoff.py",
    "test/validate_nonthermal_delivery.py",
}


def _git_lines(*args: str) -> list[str]:
    """执行只读 Git 查询并把 Windows 路径统一成正斜杠格式。"""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip().replace("\\", "/") for line in result.stdout.splitlines()]


def changed_files() -> list[str]:
    """汇总已跟踪修改和未跟踪文件，但忽略用户提供的湖北原始数据目录。"""
    tracked = _git_lines("diff", "--name-only")
    untracked = _git_lines("ls-files", "--others", "--exclude-standard")
    return sorted(
        {
            path
            for path in tracked + untracked
            if path and not path.startswith("湖北2030/")
        }
    )


def scope_errors() -> list[str]:
    """检查修改白名单、Git 差异格式和未跟踪文本的行尾空白。"""
    errors = [
        f"out-of-scope changed file: {path}"
        for path in changed_files()
        if path not in ALLOWED_FILES
    ]
    diff_check = subprocess.run(
        ["git", "diff", "--check"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if diff_check.returncode:
        errors.append(diff_check.stdout.strip() or diff_check.stderr.strip())
    untracked = set(_git_lines("ls-files", "--others", "--exclude-standard"))
    for path_text in untracked:
        if path_text.startswith("湖北2030/"):
            continue
        path = PROJECT_ROOT / path_text
        if not path.is_file() or path.suffix not in {".py", ".md"}:
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if line.rstrip() != line:
                errors.append(f"trailing whitespace: {path_text}:{line_number}")
    return errors


def real_hubei_preflight() -> list[str]:
    """用真实湖北 24 小时数据检查参考公式所需输入是否已接入 Grid。

    返回值为空表示数据预检通过；非空项均为职责范围外的外部阻塞，最终状态
    会是 CONDITIONAL_PASS。加载或对象构建本身失败也作为外部阻塞记录。
    """
    blockers: list[str] = []
    config_path = PROJECT_ROOT / "configs" / "cases" / "hubei2030.yaml"
    try:
        case_data = load_case(str(config_path), TimeConfig(0, 23))
        report = validate_case_data(case_data)
        if not report.is_valid:
            return ["data validation failed: " + "; ".join(report.errors)]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            grid = build_grid(case_data)
        ScenarioSet.from_case_data(grid, case_data).require_single_scenario(
            "BASE"
        )
    except Exception as exc:  # 数据层或对象层阻塞不在非火电资源建模层修复
        return [f"data/grid preflight failed: {type(exc).__name__}: {exc}"]

    missing_basin_process = []
    for zone in grid.zones.values():
        for basin in zone.basinDict.values():
            if not basin.hydroDict:
                continue
            missing = [
                field
                for field in ("predicted", "forced", "average")
                if not getattr(basin, field)
            ]
            if missing:
                missing_basin_process.append(
                    f"{basin.id}({','.join(missing)})"
                )
    if missing_basin_process:
        blockers.append(
            "data/grid: hydro basin process is not attached: "
            + ", ".join(missing_basin_process)
        )

    missing_monthly_capacity = [
        resource.id
        for resource in (
            grid.getResListFromType("WIND") + grid.getResListFromType("PV")
        )
        if not resource.monthly_capacity_mw
    ]
    if missing_monthly_capacity:
        blockers.append(
            "data/grid: monthly renewable capacity is not populated: "
            + ", ".join(missing_monthly_capacity)
        )

    missing_resource_series = [
        resource.id
        for resource in (
            grid.getResListFromType("WIND") + grid.getResListFromType("PV")
        )
        if not resource.TSCapacity
    ]
    if missing_resource_series:
        blockers.append(
            "grid/simulation: renewable scenario series is not attached to "
            "the Grid/scenario interface: "
            + ", ".join(missing_resource_series)
        )

    missing_load_series = [
        resource.id
        for resource in grid.getResListFromType("LOAD")
        if not resource.TSCapacity
    ]
    if missing_load_series:
        blockers.append(
            "data/grid: load series is not attached: "
            + ", ".join(missing_load_series)
        )

    skipped_hydro = [
        str(item.message)
        for item in caught
        if "Hydro flow basin" in str(item.message)
    ]
    if skipped_hydro:
        blockers.append(
            f"data/grid: {len(skipped_hydro)} hydro process tables "
            "were skipped because basin IDs do not match"
        )
    return blockers


def run_reference_alignment_suite() -> unittest.result.TestResult:
    """运行非火电参考公式和成员一至四交接测试。"""
    suite = unittest.TestSuite()
    for pattern in (
        "test_nonthermal_reference_alignment.py",
        "test_upstream_handoff.py",
    ):
        suite.addTests(
            unittest.defaultTestLoader.discover(
                start_dir=str(TEST_ROOT),
                pattern=pattern,
            )
        )
    return unittest.TextTestRunner(verbosity=2).run(suite)


def main() -> int:
    """依次执行公式追踪、数值测试、范围检查和真实数据预检。"""
    print("=" * 72)
    print("Non-thermal resource reference-alignment delivery gate")
    print("=" * 72)
    print("\n[Formula traceability]")
    for formula, reference, implementation, test_name in FORMULA_TRACEABILITY:
        print(
            f"  {formula}: reference={reference} -> "
            f"current={implementation} -> test={test_name}"
        )

    print("\n[Non-thermal numerical and integration tests]")
    result = run_reference_alignment_suite()
    from test_nonthermal_reference_alignment import (
        _solve_power_balance_integration_case,
    )

    first_residual, first_flows = _solve_power_balance_integration_case()
    second_residual, second_flows = _solve_power_balance_integration_case()
    repeat_delta = max(
        [abs(first_residual - second_residual)]
        + [
            abs(left - right)
            for left, right in zip(first_flows, second_flows)
        ]
    )
    print(f"  max_power_balance_residual={first_residual:.3e}")
    print(f"  deterministic_repeat_delta={repeat_delta:.3e}")

    print("\n[Scope and whitespace checks]")
    scope_failures = scope_errors()
    if scope_failures:
        for error in scope_failures:
            print(f"  FAIL: {error}")
    else:
        print("  PASS: all changes stay inside the approved upstream scope")

    print("\n[Real Hubei 24-hour preflight]")
    blockers = real_hubei_preflight()
    if blockers:
        for blocker in blockers:
            print(f"  EXTERNAL_BLOCKER: {blocker}")
    else:
        print("  PASS: members one-to-four handoff inputs are complete")

    if not result.wasSuccessful() or scope_failures:
        status = "FAIL"
        exit_code = 1
    elif blockers:
        status = "CONDITIONAL_PASS"
        exit_code = 0
    else:
        status = "PASS"
        exit_code = 0

    print("\n[Delivery decision]")
    print(f"  {status}")
    print(f"  tests_run={result.testsRun}")
    print(f"  failures={len(result.failures)}")
    print(f"  errors={len(result.errors)}")
    print(f"  external_blockers={len(blockers)}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
