"""Application service for data source discovery.

Thin wrapper around data_discovery functions for the /data-sources endpoint.
"""

from pathlib import Path

from ..data_discovery import (
    get_dos_dir,
    get_latest_inventory_path,
    get_latest_pipeline_path,
    parse_date_from_filename,
)
from ..domain.exceptions import DataLoadError


class DataSourceService:
    """Provides metadata about discovered data files."""

    def __init__(self, data_dir: str = "data"):
        self._data_dir = data_dir

    def get_data_sources(self) -> dict:
        """Returns metadata about all currently loaded data files.

        Returns dict matching DataSourcesResponse fields.

        Raises:
            DataLoadError: If filesystem access fails.
        """
        try:
            return self._collect_data_sources()
        except DataLoadError:
            raise
        except Exception as exc:
            raise DataLoadError(
                f"Failed to load data source metadata: {exc}"
            ) from exc

    def _collect_data_sources(self) -> dict:
        """Internal: gather data source metadata from the filesystem."""
        # DOS directory files
        dos_dir = get_dos_dir(self._data_dir)
        dos_path = Path(dos_dir)
        dos_files = []
        if dos_path.is_dir():
            for f in sorted(dos_path.iterdir()):
                if f.suffix == ".xlsx":
                    parsed = parse_date_from_filename(f)
                    date_str = (
                        f"{parsed[0]}-{parsed[1]:02d}" if parsed else None
                    )
                    dos_files.append(
                        {
                            "filename": f.name,
                            "parsed_date": date_str,
                            "exists": True,
                        }
                    )

        # Inventory file
        inv_path_str = get_latest_inventory_path(self._data_dir)
        inv_path = Path(inv_path_str)
        inv_parsed = parse_date_from_filename(inv_path)
        inv_date = (
            f"{inv_parsed[0]}-{inv_parsed[1]:02d}" if inv_parsed else None
        )
        inv_file = {
            "filename": inv_path.name,
            "parsed_date": inv_date,
            "exists": inv_path.exists(),
        }

        # Pipeline file
        pipe_path_str = get_latest_pipeline_path(self._data_dir)
        pipe_path = Path(pipe_path_str)
        pipe_parsed = parse_date_from_filename(pipe_path)
        pipe_date = (
            f"{pipe_parsed[0]}-{pipe_parsed[1]:02d}" if pipe_parsed else None
        )
        pipe_file = {
            "filename": pipe_path.name,
            "parsed_date": pipe_date,
            "exists": pipe_path.exists(),
        }

        return {
            "dos_directory": dos_dir,
            "dos_files": dos_files,
            "inventory_file": inv_file,
            "pipeline_file": pipe_file,
        }
