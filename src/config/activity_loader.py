"""
Activity configuration loader for course/activity structure.

Handles loading course YAML files with the unidades/actividades structure
used by the Colombian doctoral program grading system.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ActivityConfig:
    """Configuration for a single activity from course YAML."""

    id: str
    titulo: str
    tipo: str  # 'escrito' or 'foro'
    extraer_texto: bool
    rubrica: Path
    prompt: Path
    instrucciones: str


class ActivityConfigLoader:
    """Loads course configurations with the unidades/actividades structure."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or (Path(__file__).parent / "courses")

    def load_course(self, course_id: str) -> dict:
        """
        Load course YAML by ID (e.g., 'FI08').

        Args:
            course_id: Course identifier matching the YAML filename

        Returns:
            Dictionary with full course configuration

        Raises:
            FileNotFoundError: If course config file doesn't exist
        """
        path = self.config_dir / f"{course_id}.yml"
        if not path.exists():
            raise FileNotFoundError(f"Course config not found: {path}")
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def find_activity(
        self,
        config: dict,
        unit: int,
        activity_id: str,
    ) -> Optional[ActivityConfig]:
        """
        Find activity by unit number and activity ID.

        Args:
            config: Course configuration dictionary
            unit: Unit number (1, 2, 3, etc.)
            activity_id: Activity ID within the unit (e.g., '1.1', '1.2')

        Returns:
            ActivityConfig if found, None otherwise
        """
        for unidad in config.get("unidades", []):
            if unidad.get("unidad") == unit:
                for act in unidad.get("actividades", []):
                    if act.get("id") == activity_id:
                        return ActivityConfig(
                            id=act["id"],
                            titulo=act.get("titulo", ""),
                            tipo=act.get("tipo", "escrito"),
                            extraer_texto=act.get("extraer_texto", False),
                            rubrica=Path(act.get("rubrica", "")),
                            prompt=Path(act.get("prompt", "")),
                            instrucciones=act.get("instrucciones", ""),
                        )
        return None
