"""编码请求→路桥二期同刻快照→已冻结7天曲线→原v1.1组合。在线不fit/不刷新历史。"""
from copy import deepcopy
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from .bindings import FACTORY, POINTS, SIGNALS, BINDINGS, OUTPUTS, BJ, SCOPE, parse_time
from .fetch import IotClient, IotReadError
from fan_combination import core as rules
from fan_combination.time_input import optional_time


def invalid():
    return {"RESULT_VALID": 0, **{name: 0.0 for name in OUTPUTS[1:]}}


def validate_request(raw_df, aux):
    if not isinstance(raw_df, pd.DataFrame) or len(raw_df) != 1:
        raise ValueError("Exactly one configuration request required")
    row = raw_df.iloc[0]
    if row.get("factory_code") != FACTORY:
        raise ValueError("Wrong factory; only PS1061 phase2")
    for signal, codes in BINDINGS.items():
        supplied = row.get(signal)
        if not isinstance(supplied, (list, tuple, np.ndarray)) or list(supplied) != codes:
            raise ValueError("Wrong point-code array/order: " + signal)
    supplied = optional_time(row.get("as_of"))
    if supplied is None:
        cutoff = datetime.now(BJ).replace(microsecond=0)
    else:
        cutoff = parse_time(supplied)
    if cutoff < parse_time(aux["curves"]["history_end_exclusive"]):
        raise ValueError("Request before frozen historical epoch")
    return cutoff


def snapshot_result(raw, curves, start, end):
    required = {"data_time", "column", "value", "status"}
    if raw.empty or not required <= set(raw.columns):
        return invalid(), {"status": "NO_COMPLETE_SNAPSHOT"}
    expected = {p + "|" + s for p in POINTS for s in SIGNALS}
    if not set(raw.column) <= expected:
        raise ValueError("Unexpected point identity")
    frame = raw.copy()
    for value in frame.data_time.unique():
        parse_time(value)
    frame["time"] = pd.to_datetime(frame.data_time, utc=True)
    if frame.duplicated(["time", "column"]).any():
        raise ValueError("Duplicate point timestamp")
    if not ((frame.time >= start) & (frame.time < end)).all():
        raise ValueError("Out-of-window samples")
    frame["value"] = pd.to_numeric(frame.value, errors="coerce").replace([np.inf, -np.inf], np.nan)
    # 不把布尔值作为实际风量；状态允许数值0/1。
    booleans = raw.value.map(lambda v: isinstance(v, (bool, np.bool_))) & raw.column.str.endswith("|V_IF")
    frame.loc[booleans, "value"] = np.nan
    wide = frame.pivot(index="time", columns="column", values="value").reindex(columns=sorted(expected)).sort_index()
    quality = frame.pivot(index="time", columns="column", values="status").reindex(index=wide.index, columns=wide.columns)
    flags = [p + "|" + s for p in POINTS for s in SIGNALS if s != "V_IF"]
    complete = (wide.notna() & quality.astype(str).eq("0")).all(axis=1) & wide[flags].isin([0, 1]).all(axis=1)
    if not complete.any():
        return invalid(), {"status": "NO_COMPLETE_SNAPSHOT"}
    stamp = wide.index[complete][-1]
    if stamp < pd.Timestamp(curves["history_end_exclusive"]):
        return invalid(), {"status": "SNAPSHOT_BEFORE_CURVE_FREEZE"}
    snapshot = wide.loc[stamp]
    if any(snapshot[p + "|V_IF"] < 0 or (snapshot[p + "|S_RUN"] == 0 and snapshot[p + "|V_IF"] > rules.EPS) for p in POINTS):
        return invalid(), {"status": "CURRENT_FLOW_RUN_CONFLICT"}
    target = sum(float(snapshot[p + "|V_IF"]) for p in POINTS)
    units = []
    for point in POINTS:
        curve = deepcopy(curves["machines"][point])
        if snapshot[point + "|A_FLT"] != 0 or snapshot[point + "|A_SAG"] != 0:
            curve["status"] = "INELIGIBLE"
        units.append({"id": point, "curve": curve})
    solved = rules.solve(units, target, 5)
    detail = {"status": solved["status"], "observed_at": stamp.tz_convert("Asia/Shanghai").isoformat(),
              "snapshot_lag_seconds": (pd.Timestamp(end) - stamp).total_seconds(), "automatic_dispatch": False, "scope": SCOPE}
    rec = solved["recommendation"]
    if rec is None:
        return invalid(), detail
    selected = dict(zip(rec["S"], rec["q"]))
    flows = [float(selected.get(p, 0.0)) for p in POINTS]
    total = float(rec["Q_rec"])
    if abs(sum(flows) - total) > 1e-6 or not .95 * target - 1e-9 <= total <= 1.05 * target + 1e-9:
        raise ValueError("Conservation or target band failure")
    for point, q in zip(POINTS, flows):
        if point in selected and not curves["machines"][point]["q_min"] - 1e-9 <= q <= curves["machines"][point]["q_max"] + 1e-9:
            raise ValueError("Per-machine bound failure")
    return dict(zip(OUTPUTS, [1, target, total, *flows])), detail


def online_feature_engineering(raw_df, aux_dict):
    cutoff = validate_request(raw_df, aux_dict)
    start = cutoff - timedelta(hours=1)  # 工程搜索范围，不是历史窗、调度间隔或新鲜度验收阈值。
    try:
        raw, chunks = IotClient().fetch(start, cutoff)
        values, detail = snapshot_result(raw, aux_dict["curves"], start, cutoff)
    except IotReadError:
        values, detail = invalid(), {"status": "CURRENT_FETCH_FAILED", "automatic_dispatch": False}
    frame = pd.DataFrame([values], columns=OUTPUTS)
    frame["RESULT_VALID"] = frame.RESULT_VALID.astype("int64")
    for name in OUTPUTS[1:]:
        frame[name] = frame[name].astype("float64")
    frame.attrs["diagnostics"] = detail
    return frame


def online_post_processing(raw_prediction, aux_dict):
    if len(raw_prediction) != 1:
        raise ValueError("Expected exactly one result row")
    return raw_prediction.loc[:, list(OUTPUTS)].copy()

