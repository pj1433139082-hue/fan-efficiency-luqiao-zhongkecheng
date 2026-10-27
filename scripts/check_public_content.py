"""公开内容自检：不读取外部文件、不联网，也不在错误中回显命中内容。"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
skip = {".git", ".github", "__pycache__", "outputs", "local_runs", "raw_data", "mlruns"}
patterns = [re.compile(r"bewg\.net\.cn", re.I), re.compile(r"PS[0-9]{5}-[0-9]{2}"),
            re.compile(r"_(?:ENCLAVE_)?PAYLOAD\s*="), re.compile(r"_MASK\s*="),
            re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(r"[A-Za-z]:[/\\]Users[/\\]", re.I)]
hits = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in skip or part.startswith(".venv") for part in path.relative_to(ROOT).parts):
        continue
    if path.suffix in {".pyc", ".pkl", ".xlsx", ".csv", ".gz", ".zip"}:
        hits.append(path.relative_to(ROOT).as_posix())
        continue
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeError:
        hits.append(path.relative_to(ROOT).as_posix())
        continue
    if any(pattern.search(content) for pattern in patterns):
        hits.append(path.relative_to(ROOT).as_posix())
if hits:
    raise SystemExit("PUBLIC_CONTENT_CHECK_FAILED (paths only): " + ", ".join(hits))
print("PASS_PUBLIC_CONTENT: no internal endpoints, credential payloads, personal absolute paths or data binaries")

