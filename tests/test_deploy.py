"""Deployment artifact tests.

Service units rot silently: a renamed CLI flag breaks production months later
and nobody notices because the unit file is "just config". These tests parse the
shipped units and assert every command and flag they reference still exists.
"""

from __future__ import annotations

import plistlib
import re
from pathlib import Path

import pytest

from omniagi.cli import build_parser
from omniagi.watchdog import main as watchdog_main


@pytest.fixture(scope="module")
def deploy_dir(repo_root: Path) -> Path:
    return repo_root / "deploy"


def _service_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "[")):
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip()
    return fields


def test_all_units_are_shipped(deploy_dir: Path) -> None:
    for name in (
        "omniagi-watchdog.service",
        "omniagi-watchdog.timer",
        "com.omniagi.watchdog.plist",
        "README.md",
    ):
        assert (deploy_dir / name).is_file(), f"deploy/{name} is missing"


def test_systemd_unit_invokes_a_real_command(deploy_dir: Path) -> None:
    fields = _service_fields(deploy_dir / "omniagi-watchdog.service")
    argv = fields["ExecStart"].split()
    assert Path(argv[0]).name == "omniagi"
    # The unit must survive a CLI refactor: parse its flags with the real parser.
    args = build_parser().parse_args(argv[1:])
    assert args.command == "watch"
    assert args.once is True


def test_systemd_unit_is_a_oneshot_because_it_exits(deploy_dir: Path) -> None:
    fields = _service_fields(deploy_dir / "omniagi-watchdog.service")
    assert fields["Type"] == "oneshot"


def test_systemd_unit_is_sandboxed(deploy_dir: Path) -> None:
    """The watchdog only reads; a unit that can write anywhere is a regression."""
    fields = _service_fields(deploy_dir / "omniagi-watchdog.service")
    assert fields["NoNewPrivileges"] == "true"
    assert fields["ProtectSystem"] == "strict"
    assert fields["ProtectHome"] == "true"
    assert "memory" in fields["ReadWritePaths"]


def test_systemd_unit_sets_the_root_env_var(deploy_dir: Path) -> None:
    from omniagi.paths import ENV_VAR

    body = (deploy_dir / "omniagi-watchdog.service").read_text(encoding="utf-8")
    assert f"Environment={ENV_VAR}=" in body


def test_timer_persists_across_downtime(deploy_dir: Path) -> None:
    """A skipped check is indistinguishable from a passing one."""
    fields = _service_fields(deploy_dir / "omniagi-watchdog.timer")
    assert fields["Persistent"] == "true"
    assert fields["Unit"] == "omniagi-watchdog.service"
    assert "OnUnitActiveSec" in fields


def test_launchd_plist_parses_and_invokes_a_real_command(deploy_dir: Path) -> None:
    with (deploy_dir / "com.omniagi.watchdog.plist").open("rb") as handle:
        plist = plistlib.load(handle)

    assert plist["Label"] == "com.omniagi.watchdog"
    argv = plist["ProgramArguments"]
    assert Path(argv[0]).name == "omniagi"
    args = build_parser().parse_args(argv[1:])
    assert args.command == "watch"
    assert args.once is True
    assert plist["StartInterval"] > 0


def test_launchd_plist_sets_the_root_env_var(deploy_dir: Path) -> None:
    from omniagi.paths import ENV_VAR

    with (deploy_dir / "com.omniagi.watchdog.plist").open("rb") as handle:
        plist = plistlib.load(handle)
    assert ENV_VAR in plist["EnvironmentVariables"]


def test_launchd_placeholders_are_obvious(deploy_dir: Path) -> None:
    """Host paths must be template placeholders, never a real developer's home."""
    body = (deploy_dir / "com.omniagi.watchdog.plist").read_text(encoding="utf-8")
    for match in re.findall(r"/Users/([^/<]+)", body):
        assert match == "CHANGE_ME", f"leaked a real home directory: /Users/{match}"


def test_documented_flags_all_exist(deploy_dir: Path) -> None:
    """Every `omniagi watch ...` invocation in the deploy guide must be valid."""
    body = (deploy_dir / "README.md").read_text(encoding="utf-8")
    invocations = re.findall(r"^omniagi watch(.*)$", body, flags=re.MULTILINE)
    assert invocations, "the deploy guide documents no watch invocation"
    for tail in invocations:
        args = build_parser().parse_args(["watch", *tail.split()])
        assert args.command == "watch"


def test_watchdog_module_accepts_the_documented_flags() -> None:
    """The scripts/watchdog.py entry point must accept them too."""
    assert watchdog_main(["--once"]) in (0, 1)
