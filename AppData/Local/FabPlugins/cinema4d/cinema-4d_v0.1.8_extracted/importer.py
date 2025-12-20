import json, sys, os
from pathlib import Path
import traceback

import c4d

import helpers
import renderers
import fabplugins

def setup_geometry_tags(renderer_engine, item, useDisplacement, applies_to_imported_geometry): 
    match renderer_engine:
        case "Redshift":
            Rtag = c4d.BaseTag(1036222)
            if useDisplacement:
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_OVERRIDE] = True
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_SUBDIVISIONENABLED] = True
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_DISPLACEMENTENABLED] = True
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_SMOOTHSUBDIVISIONENABLED] = False
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_MAXDISPLACEMENT] = 1 if applies_to_imported_geometry else 10
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_DISPLACEMENTSCALE] = 1 if applies_to_imported_geometry else 10
                Rtag[c4d.REDSHIFT_OBJECT_GEOMETRY_OVERRIDE] = False
            item.InsertTag(Rtag)
        case "Octane":
            Otag = c4d.BaseTag(1029603)
            item.InsertTag(Otag)
            phong = item.GetTag(c4d.Tphong)
            if phong is None:
                phong[c4d.PHONGTAG_PHONG_ANGLELIMIT] = False
        case "Arnold":
            Atag = c4d.BaseTag(1029989)
            Atag[363257074] = 1
            Atag[1150993202] = 1
            Atag[1039494868] = 1
            Atag[1635638890] = 0
            Atag[486485632] = False
            Atag[408131505] = True
            Atag[1039494868] = 1 if applies_to_imported_geometry else 10
            Atag[1635638890] = 0.5 if applies_to_imported_geometry else 5
            Atag[1150993202] = 3
            item.InsertTag(Atag)

def apply_material_to_object(mat, item, useDisplacement, renderer_engine, applies_to_imported_geometry=False):
    try:
        # Apply the material to the model
        tag = item.GetTag(c4d.Ttexture)
        if tag == None:
            tag = c4d.TextureTag()
            item.InsertTag(tag)
        tag.SetMaterial(mat)
        tag[c4d.TEXTURETAG_PROJECTION] = 6
        setup_geometry_tags(renderer_engine, item, useDisplacement, applies_to_imported_geometry)
    except Exception as e:
        helpers.handle_exception(e, "Failed to apply material to object")

