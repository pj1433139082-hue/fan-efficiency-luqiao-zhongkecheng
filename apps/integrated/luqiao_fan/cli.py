"""本地prepare/recommend入口。所有输出先检查占用，再计算，暂存通过后发布到新目录。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

from .pipeline import OUTPUTS, prepare_curves, recommend


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      parse_constant=lambda s: (_ for _ in ()).throw(ValueError("JSON不接受" + s)))


def write_json(path, value):
    Path(path).write_text(json.dumps(json_safe(value), ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                          encoding="utf-8")


def preflight(path):
    target = Path(path).resolve()
    if target.exists():
        raise FileExistsError("输出已存在，计算前中止，不覆盖: " + str(target))
    return target


def execute(args):
    target = preflight(args.output)  # 必须早于读输入、曲线计算和第一次写文件。
    payload = load_json(args.input)
    if args.command == "prepare":
        curves, audit = prepare_curves(payload)
        files = {"curves.json": curves, "minute_audit.json": audit,
                 "quality_summary.json": curves["quality_summary"]}
        printable = {p: {k: c[k] for k in ("status", "q_min", "q_max", "eta", "n_kept")}
                     for p, c in curves["machines"].items()}
        exit_code = 0 if any(c["status"] == "OK" for c in curves["machines"].values()) else 2
    else:
        curves = load_json(args.curves)
        numeric, diagnostic = recommend(curves, payload["current"])
        files = {"numeric_result.json": numeric, "diagnostics.json": diagnostic}
        printable = numeric
        exit_code = 0 if numeric["RESULT_VALID"] else 2
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".luqiao-stage-", dir=target.parent) as directory:
        stage = Path(directory) / "result"
        stage.mkdir()
        for name, contents in files.items():
            write_json(stage / name, contents)
        if args.command == "recommend":
            (stage / "numeric_result.csv").write_text(
                ",".join(OUTPUTS) + "\n" + ",".join(str(printable[k]) for k in OUTPUTS) + "\n", encoding="utf-8")
        write_json(stage / "input_provenance.json", {
            "input": str(Path(args.input).resolve()),
            "input_sha256": hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
            "curves_sha256": hashlib.sha256(Path(args.curves).read_bytes()).hexdigest()
                if args.command == "recommend" else None,
            "fixture_notice": payload.get("fixture_notice"),
            "local_validation_only": True, "automatic_dispatch": False,
        })
        write_json(stage / "hashes.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted(stage.iterdir())})
        if target.exists():
            raise FileExistsError("输出目录在计算期间被占用，保留旧目录")
        # 不用replace，Windows上目标被抢先创建时rename会拒绝覆盖。
        stage.rename(target)
    print(json.dumps(json_safe(printable), ensure_ascii=False, allow_nan=False))
    print("结果目录: " + str(target), file=sys.stderr)
    return exit_code


def main(argv=None):
    parser = argparse.ArgumentParser(description="路桥二期5#/6#：仓库效率源码→历史曲线→当前风机组合")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare", help="显式历史窗口及F生成本厂逐台曲线")
    prep.add_argument("--input", required=True, help="历史数值样本JSON，不是测点编码请求")
    prep.add_argument("--output", required=True, help="必须尚不存在的新结果目录")
    pred = sub.add_parser("recommend", help="读取冻结曲线与当前两台同刻快照，不重新计算历史")
    pred.add_argument("--curves", required=True)
    pred.add_argument("--input", required=True, help="当前数值快照JSON")
    pred.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        return execute(args)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr)
        return 1

