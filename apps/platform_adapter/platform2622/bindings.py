"""路桥二期PS1061：仅5#/6#，数组顺序固定；不接收其他厂的测点。"""
from datetime import datetime, timedelta, timezone

BJ = timezone(timedelta(hours=8))
FACTORY = "PS1061"
POINTS = ("PS1061-BE_GFJF_0002-C_003_0004", "PS1061-BE_GFJF_0002-C_003_0001")
SIGNALS = ("V_IF", "S_RUN", "A_FLT", "A_SAG")
BINDINGS = {signal: [point + "-" + signal for point in POINTS] for signal in SIGNALS}
OUTPUTS = ("RESULT_VALID", "TARGET_FLOW", "TOTAL_FLOW", "FAN5_FLOW", "FAN6_FLOW")
SCOPE = "LUQIAO2622_PS1061_PHASE2"


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("as_of must be an ISO timestamp string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("Timezone required")
    return stamp.astimezone(BJ)

