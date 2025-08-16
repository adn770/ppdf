# --- dmap_lib/analysis/context.py ---
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional


# The internal, pre-transformation data model for a single grid cell.
@dataclass
class _TileData:
    feature_type: str  # e.g., 'floor', 'empty'
    north_wall: Optional[str] = None
    east_wall: Optional[str] = None
    south_wall: Optional[str] = None
    west_wall: Optional[str] = None


@dataclass
class _GridInfo:
    """Internal data object for grid parameters."""

    size: int
    offset_x: int
    offset_y: int


@dataclass
class _RegionAnalysisContext:
    """Internal data carrier for a single region's analysis pipeline."""

    tile_grid: Dict[Tuple[int, int], _TileData] = field(default_factory=dict)
    enhancement_layers: Dict[str, Any] = field(default_factory=dict)
    room_bounds: List[Tuple[int, int, int, int]] = field(default_factory=list)
