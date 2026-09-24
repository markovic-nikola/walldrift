from walldrift import systemd


def test_units_use_interval_and_command() -> None:
    units = systemd.units(1800, "/home/u/.local/bin/walldrift")
    assert set(units) == {"walldrift.service", "walldrift.timer"}
    assert "ExecStart=/home/u/.local/bin/walldrift next" in units["walldrift.service"]
    assert "OnUnitActiveSec=1800s" in units["walldrift.timer"]
    assert "OnActiveSec=1800s" in units["walldrift.timer"]
