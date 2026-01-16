import sys
import subprocess
import platform
import glob
import re
import os
from pathlib import Path
from typing import List, Optional, Union

# Disable output buffering to ensure real-time log output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


class Deploy:
    def __init__(self, fleet_dir: str, docker_bin: str) -> None:
        self.fleet_dir = fleet_dir
        self.docker_bin = docker_bin
        self.deploy_dir = os.path.dirname(os.path.abspath(__file__))
        self.sops_path = self.download_sops("v3.11.0")

    def run_cmd(self, cmd: List[str], cwd: Optional[Union[str, Path]] = None, capture: bool = False) -> Optional[str]:
        """Runs a shell command."""
        cwd_path = Path(cwd) if cwd else Path(self.fleet_dir)
        if capture:
            return subprocess.check_output(cmd, cwd=cwd_path, text=True).strip()
        else:
            subprocess.run(cmd, cwd=cwd_path, check=True)
            return None

    def download_sops(self, sops_version):
        system = platform.system().lower()
        arch = os.uname().machine
        if arch == "x86_64":
            arch = "amd64"

        base_url = "https://github.com/getsops/sops/releases/download"
        sops_filename = f"sops-{sops_version}.{system}.{arch}"
        sops_path = os.path.join(self.deploy_dir, sops_filename)
        sops_url = f"{base_url}/{sops_version}/{sops_filename}"

        if not os.path.isfile(sops_path):
            old_sops_files = glob.glob(f"sops-*.{system}.{arch}")
            for old_file in old_sops_files:
                os.remove(old_file)
                print(f"Removed old version: {old_file}")

            result = self.run_cmd(["curl", "-LO", sops_url], cwd=self.deploy_dir)
            if result != 0:
                print(f"Error: Failed to download {sops_filename}")
                exit(1)

            os.chmod(sops_path, 0o755)
            print(f"Downloaded {sops_filename} successfully")

        return sops_path

    def find_app_dirs(self) -> List[Path]:
        """Finds all directories containing a compose.yaml file."""
        base = Path(self.fleet_dir)
        return [d for d in base.iterdir() if d.is_dir() and (d / "compose.yaml").exists()]

    def git_changed_files_for_dir(self, app_dir: Path) -> List[str]:
        """Returns a list of changed files for a specific app directory between commits."""
        try:
            out = self.run_cmd(
                ["git", "diff", "--name-only", self.prev_commit, self.current_commit, "--", str(app_dir)], capture=True
            )
            if out:
                return [line for line in out.splitlines() if line.strip()]
            return []
        except subprocess.CalledProcessError:
            return []

    def needs_build(self, changed_files: List[str]) -> bool:
        """Determines if a rebuild is needed based on changed files."""
        pattern = re.compile(r"(^|/)(Dockerfile|requirements(\.txt)?$|compose\.ya?ml$|compose\.yml$)", re.IGNORECASE)

        for f in changed_files:
            if pattern.search(f):
                return True
        return False

    def global_cleanup(self) -> None:
        """Prunes unused docker images."""
        try:
            print(">> Pruning system...")
            self.run_cmd([self.docker_bin, "system", "prune", "-af"])
        except subprocess.CalledProcessError as e:
            print(f"WARNING: docker system prune failed: {e}", file=sys.stderr)

    def manipulate_app(self, app_dir: Path, rebuild: bool) -> None:
        """Restarts or rebuilds the valid app in the given directory."""
        if rebuild:
            print(f"   [Build-relevant changes] Rebuilding and deploying {app_dir}...")
            self.run_cmd([self.docker_bin, "compose", "up", "-d", "--build", "--remove-orphans"], cwd=app_dir)
        else:
            print(f"   [Runtime-only changes] Checking {app_dir}...")
            try:
                # Check if containers are running
                project_containers = self.run_cmd([self.docker_bin, "compose", "ps", "-q"], cwd=app_dir, capture=True)
            except subprocess.CalledProcessError:
                project_containers = ""

            if project_containers:
                print("   Restarting...")
                self.run_cmd([self.docker_bin, "compose", "restart"], cwd=app_dir)
            else:
                print("   Creating (up)...")
                self.run_cmd([self.docker_bin, "compose", "up", "-d", "--remove-orphans"], cwd=app_dir)

    def updating_repo(self) -> None:
        """Updates the git repository."""
        print(">> Updating repository...")
        self.prev_commit = self.run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        self.run_cmd(["git", "fetch", "origin", "main"])
        self.run_cmd(["git", "reset", "--hard", "origin/main"])
        self.current_commit = self.run_cmd(["git", "rev-parse", "HEAD"], capture=True)

        # update submodules if .gitmodules exists
        if (Path(self.fleet_dir) / ".gitmodules").exists():
            print(">> Updating submodules...")
            self.run_cmd(["git", "submodule", "update", "--init"])

    def decrypt_secrets(self, app_dir: Path, changed_files: List[str]) -> None:
        """Decrypts .env.enc using ssh private key if it's added or changed."""
        env_enc_path = os.path.join(app_dir, ".env.enc")
        env_path = os.path.join(app_dir, ".env")
        if not os.path.isfile(env_enc_path):
            if os.path.exists(env_path):
                os.remove(env_path)
            return

        for f in changed_files:
            if f.endswith(".env.enc"):
                print(f"   [Secrets change] Decrypting {env_enc_path} to {env_path}...")
                # use sops to decrypt self.sops_filename
                self.run_cmd(
                    [
                        f"./{self.sops_filename}",
                        "--input-type",
                        "dotenv",
                        "--output-type",
                        "dotenv",
                        "--output",
                        str(env_path),
                        "--decrypt",
                        str(env_enc_path),
                    ],
                    cwd=deploy_dir,
                )
                break

    def run(self) -> None:
        print("--- Starting Deployment ---")
        self.updating_repo()
        self.app_dirs = self.find_app_dirs()

        if not self.app_dirs:
            print(">> No compose files found. Nothing to do.")

        for app_dir in self.app_dirs:
            print(f">> Processing app: {app_dir}")

            changed = self.git_changed_files_for_dir(app_dir)
            if not changed:
                print(f"   [No changes] Skipping {app_dir}")
                continue

            rebuild = self.needs_build(changed)
            # decrypt secrets if needed (if added/changed .env.enc SOPS file)
            self.decrypt_secrets(app_dir, changed)
            try:
                self.manipulate_app(app_dir, rebuild)
            except subprocess.CalledProcessError as e:
                print(f"ERROR: Docker operation failed for {app_dir}: {e}", file=sys.stderr)

        self.global_cleanup()
        print("--- Deployment Complete ---")


if __name__ == "__main__":
    app = Deploy(fleet_dir=sys.argv[1], docker_bin=sys.argv[2])
    app.run()
