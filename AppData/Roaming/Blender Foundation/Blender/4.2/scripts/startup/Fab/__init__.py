# coding=utf-8
# TODO: 
# Add nice messages in UI
# Ctrl + Z makes blender crash !

import bpy
from bpy.app.handlers import persistent

import os
import sys
import json
import traceback
from pathlib import Path
from typing import List

bl_info = {
    "name": "Fab",
    "description": "Connects Blender to Fab for one-click imports from the Epic Games Launcher",
    "author": "Epic Games",
    "version": (0, 2, 15),
    "blender": (3, 6, 0),
    "warning": "",
    "support": "COMMUNITY",
    "category": "Import-Export"
}
plugin_version=".".join([str(i) for i in bl_info["version"]])

# Code shared by python Fab plugins
from . import fabplugins
listener = fabplugins.Listener(port=28889, plugin_version=plugin_version)
callback_logger = fabplugins.CallbackLogger(name="blender", version=bpy.app.version_string, port=24563, callback=print)
callback_logger.set_options(plugin_version=plugin_version)

def import_payload(payload: fabplugins.Payload):
    """Main import function, called with json data received from TCP socket as argument"""
    imported_models = []
    imported_materials = {}
    imported_materials_indexed = []

    # Interpret Quixel-specific metadata
    Q = payload.metadata.quixel_filtered
    prefer_specular_workflow = Q.get("prefer_specular_workflow", False)
    is_metal =                 Q.get("is_metal", False)
    is_snow =                  Q.get("is_snow", False)
    is_scatter =               Q.get("is_scatter", False)
    is_plant =                 Q.get("is_plant", False)
    displacement_scale =       Q.get("displacement_scale", 0)
    displacement_bias =        Q.get("displacement_bias", 0.5)

    callback_logger.set_options(id=payload.id, path=payload.path, port=payload.metadata.launcher_port)

    existing_objects = bpy.data.objects[:]

    def import_material(material_payload: fabplugins.Material) -> bpy.types.Material:

        is_cycles = bpy.context.scene.render.engine.lower() == "cycles"

        # Create the material and set some generic attributes
        material = bpy.data.materials.new( material_payload.name )
        material.use_nodes = True
        node_principled = material.node_tree.nodes.get("Principled BSDF", None)
        node_principled.distribution = 'MULTI_GGX'
        material_output_node = material.node_tree.nodes.get("Material Output", None)

        def link_nodes(input, output) -> bool:
            if input is None or output is None:
                return False
            else:
                material.node_tree.links.new(input, output)
                return True
        
        def add_generic_node(nodeName, PosX, PosY):
            n = material.node_tree.nodes.new(nodeName)
            n.location = (PosX, PosY)
            return n
        
        def connect_node_to_principled(input_socket_names, node_texture):
            # Check for input existence before connecting the nodes
            input_socket = None
            if isinstance(input_socket_names, list):
                for name in input_socket_names:
                    if input_socket := node_principled.inputs.get(name):
                        break
            else:
                input_socket = node_principled.inputs.get(input_socket_names)

            if input_socket is None:
                print(f"Fab: No input socket found in principled shader amongst candidate(s) '{input_socket_names}'")
            else:
                if not link_nodes(input_socket, node_texture.outputs[0]):
                    print(f"Fab: Error linking some material nodes, this should not happen")

        def create_texture_node(channel: Path, PosX, PosY, colorspace = "Non-Color", connectToMaterial = False, materialInputNames = "", separateRedChannel = False):
            node_texture = add_generic_node('ShaderNodeTexImage', PosX, PosY)
            node_texture.image = bpy.data.images.load(str(channel))
            node_texture.show_texture = True
            node_texture.image.colorspace_settings.name = colorspace
            # If it is Cycles render we connect it to the mapping node.
            if is_cycles:
                link_nodes(node_texture.inputs.get("Vector"), mappingNode.outputs.get("Vector"))
            if separateRedChannel:
                node_texture.location[0] = node_texture.location[0] - 300
                node_separate_red = add_generic_node('ShaderNodeSeparateRGB', node_texture.location[0] + 300, node_texture.location[1])
                link_nodes(node_separate_red.inputs[0], node_texture.outputs.get("Color"))
                node_texture = node_separate_red
            if connectToMaterial:
                connect_node_to_principled(materialInputNames, node_texture)
            return node_texture

        # Shared locations for shader nodes
        c00 = -2100
        c0 = -1700
        c1 = -1350
        c2 = -650
        c3 = -250
        c4 = 100

        # An optionnal node to map UVs
        mappingNode = None
        if is_cycles:
            mappingNode = add_generic_node("ShaderNodeMapping", c1, -900)
            mappingNode.vector_type = 'TEXTURE'
            texCoordNode = add_generic_node("ShaderNodeTexCoord", c0, -900)
            link_nodes(mappingNode.inputs.get("Vector"), texCoordNode.outputs.get("UV"))

        # Default or hard-coded values
        if input := node_principled.inputs.get("Metallic") :  input.default_value = 1 if is_metal else 0
        if input := node_principled.inputs.get("IOR") :       input.default_value = 1.45
        if input := node_principled.inputs.get("Specular IOR Level") :  input.default_value = 0
        elif input := node_principled.inputs.get("Specular") :  input.default_value = 0
        if input := node_principled.inputs.get("Coat Weight") : input.default_value = 0
        transmission_node = None
        if is_snow:
            node_principled.subsurface_method = 'RANDOM_WALK'
            if input := node_principled.inputs.get("Subsurface Radius") : input.default_value = (0.4, 0.5, 0.6)
            if input := node_principled.inputs.get("Subsurface Scale") : input.default_value = (0.1)
        
        uses_custom_plant_setup = is_plant and ("translucency" in material_payload.textures) and ("opacity" in material_payload.textures)

        # Process the texture channels
        for channel_type, channel in material_payload.textures.items():
            if not channel:
                print(f"Fab: Received texture channel {channel_type} is invalid for material {material_payload.name}")
            match channel_type:
                case "albedo":
                    suffix = Path(channel).suffix.lower()
                    node_albedo = create_texture_node(channel, c2, 450, "Linear" if suffix == ".exr" else "sRGB")
                    # Handle AO
                    if ao_channel := material_payload.textures.get("occlusion", None):
                        node_multiply = add_generic_node('ShaderNodeMixRGB', c3, 300)
                        node_multiply.blend_type = 'MULTIPLY'
                        if facInput := node_multiply.inputs.get("Fac", None):
                            facInput.default_value = 0.5
                        node_ao = create_texture_node(ao_channel, c2, 150, "Non-Color", separateRedChannel=True)
                        link_nodes(node_multiply.inputs.get("Color1"), node_albedo.outputs[0])
                        link_nodes(node_multiply.inputs.get("Color2"), node_ao.outputs[0])
                        connect_node_to_principled("Base Color", node_multiply)
                    else:
                        connect_node_to_principled("Base Color", node_albedo)
                    # Not 100% confident on fuzz/sheen implementation, so stay conservative and use fuzz as sheen weight, with basecolor as tint
                    if fuzz_channel := material_payload.textures.get("fuzz", None):
                        create_texture_node(fuzz_channel, c2, -1950, "Non-Color", True, ["Sheen Weight", "Sheen"], separateRedChannel=True)
                        connect_node_to_principled("Sheen Tint", node_albedo)
                case "occlusion":
                    # Only plug the ao by itself if no albedo is associated with it
                    if "albedo" not in material_payload.textures:
                        node_ao = create_texture_node(channel, c2, 150, "Non-Color", separateRedChannel=True)
                        connect_node_to_principled("Base Color", node_ao)
                case "opacity":
                    if not uses_custom_plant_setup:
                        create_texture_node(channel, c2, -750, "Non-Color", True, "Alpha", separateRedChannel=True)
                        material.blend_method = 'HASHED'
                case "translucency":
                    if not uses_custom_plant_setup:
                        transmission_node = create_texture_node(channel, c2, -1950, "Non-Color" if is_snow else "sRGB", True, ["Transmission Weight", "Transmission"], separateRedChannel=is_snow)
                case "transmission":
                    if "translucency" not in material_payload.textures:
                        transmission_node = create_texture_node(channel, c2, -1950, "Non-Color", True, ["Transmission Weight", "Transmission"], separateRedChannel=True)
                case "displacement":
                    # Add vector>displacement map node
                    node_displacement = add_generic_node("ShaderNodeDisplacement", c4, -2250)
                    if input := node_displacement.inputs.get("Scale") : input.default_value = displacement_scale
                    if input := node_displacement.inputs.get("Midlevel") : input.default_value = displacement_bias
                    node_displacement_map = create_texture_node(channel, c2, -2250, "Non-Color", separateRedChannel=True)
                    link_nodes(node_displacement.inputs.get("Height"), node_displacement_map.outputs[0])
                    # Get the material output displacement input
                    if material_output_node is not None and (displacement_input := material_output_node.inputs.get("Displacement")) :
                        link_nodes(displacement_input, node_displacement.outputs.get("Displacement"))
                    # Set the displacement method, TODO: ideally we would check on the blender version
                    try:
                        material.cycles.displacement_method = 'BOTH'
                    except:
                        pass
                    try:
                        material.displacement_method = 'BOTH'
                    except:
                        pass
                # If both roughness and glossiness are present, prefer roughness
                case "roughness":
                    create_texture_node(channel, c2, -450, "Non-Color", True, "Roughness", separateRedChannel=True)
                case "emission":
                    create_texture_node(channel, c2, -750, "sRGB", True, "Emission Color")
                    try:
                        node_principled.inputs.get("Emission Strength").default_value = 5 # An arbitrary but reasonable value
                    except:
                        pass
                case "glossiness":
                    if "roughness" not in material_payload.textures:
                        node_gloss = create_texture_node(channel, c2, -450, "Non-Color", separateRedChannel=True)
                        node_invert = add_generic_node("ShaderNodeInvert", c3, -450)
                        link_nodes(node_invert.inputs.get("Color"), node_gloss.outputs[0])
                        link_nodes(node_principled.inputs.get("Roughness"), node_invert.outputs.get("Color"))
                case "specular":
                    if "metal" not in material_payload.textures:
                        create_texture_node(channel, c2, -1650, "sRGB", True, ["Specular IOR Level", "Specular"])
                case "metal":
                    # For metalness, we ignore the prefer_specular_workflow as some Fab data is wrong for assets with a metalness map
                    create_texture_node(channel, c2, -150, "Non-Color", True, "Metallic", separateRedChannel=True)
                    if specular_channel := material_payload.textures.get("specular"):
                        # TODO: not 100% sure of this, as surfaces with low roughness can become pretty glossy with MGS data
                        create_texture_node(specular_channel, c2, -1650, "Non-Color", True, ["Specular IOR Level", "Specular"])
                case "orm":
                    # Only plug orm if no other map is available
                    if not any([ch in material_payload.textures for ch in ["occlusion", "metal", "roughness"]]):
                        node_orm = create_texture_node(channel, c2, -450, "Non-Color")
                        node_separate = add_generic_node('ShaderNodeSeparateRGB', node_orm.location[0] + 300, node_orm.location[1])
                        link_nodes(node_separate.inputs[0], node_orm.outputs.get("Color"))
                        if "albedo" not in material_payload.textures:
                            link_nodes(node_principled.inputs.get("Base Color"), node_separate.outputs[0])
                        link_nodes(node_principled.inputs.get("Roughness"), node_separate.outputs[1])
                        link_nodes(node_principled.inputs.get("Metallic"), node_separate.outputs[2])
                case "fuzz":
                    # this is handled in the albedo branch, as linked to the albedo node
                    pass
                    
                # We'll handle normal and bump separately
                case "normal" | "bump":
                    pass
                # Cases we don't handle
                case _:
                    print(f"Fab: Received unsupported channel {channel_type}")
                    pass
            
        # Normal and bumps depend on each other
        # In particular, we don't want to use the bump if displacement is active
        channel_bump = material_payload.textures.get("bump", None)
        channel_normal = material_payload.textures.get("normal", None)
        invert_normal = material_payload.flipnmapgreenchannel
        # For now, deactivate the bump as incoming data seems corrupted
        use_bump = False #channel_bump is not None and not is_high_poly
        if channel_normal and use_bump:
            node_bumpmap = create_texture_node(channel_bump, c2, -1050, "Non-Color", separateRedChannel=True)
            # Create the normal map node and invert the texture if needed
            node_normalmap = create_texture_node(channel_normal, c00 if invert_normal else c2, -1350, "Non-Color")
            if invert_normal:
                node_normalmap_separate = add_generic_node('ShaderNodeSeparateRGB', c0, -1350)
                node_normalmap_invert = add_generic_node('ShaderNodeInvert', c1, -1350)
                node_normalmap_combine = add_generic_node('ShaderNodeCombineRGB', c2, -1350)
                # I have not checked any of this, it is just my best guess and quick thoughts.
                link_nodes(node_normalmap.outputs.get("Color"), node_normalmap_separate.inputs[0])
                link_nodes(node_normalmap_separate.outputs.get("R"), node_normalmap_combine.inputs[0])
                link_nodes(node_normalmap_separate.outputs.get("G"), node_normalmap_invert.inputs[1])
                link_nodes(node_normalmap_separate.outputs.get("B"), node_normalmap_combine.inputs[2])
                link_nodes(node_normalmap_invert.outputs.get("Color"), node_normalmap_combine.inputs[1])
                node_normalmap_invert.inputs[0].default_value = 1
                node_normalmap = node_normalmap_combine

            node_bump = add_generic_node("ShaderNodeBump", c3, -1050)
            if input := node_bump.inputs.get("Strength") : input.default_value = 0.1
            node_normal = add_generic_node("ShaderNodeNormalMap", c3, -1350)
            link_nodes(node_normal.inputs.get("Color"), node_normalmap.outputs.get("Color", node_normalmap.outputs.get("Image")))
            link_nodes(node_bump.inputs.get("Height"), node_bumpmap.outputs[0])
            link_nodes(node_bump.inputs.get("Normal"), node_normal.outputs.get("Normal"))
            connect_node_to_principled("Normal", node_bump)
        elif channel_normal:
            node_normalmap = create_texture_node(channel_normal, c00 if invert_normal else c2, -1350, "Non-Color")
            if invert_normal:
                node_normalmap_separate = add_generic_node('ShaderNodeSeparateRGB', c0, -1350)
                node_normalmap_invert = add_generic_node('ShaderNodeInvert', c1, -1350)
                node_normalmap_combine = add_generic_node('ShaderNodeCombineRGB', c2, -1350)
                # I have not checked any of this, it is just my best guess and quick thoughts.
                link_nodes(node_normalmap.outputs.get("Color"), node_normalmap_separate.inputs[0])
                link_nodes(node_normalmap_separate.outputs.get("R"), node_normalmap_combine.inputs[0])
                link_nodes(node_normalmap_separate.outputs.get("G"), node_normalmap_invert.inputs[1])
                link_nodes(node_normalmap_separate.outputs.get("B"), node_normalmap_combine.inputs[2])
                link_nodes(node_normalmap_invert.outputs.get("Color"), node_normalmap_combine.inputs[1])
                node_normalmap_invert.inputs[0].default_value = 1
                node_normalmap = node_normalmap_combine
            node_normal = add_generic_node("ShaderNodeNormalMap", c3, -1350)
            link_nodes(node_normal.inputs.get("Color"), node_normalmap.outputs.get("Color", node_normalmap.outputs.get("Image")))
            connect_node_to_principled("Normal", node_normal)
        elif use_bump:
            node_bumpmap = create_texture_node(channel_bump, c2, -1050, "Non-Color", separateRedChannel=True)
            node_bump = add_generic_node("ShaderNodeBump", c3, -1050)
            if input := node_bump.inputs.get("Strength") : input.default_value = 0.1
            link_nodes(node_bump.inputs.get("Height"), node_bumpmap.outputs[0])
            connect_node_to_principled("Normal", node_bump)
        
        # Set an intensity factor of 0.25 for translucency if the asset is Quixel Megascan snow
        if is_snow and transmission_node:
            node_math = add_generic_node('ShaderNodeMath', c3, -1950)
            node_math.operation = "MULTIPLY"
            node_math.inputs[1].default_value = 0.25
            link_nodes(node_math.inputs[0], transmission_node.outputs[0])
            connect_node_to_principled(["Transmission Weight", "Transmission"], node_math)
            connect_node_to_principled(["Subsurface Weight", "Subsurface"], transmission_node)
        
        if uses_custom_plant_setup:
            # For Quixel plants, we can do a neat setup based on translucent "add shader" and better opacity masking
            try:
                bsdf_loc = node_principled.location
                material_output_node.location[0] = bsdf_loc[0] + 1150
                translucency_node = create_texture_node(material_payload.textures.get("translucency"), c2, -1950, "sRGB")
                opacity_node = create_texture_node( material_payload.textures.get("opacity"), c2, -750, "Non-Color", separateRedChannel=True)
                node_translucent_shader = add_generic_node("ShaderNodeBsdfTranslucent", bsdf_loc[0] + 250, bsdf_loc[1] - 500)
                node_transparent_shader = add_generic_node("ShaderNodeBsdfTransparent", bsdf_loc[0] + 500, bsdf_loc[1])
                node_add_shader = add_generic_node("ShaderNodeAddShader", bsdf_loc[0] + 500, bsdf_loc[1] - 200)
                node_greater_than = add_generic_node("ShaderNodeMath", bsdf_loc[0] + 250, bsdf_loc[1] - 1000)
                node_mix_shader = add_generic_node("ShaderNodeMixShader", bsdf_loc[0] + 800, bsdf_loc[1])

                link_nodes(material_output_node.inputs.get("Surface", None), node_mix_shader.outputs[0])

                link_nodes(node_mix_shader.inputs[0], node_greater_than.outputs[0])
                link_nodes(node_mix_shader.inputs[1], node_transparent_shader.outputs[0])
                link_nodes(node_mix_shader.inputs[2], node_add_shader.outputs[0])

                link_nodes(node_greater_than.inputs[0], opacity_node.outputs[0])
                node_greater_than.operation = "GREATER_THAN"
                node_greater_than.inputs[1].default_value = 0.2
                node_greater_than.use_clamp = True

                link_nodes(node_add_shader.inputs[0], node_principled.outputs[0])
                link_nodes(node_add_shader.inputs[1], node_translucent_shader.outputs[0])

                link_nodes(node_translucent_shader.inputs[0], translucency_node.outputs[0])

                material.blend_method = 'HASHED'
            except Exception as e:
                print("Fab: encountered an issue setting up plants shader")
                print(traceback.format_exc())


        return material

    def import_model(model_payload: fabplugins.Model) -> List[bpy.types.Object]:

        existing_objects = bpy.context.scene.objects[:]

        for f in [model_payload.file]:

            model_filepath = Path(f).resolve()
            model_extension = model_filepath.suffix
            if not model_filepath.exists(): 
                print(f"{model_filepath} does not exist, skipping import")
                continue

            model_filepath = str(model_filepath)

            match model_extension.lower():
                case ".gltf" | ".glb":
                    bpy.ops.import_scene.gltf(filepath=model_filepath)
                    break
                case ".usd" | ".usda" | ".usdc" | ".usdz":
                    bpy.ops.wm.usd_import(filepath=model_filepath, scale=1) # Scale argument should not have to be used, there is a data or import issue
                    break
                case ".fbx":
                    bpy.ops.import_scene.fbx(filepath=model_filepath)
                    break
                case ".obj":
                    # TODO: not ideal as not extensively tested 
                    try: # Before 2.92
                        bpy.ops.import_scene.obj(filepath=model_filepath, use_split_objects = True, use_split_groups = True, global_clight_size = 1.0)
                    except:
                        try:
                            bpy.ops.import_scene.obj(filepath=model_filepath, use_split_objects = True, use_split_groups = True, global_clamp_size  = 1.0)
                        except:
                            try:
                                bpy.ops.wm.obj_import(filepath=model_filepath)
                            except:
                                print("Fab: Could not import obj file, this shoud not happen")
                    break
                case ".abc":
                    bpy.ops.wm.alembic_import(filepath=model_filepath, as_background_job=False, scale=0.01)
                    break
                case _:
                    callback_logger.log(status="warning", message=f"Unrecognized file extension {model_extension.lower()}")
                    continue

        return [o for o in bpy.context.scene.objects if o not in existing_objects and o.type == "MESH"]

    # Import materials if any
    if payload.materials:
        for material_data in payload.materials:
            try:
                if material := import_material(material_data):
                    imported_materials[material_data.name] = material
                    imported_materials_indexed.append(material)
            except Exception as e:
                print(f"Fab: Error importing material {material_data.name}")
                print(traceback.format_exc())
                imported_materials_indexed.append(None)
        
    # Then, import model geometries
    if payload.models:
        for model_data in payload.models:
            try:
                if models := import_model(model_data):
                    imported_models.extend(models)
                    # If we already imported materials, and the payload contains indices to use one, link the materials we imported
                    if len(imported_materials) and model_data.material_index is not None:
                        if model_data.material_index == -1:
                            # This will be the case for multi materials
                            # In that case, we'll assign materials at the end
                            pass
                        elif model_data.material_index < len(imported_materials):
                            # Only link the material if it is not None, for an unknown reason
                            if material := imported_materials_indexed[model_data.material_index]:
                                for object in models:
                                    object.active_material = material
            except Exception as e:
                print(f"Fab: Error importing model {model_data.name}")
                print(traceback.format_exc())
        
        # Try to map multiple materials to the meshes materials
        # For every available slot, try to find a matching material in the imported list
        # We'll get pretty liberal, checking first material names, then model names
        try:
            try_mapping = all([m.material_index == -1 for m in payload.models]) and (len(imported_materials) == len(payload.materials))
            if try_mapping:
                imported_materials_sorted = sorted([n for n in imported_materials], reverse=True)
                for imported_model in imported_models:
                    for slot in imported_model.material_slots:
                        if assigned_material := slot.material:
                            for n in imported_materials_sorted:
                                assigned_material_name = assigned_material.name.lower()
                                n_lower = n.lower()
                                match_material_names = assigned_material_name.startswith(n_lower)
                                match_material_and_model = n_lower in imported_model.name.lower()
                                match_with_model_name_and_material = n_lower.split(".")[0].replace(imported_model.name.split(".")[0].lower(), "").replace("_", "") in assigned_material_name # ScifiPistol_Bloack.001
                                if match_material_names or match_material_and_model or match_with_model_name_and_material:
                                    slot.material = None
                                    try:
                                        bpy.data.materials.remove(assigned_material)
                                    except:
                                        pass
                                    slot.material = imported_materials[n]
                                    break
        except:
            print("Fab: Failed matching multiple materials with one mesh")
            print(traceback.format_exc())

    # And additional textures
    try:
        for additional_texture in payload.additional_textures:
            bpy.data.images.load(additional_texture, check_existing=False)
    except:
        print("Fab: Issue importing additional textures, ignoring")
        print(traceback.format_exc())

        # Append objects from .blend files in a new collection
    
    # Append the content of .blend files
    for blend_file in payload.native_files:
        try:
            if Path(blend_file).suffix.lower().endswith("blend"):
                data_to = None
                with bpy.data.libraries.load(blend_file, link=False) as (data_from, data_to):
                    # data_to.materials = data_from.materials
                    data_to.objects = data_from.objects
                    data_to.images = data_from.images
                    data_to.materials = data_from.materials
                    data_to.lights = data_from.lights
                    data_to.curves = data_from.curves
                if data_to is not None:
                    for obj in data_to.objects:
                        if obj is not None:
                            bpy.context.collection.objects.link(obj)
                    imported_models.extend(data_to.objects)
                    for material in data_to.materials:
                        imported_materials[material.name] = material
        except:
            print("Fab: Issue importing blend file:", str(blend_file))
            print(traceback.format_exc())

    # Reparenting / renaming operations
    try:
        new_objects = [o for o in bpy.data.objects if o not in existing_objects]
        # Reparenting / renaming
        top_parents = []
        try:
            for new_object in new_objects:
                parent = new_object
                while parent.parent:
                    parent = parent.parent
                top_parents.append(parent)
            top_parents = list(set(top_parents))
        except:
            pass
        try:
            if len(top_parents) == 1:
                # if there is one and it is an empty node, rename it
                top_parents[0].name = payload.root_name
            elif len(top_parents) > 1:
                # Multiple parents, we create a new empty object
                bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0))
                empty = bpy.context.active_object
                empty.name = payload.root_name
                for top_parent in top_parents:
                    top_parent.parent = empty
        except:
            print("Failed reparenting assets, this should not have happened, but should not impact import negatively")
            print(traceback.format_exc())
    except:
        print("Fab: Issue encountered during reparenting, this should not have an effect on the import")
        print(traceback.format_exc())

    return imported_models, imported_materials
    
