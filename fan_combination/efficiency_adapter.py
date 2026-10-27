"""加载仓库唯一效率源码；只导出其函数和常量，不维护另一份公式。"""
import importlib.util
import sys
from .contract import EFFICIENCY_SOURCE, check_sources

check_sources()
_name = "fan_combination._canonical_efficiency"
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, EFFICIENCY_SOURCE)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
else:
    _module = sys.modules[_name]
for _key, _value in vars(_module).items():
    if not _key.startswith("__"):
        globals()[_key] = _value