def import_payload(payload: fabplugins.Payload, callback_logger: fabplugins.CallbackLogger):
    """Main import function, called with json data received from TCP socket as argument"""
    doc = c4d.documents.GetActiveDocument()

    # Interpret Quixel-specific metadata
    Q = payload.metadata.quixel_filtered
    is_quixel                = len(payload.metadata.quixel_json) > 0
    prefer_specular_workflow = Q.get("prefer_specular_workflow", False) # Previously, this was forced to True
    is_metal =                 Q.get("is_metal", False)
    is_snow =                  Q.get("is_snow", False)
    is_scatter =               Q.get("is_scatter", False)
    can_have_displacement =    Q.get("displacement", True)

    renderer_engine = helpers.get_renderer_id()
    callback_logger.set_options(renderer = renderer_engine)
    if renderer_engine not in ["Physical/Standard", "Redshift", "Arnold", "Octane"]:
        helpers.show_error_message(f"Your current render engine is not supported ({renderer_engine})\nSupported : Physical, Standard, Octane, Redshift, and Arnold")
        # TODO: we should only return afterwards
        return

    # This is done to match the legacy
    if payload.metadata.type == "brush":
        callback_logger.log(status = "critical", message = "Asset type Brush not supported yet")
        return

    # Previously, physical used material[c4d.MATERIAL_PREVIEWSIZE] to set a viewport resolution. Now ignored.
    # preview_size = {"unset": 11, "4k": 12, "8k":13}.get(payload.metadata_generic.get("resolution", "unset"), 11)

    # Assets with a fixed scale
    is_fixed_scale = False
    for meta in payload.metadata.quixel_json.get("meta", []):
        if (meta['key'] in ['isScaleFixed', 'small3dasset']) and (meta['value'].lower() == 'true'):
            is_fixed_scale = True

    # TODO : those were set by the UI, find good candidates values for them
    prefer_exr = True
    applyToSelection = (len(payload.models) == 0) and (len(payload.materials) == 1) and (payload.metadata.type == "material")

    if(c4d.GetC4DVersion() < 19000):
        callback_logger.log(status = "critical", message = "Unsupported Cinema 4D version")
        return

    # Sanitize payload names
    # TODO: this should be improved, hardly readable / scalable
    name = payload.root_name
    material_name = f"{name}_{payload.id}"

    # TODO: info can be gathered to send debug info to the application
    if(c4d.GeGetCurrentOS() == 1): info = helpers.GetLogData(renderer_engine=renderer_engine)

    # Gather assets already selected
    selection = helpers.get_all_objects(in_selection=True)

    def import_model(model_payload: fabplugins.Model):

        old_objects = helpers.get_all_objects()
        new_objects = []

        # Tries to convert gltf uris to absolute to overcome c4d limitations
        if Path(model_payload.file).suffix.lower() == ".gltf":
            try:
                temp_gltf = helpers.make_gltf_with_absolute_paths(str(model_payload.file))
                model_payload.file = Path(temp_gltf)
            except:
                print(traceback.format_exc())
                print("Could not convert gltf paths to absolute, import continues with original gltf")

        # Import all files in the payload
        import_flags = c4d.SCENEFILTER_OBJECTS
        if len(payload.materials) == 0: # Only import materials if no material is passed in the payload
            import_flags |= c4d.SCENEFILTER_MATERIALS
        success = c4d.documents.MergeDocument(c4d.documents.GetActiveDocument(), str(model_payload.file), import_flags, None)
        if not success:
            callback_logger.log(status = "warning", message = f"Failed merging file {Path(model_payload.file).name}")
        
        just_imported = [o for o in helpers.get_all_objects() if o not in old_objects]
        new_objects.extend(just_imported)

        return {"material_index": model_payload.material_index, "meshes": new_objects}

    imported_models = []
    for model_payload in payload.models:
        imported_objects = import_model(model_payload)
        imported_models.append(imported_objects)

    def import_material(material_payload: fabplugins.Material):

        def filter_textures():
            textures = {}
            for channel_type, texture_channel in material_payload.textures.items():
                textures[channel_type] = Path(texture_channel)
            if not textures:
                return None
            # Use exr or jpg alternatives if needed
            if can_have_displacement and (displacement_path := textures.get("displacement", None)):
                displacement_path = Path(displacement_path)
                extension = displacement_path.suffix
                if renderer_engine == "Octane":
                    if extension == ".exr":
                        # Force Octane to use jpg displacement if exrs are given
                        jpg_alternative = displacement_path.with_suffix(".jpg")
                        jpeg_alternative = displacement_path.with_suffix(".jpeg")
                        if jpg_alternative.exists(): 
                            textures["displacement"] = jpg_alternative
                        elif jpeg_alternative.exists():
                            textures["displacement"] = jpeg_alternative
                elif extension != ".exr" and prefer_exr:
                    # Other renderers can use exr if we wish
                    exr_alternative = displacement_path.with_suffix(".exr")
                    if exr_alternative.exists(): 
                        textures["displacement"] = exr_alternative
            # # Decode if needed, and use str
            # if(c4d.GetC4DVersion() >= 23000):
            #     return {t.decode("utf-8") : str(f).decode("utf-8") for (t,f) in textures.items()}
            # else:
            return {t : str(f) for (t,f) in textures.items()}
        
        def create_material(textures):
            material = None
            try:
                match renderer_engine:
                    case "Physical/Standard":
                        material = renderers.physical_material(textures, material_name, is_metal, len(imported_models) > 0, is_snow, payload.metadata.type)
                    case "Redshift":
                        material = renderers.redshift_material(textures, material_name, is_metal, is_snow)
                    case "Arnold":
                        material = renderers.arnold_material(textures, material_name, is_metal)
                    case "Octane":
                        material = renderers.octane_material(textures, material_name, is_metal, payload.metadata.type, len(imported_models) > 0, prefer_specular_workflow)
            except Exception as e:
                helpers.handle_exception(e, "Failed to setup material")
            return material

        # TODO: we should do this once per import only
        if renderer_engine not in ["Physical/Standard", "Redshift", "Arnold", "Octane"]:
            helpers.show_error_message(f"Your current render engine is not supported ({renderer_engine})\nSupported : Physical, Standard, Octane, Redshift, and Arnold")
            return None

        textures = filter_textures()
        material = create_material(textures)

        return material

    imported_materials = []
    for material_payload in payload.materials:
        if material := import_material(material_payload):
            imported_materials.append(material)

    # Apply the materials to the relevant geometries
    # TODO: if we were to use material indices, this is where we would do it
    # In the meantime, this assumes only on material was imported
    if len(imported_materials) == 1:
        # One material is imported, assign it to the selection or to imported models
        material = imported_materials[0]
        if material:
            if applyToSelection and len(selection) > 0:
                for selected_object in selection:
                    # TODO: add to everything that was selected, includinig children, non polygon objects... 
                    apply_material_to_object(material, selected_object, can_have_displacement, renderer_engine, applies_to_imported_geometry=False)
            elif len(imported_models) > 0:
                # We apply the material to geometries we just imported
                for polygon_object in [obj for model in imported_models for obj in model.get("meshes") if isinstance(obj, c4d.PolygonObject)]:
                    apply_material_to_object(material, polygon_object, can_have_displacement, renderer_engine, applies_to_imported_geometry=True)
            else:
                # No selection, no imported models, simply create a tag matching the material
                tag = c4d.BaseTag( c4d.Ttexture )
                tag[c4d.TEXTURETAG_MATERIAL] = material
                tag[c4d.TEXTURETAG_PROJECTION] = 6
                # TODO: this needs a warning
                print("A material was imported and made available in a texture tag", tag)
        else:
            print("Imported material is invalid, this should not happen")
    elif len(imported_materials) >= 2:
        # Loop on models, find their material index, check they're right, proceed
        for model in imported_models:
            material_index = model.get("material_index", -1)
            if material_index is not None and material_index != -1:
                if material_index < len(imported_materials):
                    material = imported_materials[material_index]
                    for mesh in model.get("meshes", []):
                        if mesh is not None and isinstance(mesh, c4d.PolygonObject):
                            apply_material_to_object(material, mesh, can_have_displacement, renderer_engine, applies_to_imported_geometry=True)
                else:
                    print("A material index is above the number of imported materials, this should not happen")

    # Merge native c4d files into the active document
    if len(payload.native_files):

        old_objects = helpers.get_all_objects()
        new_objects = []

        for c4d_file in payload.native_files:
            try:
                if Path(c4d_file).suffix.lower().endswith("c4d"):
                    ok = c4d.documents.MergeDocument(doc, str(c4d_file), c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS | c4d.SCENEFILTER_MERGESCENE)
                    if not ok:
                        raise RuntimeError("Merge failed")
            except:
                print("Fab: Issue merging c4d file into document:", str(c4d_file))
                print(traceback.format_exc())
            # callback_logger.log(status = "warning", message = f"Failed merging file {Path(model_payload.file).name}")

        just_imported = [o for o in helpers.get_all_objects() if o not in old_objects]
        imported_models.append({"meshes": just_imported})

    # Reparenting / renaming
    top_parents = []
    try:
        for model in imported_models:
            for mesh in model.get("meshes", []):
                parent = mesh
                while parent.GetUp():
                    parent = parent.GetUp()
                top_parents.append(parent)
        top_parents = list(set(top_parents))
    except:
        pass
    try:
        if len(top_parents) == 1:
            # if there is one and it is an empty node, rename it
            top_parents[0].SetName(payload.root_name)
        elif len(top_parents) > 1:
            # Multiple parents, we create a new group
            newParent = c4d.BaseObject(c4d.Onull)
            newParent.SetName(payload.root_name)
            doc.InsertObject(newParent)
            for top_parent in top_parents:
                top_parent.InsertUnder(newParent)
    except:
        print("Failed reparenting assets, this should not have happened, but should not impact import negatively")
        print(traceback.format_exc())

    n_imported_geometries = sum([len(m.get("meshes", [])) for m in imported_models])

    # Refresh the current view to update materials visibility
    c4d.EventAdd()

    # TODO : we should to pass the successful import to the main app
    msg = f"Imported {n_imported_geometries} object(s) and {len(imported_materials)} material(s)"
    if len(imported_materials) > 0 or n_imported_geometries > 0:
        callback_logger.log(status="success", message=msg)
    else:
        callback_logger.log(status="error", message=msg)
