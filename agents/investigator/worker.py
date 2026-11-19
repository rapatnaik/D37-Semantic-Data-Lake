"""Entry point that runs one generated analysis inside the isolated worker.

Standalone on purpose (standard library only, no package imports): it is
mounted read-only into the container at /opt/d37/worker.py.

Usage: ``python -I worker.py <workdir>`` where <workdir> contains

    sandbox.json   {"inputs": {source_id: {"path", "relative_path"}}, "parameters", "seed"}
    code.py        generated analysis source (read-only)
    inputs/        selected input files (read-only)
    outputs/       the only place results may be written
    meta/          worker_status.json written here

Generated code runs with these globals and with ``outputs/`` as the cwd:

    INPUTS       {source_id: pathlib.Path}      read-only input files
    INPUT_FILES  {relative_path: pathlib.Path}  same files keyed by dataset path
    PARAMETERS   dict from the AnalysisRequest
    OUTPUT_DIR   pathlib.Path of outputs/
    SEED         int; random (and numpy, if installed) are pre-seeded
    save_json(name, obj)  write strict JSON to OUTPUT_DIR/name
"""

from __future__ import annotations

import json
import os
import platform
import random
import sys
import time
import traceback
from pathlib import Path

_PACKAGES = ("numpy", "pandas", "pyarrow", "matplotlib", "pillow", "tifffile", "openpyxl")


def _versions() -> dict:
    try:
        from importlib import metadata
    except ImportError:  # pragma: no cover
        return {}
    found = {}
    for name in _PACKAGES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            pass
    return found


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: worker.py <workdir>", file=sys.stderr)
        return 2
    work = Path(argv[1]).resolve()
    output_dir = work / "outputs"
    meta_dir = work / "meta"
    status: dict = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": _versions(),
        "status": "error",
    }
    started = time.monotonic()
    try:
        request = json.loads((work / "sandbox.json").read_text(encoding="utf-8"))
        inputs, files = {}, {}
        for source_id, entry in request["inputs"].items():
            path = (work / entry["path"]).resolve()
            if not _inside(path, work / "inputs"):
                raise PermissionError(f"Input outside inputs/: {entry['relative_path']}")
            inputs[source_id] = path
            files[entry["relative_path"]] = path
        seed = int(request.get("seed", 0))
        random.seed(seed)
        try:
            import numpy  # noqa: PLC0415

            numpy.random.seed(seed % (2**32))
        except ImportError:
            pass

        def save_json(name: str, obj) -> Path:
            target = (output_dir / name).resolve()
            if not _inside(target, output_dir):
                raise PermissionError(f"Output escapes OUTPUT_DIR: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(obj, indent=2, allow_nan=False, default=str), encoding="utf-8")
            return target

        namespace = {
            "__name__": "__main__",
            "__file__": str(work / "code.py"),
            "INPUTS": inputs,
            "INPUT_FILES": files,
            "PARAMETERS": request.get("parameters", {}),
            "OUTPUT_DIR": output_dir,
            "SEED": seed,
            "save_json": save_json,
        }
        source = (work / "code.py").read_text(encoding="utf-8")
        compiled = compile(source, "analysis.py", "exec")
        os.chdir(output_dir)
        try:
            exec(compiled, namespace)  # noqa: S102 - this is the sandboxed worker
        except SystemExit as exit_request:
            if exit_request.code not in (None, 0):
                raise
        status["status"] = "ok"
        code = 0
    except BaseException as error:  # report everything, including KeyboardInterrupt
        status["error_type"] = type(error).__name__
        status["error"] = str(error)[:2000]
        status["traceback"] = traceback.format_exc()[-8000:]
        traceback.print_exc()
        code = 1
    status["duration_seconds"] = round(time.monotonic() - started, 3)
    try:
        meta_dir.mkdir(exist_ok=True)
        (meta_dir / "worker_status.json").write_text(json.dumps(status, indent=2, default=str), encoding="utf-8")
    except OSError:
        traceback.print_exc()
        code = code or 1
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
