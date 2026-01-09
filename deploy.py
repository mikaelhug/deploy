import sys
import shutil
import subprocess
import re
from pathlib import Path
from typing import List, Optional, Union

# Disable output buffering to ensure real-time log output
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

DOCKER_BIN = shutil.which("docker") or "docker"

class Deploy:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir

    def run_cmd(self, cmd: List[str], cwd: Optional[Union[str, Path]] = None, capture: bool = False) -> Optional[str]:
        """Runs a shell command."""
        cwd_path = Path(cwd) if cwd else Path(self.base_dir)
        if capture:
            return subprocess.check_output(cmd, cwd=cwd_path, text=True).strip()
        else:
            subprocess.run(cmd, cwd=cwd_path, check=True)
            return None

    def find_app_dirs(self) -> List[Path]:
        """Finds all directories containing a compose.yaml file."""
        base = Path(self.base_dir)
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
            self.run_cmd([DOCKER_BIN, "system", "prune", "-af"])
        except subprocess.CalledProcessError as e:
            print(f"WARNING: docker system prune failed: {e}", file=sys.stderr)

    def manipulate_app(self, app_dir: Path, rebuild: bool) -> None:
        """Restarts or rebuilds the valid app in the given directory."""
        if rebuild:
            print(f"   [Build-relevant changes] Rebuilding and deploying {app_dir}...")
            self.run_cmd([DOCKER_BIN, "compose", "up", "-d", "--build", "--remove-orphans"], cwd=app_dir)
        else:
            print(f"   [Runtime-only changes] Checking {app_dir}...")
            try:
                # Check if containers are running
                project_containers = self.run_cmd([DOCKER_BIN, "compose", "ps", "-q"], cwd=app_dir, capture=True)
            except subprocess.CalledProcessError:
                project_containers = ""

            if project_containers:
                print("   Restarting...")
                self.run_cmd([DOCKER_BIN, "compose", "restart"], cwd=app_dir)
            else:
                print("   Creating (up)...")
                self.run_cmd([DOCKER_BIN, "compose", "up", "-d", "--remove-orphans"], cwd=app_dir)

    def updating_repo(self) -> None:
        """Updates the git repository."""
        print(">> Updating repository...")
        self.prev_commit = self.run_cmd(["git", "rev-parse", "HEAD"], capture=True)
        self.run_cmd(["git", "fetch", "origin", "main"])
        self.run_cmd(["git", "reset", "--hard", "origin/main"])
        self.current_commit = self.run_cmd(["git", "rev-parse", "HEAD"], capture=True)

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
            try:
                self.manipulate_app(app_dir, rebuild)
            except subprocess.CalledProcessError as e:
                print(f"ERROR: Docker operation failed for {app_dir}: {e}", file=sys.stderr)

        self.global_cleanup()
        print("--- Deployment Complete ---")


if __name__ == "__main__":
    app = Deploy(base_dir=sys.argv[1])
    app.run()
