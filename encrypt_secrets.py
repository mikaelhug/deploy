#!/usr/bin/env python3
import os
import sys
import platform
import glob
import hashlib
import json
import subprocess


# check if sops is downloaded else download it
def download_sops(sops_version):
    system = platform.system().lower()
    arch = os.uname().machine
    base_url = "https://github.com/getsops/sops/releases/download"
    sops_filename = f"sops-{sops_version}.{system}.{arch}"
    sops_url = f"{base_url}/{sops_version}/{sops_filename}"

    if not os.path.isfile(sops_filename):
        old_sops_files = glob.glob(f"sops-*.{system}.{arch}")
        for old_file in old_sops_files:
            os.remove(old_file)
            print(f"Removed old version: {old_file}")

        result = os.system(f"curl -LO {sops_url}")
        if result != 0:
            print(f"Error: Failed to download {sops_filename}")
            exit(1)

        os.chmod(sops_filename, 0o755)
        print(f"Downloaded {sops_filename} successfully")

    return sops_filename


sops_filename = download_sops("v3.11.0")

# Check for command-line argument
if len(sys.argv) != 2:
    print("Usage: python3 encrypt_secrets.py <directory_name>")
    print("Example: python3 encrypt_secrets.py authentik")
    sys.exit(1)

target_dir = sys.argv[1]

# Checksum file to track changes
checksum_file = ".env_checksums.json"


def get_file_checksum(filepath):
    """Calculate SHA256 checksum of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def load_checksums():
    """Load saved checksums from file"""
    if os.path.exists(checksum_file):
        with open(checksum_file, "r") as f:
            return json.load(f)
    return {}


def save_checksums(checksums):
    """Save checksums to file"""
    with open(checksum_file, "w") as f:
        json.dump(checksums, f, indent=2)


# Load existing checksums
checksums = load_checksums()

# Process only the specified directory
item_path = os.path.join("..", target_dir)

# Check if directory exists
if not os.path.isdir(item_path):
    print(f"Error: Directory '{target_dir}' not found in parent directory")
    sys.exit(1)

env_path = os.path.join(item_path, ".env")

if os.path.isfile(env_path):
    encrypted_env_path = env_path + ".enc"
    current_checksum = get_file_checksum(env_path)

    # Check if file has changed or if .env.enc doesn't exist
    if (
        env_path not in checksums
        or checksums[env_path] != current_checksum
        or not os.path.exists(encrypted_env_path)
    ):
        # Use sops - it will find .sops.yaml automatically in parent directories
        result = subprocess.run(
            [
                f"./{sops_filename}",
                "--input-type",
                "dotenv",
                "--output-type",
                "dotenv",
                "--output",
                encrypted_env_path,
                "--encrypt",
                env_path,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Error: Failed to encrypt {env_path}")
            print(f"Error details: {result.stderr}")
            sys.exit(1)
        else:
            print(f"Encrypted {encrypted_env_path} successfully")
            # Update checksum only for this file
            checksums[env_path] = current_checksum
            save_checksums(checksums)
    else:
        print(f"Skipped {env_path} - no changes detected")
else:
    print(f"Error: No .env file found in {item_path}")
    sys.exit(1)
