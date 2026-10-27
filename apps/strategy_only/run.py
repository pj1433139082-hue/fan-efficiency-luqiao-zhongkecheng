"""独立组合策略：效率结果→曲线，或曲线+当前风量→推荐；不联网。"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integrated"))
from luqiao_fan import cli
from fan_combination.strategy import prepare_curves_from_points

if __name__ == "__main__":
    cli.prepare_curves = prepare_curves_from_points
    raise SystemExit(cli.main())

