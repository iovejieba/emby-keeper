import os
import re
import subprocess
import shutil
from pathlib import Path


def update_version(app_path, version):
    """Update version in app.py"""
    with open(app_path, "r", encoding="utf-8") as f:
        content = f.read()

    new_content = re.sub(r'EK_VERSION = "[^"]+"', f'EK_VERSION = "{version}"', content)

    with open(app_path, "w", encoding="utf-8") as f:
        f.write(new_content)


def obfuscate_with_pyarmor(app_path):
    """Obfuscate app.py using pyarmor and replace the original file with obfuscated version"""
    app_dir = os.path.dirname(app_path)
    
    # Run pyarmor
    subprocess.run(["pyarmor", "gen", "--recursive", app_dir], check=True)
    
    # Get the dist directory where pyarmor outputs files
    dist_dir = os.path.join(os.getcwd(), "dist")
    
    if os.path.exists(dist_dir):
        # Copy the obfuscated files back to original location
        for root, _, files in os.walk(dist_dir):
            relative_path = os.path.relpath(root, dist_dir)
            target_dir = os.path.join(app_dir, relative_path)
            os.makedirs(target_dir, exist_ok=True)
            
            for file in files:
                src_file = os.path.join(root, file)
                dst_file = os.path.join(target_dir, file)
                shutil.copy2(src_file, dst_file)
        
        # Clean up dist directory
        shutil.rmtree(dist_dir)
        return True
    return False


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
    if not obfuscate_with_pyarmor(app_path):
        raise RuntimeError("Failed to obfuscate app.py")

    print(f"Successfully processed app.py with version {version}")


if __name__ == "__main__":
    main()
