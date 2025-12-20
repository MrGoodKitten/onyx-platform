import os
import c4d
import traceback

def show_error_message(msg : str):
    c4d.gui.MessageDialog(f"FAB Error: {msg}")

def handle_exception(e : Exception, msg):
    error_msg = f"Message: {msg}\nTraceback: {traceback.format_exc()}"

    # Show a modal dialog in C4D
    show_error_message(error_msg)

    # Print to the console
    print(f"FAB Error:\n{error_msg}")

    # TODO: previously, we sent data back to Bridge
    # if(c4d.GeGetCurrentOS() == 1):
    #     LogUtil.UpdateStatus(error_msg, True, True)

#########################
# C4D API helpers
#########################

def get_renderer_id():
    doc = c4d.documents.GetActiveDocument()
    renderer_int = doc.GetActiveRenderData()[c4d.RDATA_RENDERENGINE]
    if renderer_int == 1023342: renderer_int = 0 # Physical
    renderer_id = {
        0: "Physical/Standard",
        1019782: "V-Ray",
        1029525: "Octane",
        1029988: "Arnold",
        1030480: "Corona",
        1036219: "Redshift",
        1037639: "ProRender",
    }.get(renderer_int, None)
    return renderer_id

def get_all_objects(in_selection=False):
    def get_all_children(object):
        object_list = []
        for o in object.GetChildren():
            object_list.append(o)
            object_list.extend(get_all_children(o))
        return object_list
    # TODO: this repeats itself, but a list of set allows to workaround
    doc = c4d.documents.GetActiveDocument()
    objects = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN) if in_selection else doc.GetObjects()
    for obj in objects:
        objects.extend(get_all_children(obj))
    return list(set(objects))

def GetLogData(renderer_engine):

    doc = c4d.documents.GetActiveDocument()

    # TODO: need to add plugin_version, this should be centralized
    # Longer term, id, status, message... could be reinstated to send
    info = {
        "renderer": renderer_engine,
        "renderer_version": "unknown",
        "app_version": c4d.GetC4DVersion(),
    }

    # Gather the current renderer version, if available
    try:
        match renderer_engine:
            case "Physical/Standard":
                pass # No renderer version
            case "Redshift":
                import redshift
                info["renderer_version"] = redshift.GetCoreVersion()
            case "Arnold":
                ARNOLD_SCENE_HOOK = 1032309
                C4DTOA_MSG_TYPE = 1000
                C4DTOA_MSG_GET_VERSION = 1040
                C4DTOA_MSG_RESP2 = 2012
                arnoldSceneHook = doc.FindSceneHook(ARNOLD_SCENE_HOOK)
                if arnoldSceneHook is not None:
                    msg = c4d.BaseContainer()
                    msg.SetInt32(C4DTOA_MSG_TYPE, C4DTOA_MSG_GET_VERSION)
                    arnoldSceneHook.Message(c4d.MSG_BASECONTAINER, msg)
                    info["renderer_version"] = msg.GetString(C4DTOA_MSG_RESP2)
            case "Octane":
                OCTANE_LIVELINK_PLUGIN = 1029499
                ID_OPEN_OCTANE_DIALOG = 1031193
                bc = doc[OCTANE_LIVELINK_PLUGIN]
                octane_dialog_opened = False
                try:
                    info["renderer_version"] = bc[c4d.SET_OCTANE_VERSION]
                    octane_dialog_opened = True
                except Exception as e:
                    if not octane_dialog_opened:
                        octane_dialog_opened = True
                        c4d.CallCommand(ID_OPEN_OCTANE_DIALOG)
                    info["renderer_version"] = bc[c4d.SET_OCTANE_VERSION]
    except Exception as e:
        print(f"Did not manage to gather renderer ({renderer_engine}) version")

    return info

#########################
# GLTF CONVERSION
#########################

import json
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse, unquote

def abspath_from(uri: str, base_dir: str):
    stripped = uri.strip()
    if stripped.startswith("data:"):
        return uri
    if urlparse(stripped).scheme in ("http", "https"):
        return uri
    if os.path.isabs(stripped) or stripped.startswith("\\\\"):
        return uri
    rel = unquote(stripped)
    return os.path.normpath(os.path.join(base_dir, rel))

def make_gltf_with_absolute_paths(gltf_path: str | os.PathLike):
    # Open a gltf file, convert paths to absolute, and save to a temp gltf file
    gltf_path = Path(gltf_path)
    base_dir = str(gltf_path.parent)
    with gltf_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    for buf in data.get("buffers", []):
        uri = buf.get("uri")
        if isinstance(uri, str):
            buf["uri"] = abspath_from(uri, base_dir)
    for img in data.get("images", []):
        uri = img.get("uri")
        if isinstance(uri, str):
            img["uri"] = abspath_from(uri, base_dir)
    fd, tmp_path = tempfile.mkstemp(suffix=".gltf")
    os.close(fd)
    with open(tmp_path, "w", encoding="utf-8") as out:
        json.dump(data, out, indent=2, ensure_ascii=False)
        out.write("\n")
    return tmp_path