def import_buffered_data_if_any():
    if listener and (data := listener.payload()):
        try:

            # Get selected objects
            selection = [ o for o in bpy.context.scene.objects if o.type == "MESH" and o.select_get() ]

            for payload_data in data:

                # Convert the json data into a structured payload object
                try:
                    payload = fabplugins.Payload(payload_data, print_debug=True)
                except Exception as e:
                    callback_logger.log(status="warning", message=f"Failed interpreting data sent by launcher")
                    print(traceback.format_exc())
                    continue

                # Execute the actual import routines
                imported_models, imported_materials = import_payload(payload)
                n_imported_models = len(imported_models)
                n_imported_materials = len(imported_materials)

                # If no models and only one material were created, apply it to selected objects
                apply_material_to_selection = True
                if apply_material_to_selection and (n_imported_models == 0) and (n_imported_materials == 1):
                    if material := list(imported_materials.values())[0]:
                        for object in selection:
                            object.active_material = material
                
                # Check that the number of models imported matches the payloads
                # And send data back to the launcher
                n_payload_models = len(imported_models)
                n_payload_materials = len(imported_materials)
                if not(n_imported_models or n_imported_materials) and len(payload.native_files) == 0:
                    callback_logger.log(status="error", message="No model nor material imported")
                else:
                    if n_imported_models != n_payload_models:
                        callback_logger.log(status="warning", message=f"{n_imported_models} models imported, but {n_payload_models} should have been")
                    if n_imported_materials != n_payload_materials:
                        callback_logger.log(status="warning", message=f"{n_imported_materials} models imported, but {n_payload_materials} should have been")
                    callback_logger.log(status="success", message=f"{n_imported_models} models and {n_imported_materials} materials imported")
        
        except Exception as e:
            callback_logger.log(status="error", message="An unknown error occured")
            print(traceback.format_exc())
    else:
        pass
    return 1.0 if bpy.app.timers.is_registered(import_buffered_data_if_any) else None

bpy.app.timers.register(import_buffered_data_if_any)

@persistent
def register_new_data_timer(_scene=None):
    if not bpy.app.timers.is_registered(import_buffered_data_if_any):
        bpy.app.timers.register(import_buffered_data_if_any)

def register():
    if listener.paused:
        listener.start()
    register_new_data_timer()
    if len(bpy.app.handlers.load_post) > 0:
        if "register_timer_that_checks_for_new_data_to_import" in bpy.app.handlers.load_post[0].__name__.lower() or register_new_data_timer in bpy.app.handlers.load_post:
            return
    bpy.app.handlers.load_post.append(register_new_data_timer)

def unregister():
    if bpy.app.timers.is_registered(import_buffered_data_if_any):
        bpy.app.timers.unregister(import_buffered_data_if_any)
    if len(bpy.app.handlers.load_post) > 0:
        if "register_timer_that_checks_for_new_data_to_import" in bpy.app.handlers.load_post[0].__name__.lower() or register_new_data_timer in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.remove(register_new_data_timer)
    listener.pause()
