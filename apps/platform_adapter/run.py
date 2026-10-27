"""公开版在线调用入口；认证和目标地址只能来自外部IOT_*环境变量。"""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
from platform2622.main import online_feature_engineering

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--curves", required=True, help="调用者在私有目录准备的本厂曲线；仓库示例仅合成测试")
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8-sig"))
    curves = json.loads(Path(args.curves).read_text(encoding="utf-8-sig"))
    result = online_feature_engineering(pd.DataFrame([request]), {"curves": curves})
    print(result.to_json(orient="records"))

