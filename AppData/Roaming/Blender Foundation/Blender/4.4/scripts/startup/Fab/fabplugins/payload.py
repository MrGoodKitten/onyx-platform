# coding=utf-8

import inspect
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Any, Optional

def from_dict(class_type, dict):
    # This allows to ignore additional parameters, while not crashing on optional ones
    class_parameters = inspect.signature(class_type).parameters
    kwargs = {k: v for k, v in dict.items() if k in class_parameters}
    for k in class_parameters:
        if k not in dict:
            kwargs[k] = None
    return class_type(**kwargs)

@dataclass
class LOD:
    file: Path
    material_index: int = -1
    @classmethod
    def from_dict(cls, d): return from_dict(cls, d)

@dataclass
class Model:
    file: Path
    name: str = ""
    material_index: int = -1
    lods: list[LOD] = field(default_factory=list)
    @classmethod
    def from_dict(cls, d): return from_dict(cls, d)

@dataclass
class Material:
    name: str = ""
    textures: dict[str, Path] = field(default_factory=dict)
    file: Path = None
    flipnmapgreenchannel : bool = False
    @classmethod 
    def from_dict(cls, d): return from_dict(cls, d)

class Metadata:

    # From "metadata.launcher"
    launcher_version: str = ""
    launcher_port: int = 24563

    # From "metadata.fab"
    type: str = ""
    title: str = ""
    category: str = ""
    tags: str = []
    format: str = ""
    is_quixel: str = False
    quality: str = ""

    # Quixel info
    quixel_json: dict = {}
    quixel_filtered: dict = {}

    def __init__(self, M):

        L = M.get("launcher", {})
        self.launcher_version = L.get("version", "")
        self.launcher_port = int(L.get("listening_port", 24563))

        F = M.get("fab", {})
        self.type = F.get("listing", {}).get("listingType", "3d-model")
        self.title = F.get("listing", {}).get("title", "")
        self.category = F.get("listing", {}).get("category", {}).get("slug", "")
        self.tags = [t for tag in F.get("listing", {}).get("tags", []) if (t:=tag.get("slug", None))]
        self.format = F.get("format", "")
        self.is_quixel = bool(F.get("isQuixel", False))
        self.quality = F.get("quality", "")

        Q = M.get("megascans", {})
        
        self.quixel_json = Q
        categories = [c.lower() for c in Q.get("categories", [])]
        main_category = categories[0] if len(categories) else "3d"
        tags = [t.lower() for t in Q.get("tags", [])]
        
        # TODO, we'd have to handle this better, I'll have suggestions :) 
        displacement_bias = 0.5
        displacement_scale = 0
        try:
            bias_keys = [k for k in Q if "displacement_bias" in k]
            scale_keys = [k for k in Q if "displacement_scale" in k]
            displacement_bias = float(Q.get(bias_keys[0], displacement_bias)) if len(bias_keys) == 1 else displacement_bias
            displacement_scale = float(Q.get(scale_keys[0], displacement_scale)) if len(scale_keys) == 1 else displacement_scale
        except:
            print("Error encountered while parsing displacement, setting default values")

        self.quixel_filtered = {
            "is_custom": bool(Q.get("isCustom", False)),
            "prefer_specular_workflow" : Q.get("workflow", None) == "specular",
            "is_high_poly" : Q.get("activeLOD", None) == "high",
            "is_metal" : (Q.get("category", None) == "Metal") or ("metal" in tags + categories),
            "is_scatter" : any([key in categories + tags for key in ["scatter", "cmb_asset"]]),
            "is_fruit" : any([key in categories + tags for key in ["fruit", "fruits"]]),
            "is_fabric" : "fabric" in tags + categories,
            "is_snow" : "snow" in tags + categories,
            "is_colorless" : "colorless" in tags,
            "is_sss": any([key in categories for key in ["moss", "skin", "snow"]]),
            "type": main_category,
            "is_plant" : self.category.startswith("nature-plants--plants") or main_category == "3dplant",
            "displacement_bias": displacement_bias,
            "displacement_scale": displacement_scale,
            "name": Q.get("name", "").replace(" ", "_")
        }
        self.type = "material" if self.quixel_filtered.get("type") == "surface" else self.type

        can_have_displacement = True
        if (self.type == "3d-model") and self.quixel_filtered.get("is_high_poly"):
            can_have_displacement = False
        elif self.quixel_filtered.get("is_plant"):
            can_have_displacement = False
        self.quixel_filtered["displacement"] = can_have_displacement

@dataclass
class Payload:
    """A structured data class meant to match received TCP payloads."""
    id: str
    path: str
    models : Optional[List[Model]]
    materials: Optional[List[Material]]
    native_files: Optional[List[Path]]
    additional_textures: Optional[List[Path]]
    metadata: Metadata
    root_name: str

    def __init__(self, d:dict, print_debug=False):

        if print_debug:
            print("\nDebug payload:")
            payload_for_print = dict(d)
            if "metadata" in payload_for_print:
                if "megascans" in payload_for_print["metadata"]:
                    payload_for_print["metadata"]["megascans"] = {"simplified": "fordisplay"}
            print(json.dumps(payload_for_print, sort_keys=True, indent=2, separators=(',', ': ')))
            print()
        
        # Parsing main payload data
        self.id = d.get("id", "")
        self.path = d.get("path", "")
        self.models = [Model.from_dict(x) for x in d.get("meshes", [])]
        self.materials = [Material.from_dict(x) for x in d.get("materials", [])]
        self.native_files = d.get("native_files", [])
        self.additional_textures = d.get("additional_textures", [])

        # Register metadata
        self.metadata = Metadata(d.get("metadata", {}))

        # Get a root name
        if self.metadata.is_quixel and (n := self.metadata.quixel_json.get("name", "")): 
            self.root_name = n.replace(" ", "_")
        elif self.metadata.title:
            self.root_name = self.metadata.title.replace(" ", "_")
        else:
            self.root_name = self.id

        # Fill in default names if we can / need
        for m in self.materials:
            m.name = m.name if m.name else "material"
        for m in self.models:
            m.name = m.name if m.name else "model"
