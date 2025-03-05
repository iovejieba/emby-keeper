import os
import re
import subprocess
from pathlib import Path


def update_version(app_path, version):
    """Update version in app.py"""
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(r'EK_VERSION = "[^"]+"', f'EK_VERSION = "{version}"', content)

    with open(app_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def obfuscate_with_pyarmor(app_path):
    """Obfuscate app.py using pyarmor"""
    subprocess.run(
        ["pyarmor", "obfuscate", "--recursive", "--output", os.path.dirname(app_path), app_path], check=True
    )


def main():
    # Get version from environment variable (set by GitHub Actions)
    version = os.environ.get("GITHUB_REF_NAME", "").lstrip("v")
    if not version:
        raise ValueError("Version not found in GITHUB_REF_NAME")

    # Paths
    hf_dir = Path("hf")
    app_path = hf_dir / "app.py"

    # Update version in app.py
    update_version(app_path, version)

    # Obfuscate app.py
    obfuscate_with_pyarmor(app_path)

    print(f"Successfully processed app.py with version {version}")


if __name__ == "__main__":
    main()
