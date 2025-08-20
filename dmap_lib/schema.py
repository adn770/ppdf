# --- dmap_lib/schema.py ---
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class GridPoint:
    """Represents a single point in the grid-based coordinate system."""

    x: float
    y: float


@dataclass
class BoundingBox:
    """Represents an axis-aligned bounding box."""

    x: float
    y: float
    width: float
    height: float


# The 'properties' field can have varied content. A flexible dictionary is best.
Properties = Dict[str, Any]


@dataclass
class Meta:
    """Represents the metadata for a map file."""

    title: str
    sourceImage: str
    legend: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Room:
    """Represents a room or a corridor."""

    id: str
    shape: str
    gridVertices: List[GridPoint]
    roomType: str  # e.g., "chamber", "corridor"
    label: Optional[str] = None
    properties: Optional[Properties] = None
    contents: Optional[List[str]] = None
    type: str = "room"


@dataclass
class Door:
    """Represents a door connecting two map objects."""

    id: str
    gridPos: GridPoint
    orientation: str
    connects: List[str]
    properties: Optional[Properties] = None
    type: str = "door"


@dataclass
class Feature:
    """Represents a distinct feature within a room (e.g., statue, column)."""

    id: str
    featureType: str
    shape: str
    gridVertices: List[GridPoint]
    bounds: Optional[BoundingBox] = None
    properties: Optional[Properties] = None
    type: str = "feature"


@dataclass
class EnvironmentalLayer:
    """Represents an area with a specific environmental effect."""

    id: str
    layerType: str  # e.g., "water", "rubble", "chasm"
    gridVertices: List[GridPoint]
    bounds: Optional[BoundingBox] = None
    properties: Optional[Properties] = None
    type: str = "layer"


# A Union type for any object that can appear in a region's mapObjects list.
MapObject = Union[Room, Door, Feature, EnvironmentalLayer]


@dataclass
class Region:
    """Represents a distinct, self-contained area of a map (e.g., a floor)."""

    id: str
    label: str  # e.g., "Tower, Floor 1"
    gridSizePx: int
    bounds: List[GridPoint]
    mapObjects: List[MapObject]


@dataclass
class MapData:
    """The root object representing a complete, structured map."""

    dmapVersion: str
    meta: Meta
    regions: List[Region]


def _deserialize_map_objects(objects_data: List[Dict]) -> List[MapObject]:
    """Helper to deserialize a list of generic map object dictionaries."""
    map_objects = []
    for obj_data in objects_data:
        obj_type = obj_data.get("type")
        # Pop type to avoid TypeError during dataclass construction
        if "type" in obj_data:
            obj_data.pop("type")

        if obj_type == "room":
            if obj_data.get("gridVertices"):
                obj_data["gridVertices"] = [GridPoint(**v) for v in obj_data["gridVertices"]]
            map_objects.append(Room(type=obj_type, **obj_data))
        elif obj_type == "door":
            if obj_data.get("gridPos"):
                obj_data["gridPos"] = GridPoint(**obj_data["gridPos"])
            map_objects.append(Door(type=obj_type, **obj_data))
        elif obj_type == "feature":
            if obj_data.get("bounds"):
                obj_data["bounds"] = BoundingBox(**obj_data["bounds"])
            if obj_data.get("gridVertices"):
                obj_data["gridVertices"] = [GridPoint(**v) for v in obj_data["gridVertices"]]
            map_objects.append(Feature(type=obj_type, **obj_data))
        elif obj_type == "layer":
            if obj_data.get("bounds"):
                obj_data["bounds"] = BoundingBox(**obj_data["bounds"])
            if obj_data.get("gridVertices"):
                obj_data["gridVertices"] = [GridPoint(**v) for v in obj_data["gridVertices"]]
            map_objects.append(EnvironmentalLayer(type=obj_type, **obj_data))
        else:
            # Note: In a real application, consider more robust error handling.
            print(f"Warning: Unknown object type '{obj_type}' encountered. Skipping.")
    return map_objects


def save_json(map_data: MapData, output_path: str) -> None:
    """
    Serializes a MapData object to a JSON file.

    Args:
        map_data: The MapData object to serialize.
        output_path: The path to the output .json file.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(asdict(map_data), f, indent=2)


def load_json(input_path: str) -> MapData:
    """
    Deserializes a JSON file into a MapData object.

    Args:
        input_path: The path to the input .json file.

    Returns:
        A MapData object representing the content of the JSON file.
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = Meta(**data["meta"])
    regions = []
    for region_data in data.get("regions", []):
        map_objects = _deserialize_map_objects(region_data.get("mapObjects", []))
        region_data["mapObjects"] = map_objects
        if region_data.get("bounds"):
            region_data["bounds"] = [GridPoint(**v) for v in region_data["bounds"]]
        regions.append(Region(**region_data))

    return MapData(dmapVersion=data["dmapVersion"], meta=meta, regions=regions)
