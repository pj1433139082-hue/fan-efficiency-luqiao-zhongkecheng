"""路桥二期公共契约；参数含义来自已核对的311逻辑。"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import math

REPO_ROOT = Path(__file__).resolve().parents[1]
EFFICIENCY_SOURCE = REPO_ROOT / "models/_drafts/fan-efficiency-luqiao-zhongkecheng/src/model.py"
BJ = timezone(timedelta(hours=8))  # 本项目现代北京时间，与311发布接口一致；不依赖Windows额外时区包。

MACHINES = {
    "PS1061-BE_GFJF_0002-C_003_0004": "二期5#曝气风机",
    "PS1061-BE_GFJF_0002-C_003_0001": "二期6#曝气风机",
}

OUTPUTS = ("RESULT_VALID", "TARGET_FLOW", "TOTAL_FLOW", "FAN5_FLOW", "FAN6_FLOW")

PHYSICAL = ("inlet_flow", "outlet_pressure", "motor_power", "inlet_temperature", "elevation")

EFFICIENCY_COMMIT = "c06afdb36c5b1d5476d3430de1f2c0598f5532b7"

SOURCE_HASHES = {
    "efficiency.py": "17f0bdc5a697069ea9707ee4fd6258d9216311a8f7dd3b986d64838209a7c533",
    "combination.py": "3179315e8f473b1112e5b9506091f0763f0b5cf3d60389dd13026a1b69dd0ead",
}

def check_sources():
    paths = {"efficiency.py": EFFICIENCY_SOURCE, "combination.py": Path(__file__).with_name("core.py")}
    for name, path in paths.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_HASHES[name]:
            raise ValueError("SOURCE_DIGEST_MISMATCH: " + name)


def time_value(value):
    if not isinstance(value, str):
        raise ValueError("时间必须是带时区的ISO字符串")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("时间必须是带时区的ISO字符串") from None
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("不接受无时区时间")
    return stamp.astimezone(BJ)

def real(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " 必须是有限数值，不能用字符串或布尔值替代")
    return float(value)

def flag(value, name):
    if isinstance(value, bool) or value not in (0, 1):
        raise ValueError(name + " 必须为数值0或1")
    return int(value)

def boolean(value, name):
    if not isinstance(value, bool):
        raise ValueError(name + " 必须是true/false")
    return value

def blank_result():
    return {"RESULT_VALID": 0, **{name: 0.0 for name in OUTPUTS[1:]}}

def _minute(stamp):
    return stamp.replace(second=0, microsecond=0)

def _validate_curves(bundle):
    if (bundle.get("schema_version") != 1 or bundle.get("flow_unit") != "m3/min"
            or bundle.get("model_id") != "luqiao-phase2-fan-combination"
            or bundle.get("efficiency_caliber") != "eta_excel"
            or bundle.get("source_hashes") != SOURCE_HASHES
            or bundle.get("efficiency_commit") != EFFICIENCY_COMMIT
            or set(bundle.get("machines", {})) != set(MACHINES)):
        raise ValueError("曲线身份、来源、单位或设备不匹配")
    start, end = time_value(bundle["history_start"]), time_value(bundle["history_end_exclusive"])
    if start >= end:
        raise ValueError("曲线历史边界无效")
    for point, curve in bundle["machines"].items():
        if curve["status"] == "OK":
            lo, hi, eta = (real(curve[k], point + ":" + k) for k in ("q_min", "q_max", "eta"))
            if not 0 <= lo <= hi or not 0.2 <= eta <= 1 or curve["n_kept"] < 1:
                raise ValueError("无效的逐台曲线摘要")
        elif curve["status"] != "INSUFFICIENT_POINTS":
            raise ValueError("不接受未知历史曲线状态")
    return end
