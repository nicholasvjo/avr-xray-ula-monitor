from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def main() -> None:
    project_dir = Path(__file__).resolve().parent
    python_dir = project_dir / "python"
    sys.path.insert(0, str(python_dir))

    module_path = python_dir / "main.py"
    spec = importlib.util.spec_from_file_location("avr_xray_entrypoint", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Nao foi possivel carregar {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()


if __name__ == "__main__":
    main()
