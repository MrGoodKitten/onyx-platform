import pymxs
import traceback
from pathlib import Path
import os

def get_version_and_renderer_info():

    # Running Max version
    max_version = "2019 or lower"
    try:
        max_version = pymxs.runtime.maxversion()[7]
    except:
        pass

    # Get the current renderer
    renderer_string = str(pymxs.runtime.execute("renderers.current")).lower()
    print("Renderer =", renderer_string)
    if("corona" in renderer_string):
        renderer_id = "corona"
    elif("redshift" in renderer_string):
        renderer_id = "redshift"
    elif("v_ray" in renderer_string):
        renderer_id = "vray"
    elif("octane" in renderer_string):
        renderer_id = "octane"
    elif("fstorm" in renderer_string):
        renderer_id = "fstorm"
    elif("arnold" in renderer_string):
        renderer_id = "arnold"
    else:
        # TODO: we might want to have a stronger warning here
        return max_version, renderer_string, ""

    # If we found a renderer, find its version
    renderer_version = 'unimplemented'

    return max_version, renderer_id, renderer_version

def generate_unique_name(n, assets):
    existing_names = {material.name for material in assets}
    if n not in existing_names:
        return n
    ind = 1
    while f"{n}_{ind}" in existing_names:
        ind += 1
    return f"{n}_{ind}"

def find_first_usd_file_in_directory(directory):
    usd_files = [Path(directory) / l for l in os.listdir(directory) if l.endswith(".usd") or l.endswith(".usda") or l.endswith(".usdc")]
    if len(usd_files) == 0 :
        return None
    if len(usd_files) > 1:
        print(f"Multiple OpenUSD files are available in {str(directory)}, the first one will be used")
    return sorted(usd_files)[0]

###########################
# Various parsing helpers
###########################

def GetTexturePath(textures, textureType):
    if texture := textures.get(textureType, None):
        return str(texture).replace("\\", "/")
    return ""

def GetMeshType(meshList):
    if len(meshList) > 0:
        if meshList[0]["format"] == "abc":
            return True
    return False

def GetScanWidth(meta):
    width = 1
    try:
        scanArea = [item for item in meta if item["key"].lower() == "scanarea"]
        if len(scanArea) >= 1:
            scanValue = str(scanArea[0]["value"])
            scanValue = scanValue.split(" ")[0]
            width = int(scanValue.split("x")[0])
    except:
        pass
    return width

def GetScanHeight(meta):
    height = 1
    try:
        scanArea = [item for item in meta if item["key"].lower() == "scanarea"]
        if len(scanArea) >= 1:
            scanValue = str(scanArea[0]["value"])
            scanValue = scanValue.split(" ")[0]
            height = int(scanValue.split("x")[1])
    except:
        pass
    return height

###########################
# Multi-material functions
###########################

class MaterialData():
    def __init__(self, matType, matIDs):
        self.matType = matType
        self.matIDs = matIDs

def get_multi_material_info(meta):
    has_multi_material = False
    materials_data = []
    num_materials = 0

    try:
        for item in meta:
            if item["key"].lower() == "materialids":
                has_multi_material = True
                for vals in item["value"]:
                    materials_data.append(MaterialData(vals["material"], vals["ids"]))
                    num_materials += len(vals["ids"])
    except:
        pass

    return has_multi_material, materials_data, num_materials