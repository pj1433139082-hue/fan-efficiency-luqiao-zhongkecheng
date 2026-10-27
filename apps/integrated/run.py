"""从任意工作目录运行；只把仓库及本应用加入模块搜索路径。"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from luqiao_fan.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
