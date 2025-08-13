# --- dmap_lib/schema.py ---
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union


@dataclass
class GridPoint:
    """Represents a single point in the grid-based coordinate system."""
    x: int
    y: int


@dataclass
class Meta:
    """Represents the metadata for a map file."""
    title: str
    sourceImage: str
    gridSizePx: int


# The 'properties' field across different objects can have varied content.
# Using a flexible dictionary is the most straightforward approach.
Properties = Dict[str, Any]


@dataclass
class Room:
    """Represents a room or a corridor."""
    id: str
    shape: str
    gridVertices: List[GridPoint]
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
    type: str = "door"


@dataclass
class Feature:
    """Represents a distinct feature within a room (e.g., statue, column)."""
    id: str
    featureType: str
    shape: str
    gridVertices: List[GridPoint]
    properties: Optional[Properties] = None
    type: str = "feature"


# A Union type for any object that can appear in the mapObjects list.
MapObject = Union[Room, Door, Feature]


@dataclass
class MapData:
    """The root object representing a complete, structured map."""
    dmapVersion: str
    meta: Meta
    mapObjects: List[MapObject]


def save_json(map_data: MapData, output_path: str) -> None:
    """
    Serializes a MapData object to a JSON file.

    Args:
        map_data: The MapData object to serialize.
        output_path: The path to the output .json file.
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(asdict(map_data), f, indent=2)


def load_json(input_path: str) -> MapData:
    """
    Deserializes a JSON file into a MapData object.

    Args:
        input_path: The path to the input .json file.

    Returns:
        A MapData object representing the content of the JSON file.
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Reconstruct the nested dataclasses
    meta = Meta(**data['meta'])
    map_objects = []
    for obj_data in data['mapObjects']:
        obj_type = obj_data.pop('type', None)
        if obj_type == 'room':
            if obj_data.get('gridVertices'):
                obj_data['gridVertices'] = [GridPoint(**v) for v in obj_data['gridVertices']]
            map_objects.append(Room(type=obj_type, **obj_data))
        elif obj_type == 'door':
            if obj_data.get('gridPos'):
                obj_data['gridPos'] = GridPoint(**obj_data['gridPos'])
            map_objects.append(Door(type=obj_type, **obj_data))
        elif obj_type == 'feature':
            if obj_data.get('gridVertices'):
                obj_data['gridVertices'] = [GridPoint(**v) for v in obj_data['gridVertices']]
            map_objects.append(Feature(type=obj_type, **obj_data))
        else:
            raise TypeError(f"Unknown object type in mapObjects: {obj_type}")

    return MapData(
        dmapVersion=data['dmapVersion'],
        meta=meta,
        mapObjects=map_objects
    )
