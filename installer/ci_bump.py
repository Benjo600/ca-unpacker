import os
import pathlib
import re
import sys


def main() -> int:
    run_number = os.environ.get("GITHUB_RUN_NUMBER")
    if not run_number:
        print("GITHUB_RUN_NUMBER is not set; refusing a non-CI version bump.", file=sys.stderr)
        return 1

    version_file = pathlib.Path("apps/version.py")
    code = version_file.read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)"', code)
    if not match:
        print("apps/version.py has no strict x.y.z APP_VERSION", file=sys.stderr)
        return 1

    version = f"{match.group(1)}.{match.group(2)}.{run_number}"
    code = re.sub(
        r'APP_VERSION\s*=\s*"\d+\.\d+\.\d+"',
        f'APP_VERSION = "{version}"',
        code,
    )
    version_file.write_text(code, encoding="utf-8")

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as fh:
            fh.write(f"version={version}\n")

    print("CI version:", version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
