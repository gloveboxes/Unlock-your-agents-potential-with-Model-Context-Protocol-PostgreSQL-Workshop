from pathlib import Path


class Utilities:
    # property to get the relative path of shared files
    @property
    def shared_files_path(self) -> Path:
        """Get the path to the shared files directory."""
        return Path(__file__).parent.resolve() / "shared"
