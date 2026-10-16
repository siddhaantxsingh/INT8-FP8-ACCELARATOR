#!/usr/bin/env python3
"""Summarise one ORFS run directory (WORK_HOME) as a JSON line.

Usage: collect.py <run dir> <platform> <design nickname> <clock ns>
Reads the per-stage metric JSON files that ORFS writes to logs/. Missing
stages give null values (e.g. a run stopped after placement).
"""
import glob
import json
import os
import sys

run, plat, design, clk = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
logs = os.path.join(run, "logs", plat, design, "base")
m = {}
for f in sorted(glob.glob(os.path.join(logs, "*.json"))):
    try:
        m.update(json.load(open(f)))
    except (OSError, ValueError):
        pass


def g(k):
    return m.get(k)


out = {
    "platform": plat, "design": design, "clock_ns": clk,
    "synth_cells": g("synth__design__instance__count__stdcell"),
    "synth_area_um2": g("synth__design__instance__area__stdcell"),
    "floorplan_setup_wns_ns": g("floorplan__timing__setup__ws"),
    "cts_setup_wns_ns": g("cts__timing__setup__ws"),
    "grt_setup_wns_ns": g("globalroute__timing__setup__ws"),
    "final_cells": g("finish__design__instance__count__stdcell"),
    "final_cell_area_um2": g("finish__design__instance__area__stdcell"),
    "core_area_um2": g("finish__design__core__area"),
    "die_area_um2": g("finish__design__die__area"),
    "utilization": g("finish__design__instance__utilization"),
    "setup_wns_ns": g("finish__timing__setup__ws"),
    "setup_tns_ns": g("finish__timing__setup__tns"),
    "hold_wns_ns": g("finish__timing__hold__ws"),
    "hold_tns_ns": g("finish__timing__hold__tns"),
    "fmax_mhz": (g("finish__timing__fmax") or 0) / 1e6 or None,
    "power_total_w": g("finish__power__total"),
    "power_internal_w": g("finish__power__internal__total"),
    "power_switching_w": g("finish__power__switching__total"),
    "power_leakage_w": g("finish__power__leakage__total"),
    "route_drc_errors": g("detailedroute__route__drc_errors"),
    "antenna_violating_nets": g("detailedroute__antenna__violating__nets"),
    "flow_errors": g("finish__flow__errors__count"),
}
out["timing_closed"] = (out["setup_wns_ns"] is not None and out["setup_wns_ns"] >= 0
                        and (out["hold_wns_ns"] or 0) >= 0 and out["route_drc_errors"] == 0)
print(json.dumps(out))
