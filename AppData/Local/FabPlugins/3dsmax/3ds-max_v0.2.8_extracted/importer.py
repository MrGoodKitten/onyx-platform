from pathlib import Path

import pymxs
rt = pymxs.runtime

import helpers
import ms_snippets as ms
import renderers
import traceback
from zipfile import ZipFile

import fabplugins
from version import version as plugin_version
callback_logger = fabplugins.CallbackLogger(name="3dsmax", version=str(pymxs.runtime.maxversion()[7]), port=24563, callback=print)

class Importer():

    def import_payload(self, payload: fabplugins.Payload):

        # Keep track of the initial selection
        initial_selection = list(rt.selection)
        existing_objects = list(rt.objects)
        rt.clearSelection()

        # Interpret Quixel-specific metadata
        Q = payload.metadata.quixel_filtered
        is_snow =                  Q.get("is_snow", False)
        is_plant =                 Q.get("is_plant", False)
        displacement_scale =       Q.get("displacement_scale", 0)
        displacement_bias =        Q.get("displacement_bias", 0.5)

        has_gltf = any([Path(f).suffix.lower() in [".gltf", ".glb"] for f in [m.file for m in payload.models]])
        has_usd = any([Path(f).suffix.lower() in [".usd", ".usdc", ".usda", ".usdz"] for f in [m.file for m in payload.models]])

        callback_logger.set_options(id=payload.id, path=payload.path, plugin_version=plugin_version)

        # If there are some gltf files in the payload files, stop the import as this should not happen
        if has_gltf:
            callback_logger.log(status="critical", message="3DS Max does not support gltf or glb files")
            return
        
        # If there are some usd files in the payload files, stop the import if the usd for 3ds max plugin is not found
        if has_usd:
            usdimport_plugin_available = False
            usdimport_plugin_loaded = False
            # Iterate over plugins to find usdimport.dli
            for p in range(1, pymxs.runtime.pluginManager.pluginDllCount + 1):
                name = pymxs.runtime.pluginManager.pluginDllName(p)
                if "usdimport" in name:
                    usdimport_plugin_available = True
                    if pymxs.runtime.pluginManager.isPluginDllLoaded(p):
                        usdimport_plugin_loaded = True
                    else:
                        try:
                            pymxs.runtime.pluginManager.loadPluginDll(p)
                            usdimport_plugin_loaded = True
                        except:
                            print("Error loading USD plugin, this should not happen", name)
                            print(traceback.print_exc())
            if usdimport_plugin_available:
                if not usdimport_plugin_loaded:
                    callback_logger.log(status="warning", message="Plugin 'USD Importer' is available but not loaded, this could happen the first time a USD is imported into 3DS Max")
            else:
                msg = "Plugin 'USD Importer' not available. Install from https://help.autodesk.com/view/3DSMAX/2024/ENU/?guid=GUID-1A33A64B-6829-4806-98FC-9B25E4ED47FC"
                callback_logger.log(status="critical", message=msg)
                return

            # Hack to extract usdz and replace the usdz payload file with an appropriate usd if possible
            for model_payload in payload.models:
                model_file = Path(model_payload.file)
                if model_file.suffix.lower() == ".usdz":
                    extract_destination = model_file.parent.parent / (model_file.stem + "_extracted_for_3ds_max")
                    if extract_destination.exists() and extract_destination.is_dir():
                        pass
                    else:
                        try:
                            # Extract the usdz and check for validity
                            with ZipFile(str(model_file), 'r') as zObject:
                                zObject.extractall(path=str(extract_destination))
                        except:
                            print("USDZ extraction failed, this should not happen")
                            continue
                    usd_file = helpers.find_first_usd_file_in_directory(extract_destination)
                    if usd_file is not None and usd_file.exists():
                        model_payload.file = str(usd_file)
                    else:
                        print("USD fie does not exist but should, aie aie aie")

        def create_material(textures, renderer_id, material_name="Material", flip_green=False):

            material = None
            mod = None

            # Find the appropriate shader
            match renderer_id:
                case "arnold":
                    material = rt.ai_standard_surface()
                case "redshift":
                    material = rt.rsStandardMaterial()
                case "octane":
                    material = rt.universal_material()
                case "vray":
                    material = rt.VRayMtl()
                case "corona":
                    material = rt.CoronaPhysicalMtl()
                case _:
                    return None, None

            # Safety return
            if material is None:
                return None, None

            material.name = helpers.generate_unique_name(material_name, rt.sceneMaterials)
            material.showInViewport = True

            # Import textures
            imported_bitmaps = {}
            for channel, texture_file in textures.items():

                sanitized_texture_file = str(texture_file).replace("\\", "/")
                bitmap = rt.Bitmaptexture(filename=sanitized_texture_file)
                bitmap.filename = sanitized_texture_file

                # Set the appropr
                bitmap.gamma = 2.2 if channel in ["albedo", "emission", "specular", "translucency"] else 1.0

                if channel == "glossiness" and "roughness" not in textures:
                    bitmap.output.invert = True

                # Use the red channel for linear maps
                if channel not in ["albedo", "translucency", "emission", "specular", "normal"]:
                    color_correct = rt.ColorCorrection()
                    color_correct.map = bitmap
                    color_correct.rewireMode = 3
                    color_correct.rewireR = 0
                    color_correct.rewireG = 0
                    color_correct.rewireB = 0
                    bitmap = color_correct

                imported_bitmaps[channel] = bitmap
            
            if renderer_id == "arnold":

                mod = rt.ArnoldGeometryPropertiesModifier()
                mod.double_sided = True # TODO : could this be used only for opacity ?

                for channel, bitmap in imported_bitmaps.items():
                    match channel:
                        case "albedo":
                            material.base_color_shader = bitmap
                            material.base = 1.0
                        case "roughness" | "glossiness":
                            material.specular = 1.0
                            if channel == "roughness" or ("roughness" not in imported_bitmaps):
                                material.specular_roughness_shader = bitmap
                        case "specular":
                            if "metal" not in textures:
                                material.specular_shader = bitmap
                        case "metal":
                            material.metalness = 1.0
                            material.metalness_shader = bitmap
                        case "normal":
                            normal_map_node = rt.CreateInstance(rt.Ai_Normal_Map, "MyArnoldNormal")
                            normal_map_node.input_shader = bitmap
                            normal_map_node.invert_y = flip_green
                            material.normal_shader = normal_map_node
                        case "opacity":
                            material.opacity_shader = bitmap
                            mod.enable_general_options = True
                            mod.opaque = False
                        case "emission":
                            material.emission = 1.0
                            material.emission_color_shader = bitmap
                
                # Transmission and translucency
                transmission = imported_bitmaps.get("transmission", None)
                translucency = imported_bitmaps.get("translucency", None)
                if is_snow:
                    material.subsurface_scale = 0.1
                    material.subsurface_type = 1
                    material.subsurface_radius = (102, 127.5, 153)
                    if transmission or translucency:
                        material.subsurface_shader = transmission if transmission else translucency
                        material.subsurface_color = (255, 255, 255)
                        multiplyNode = rt.RGB_Multiply()
                        multiplyNode.map1 = transmission if transmission else translucency
                        multiplyNode.color2 = (64, 64, 64)
                        material.transmission_shader = multiplyNode
                else:
                    if translucency:
                        material.subsurface_color_shader = translucency
                        material.subsurface = 0.55
                        material.exit_to_background = True
                        material.thin_walled = True
                    if transmission:
                        material.transmission_shader = transmission

                # Displacement through geometry modifier
                if displacement_bitmap := imported_bitmaps.get("displacement", None):
                    mod.displacement_map_on = True
                    mod.enable_displacement_options = True
                    mod.enable_subdivision_options = True
                    mod.subdivision_iterations = 3
                    mod.displacement_zero = displacement_bias
                    mod.displacement_height = displacement_scale
                    mod.displacement_enable_autobump = False
                    mod.displacement_map = displacement_bitmap

                # Sheen/fuzz with reusing the base color
                if fuzz := imported_bitmaps.get("fuzz", None):
                    material.sheen = 1.0
                    material.sheen_shader = fuzz
                    if albedo := imported_bitmaps.get("albedo"):
                        material.sheen_color_shader = albedo

            elif renderer_id == "redshift":

                mod = rt.Redshift_Mesh_Parameters()
                # mod.double_sided = True # TODO : could this be used only for opacity ?

                material.refl_ior = 1.5
                material.refl_color = (255, 255, 255)

                for channel, bitmap in imported_bitmaps.items():
                    match channel:
                        case "albedo":
                            if "occlusion" in imported_bitmaps:
                                material.base_color_map = rt.CompositeTexturemap()
                                material.base_color_map.mapEnabled.count = 2
                                material.base_color_map.blendMode[2] = 5
                                material.base_color_map.opacity[2] = 0
                                material.base_color_map.mapList[2] = imported_bitmaps["occlusion"]
                                material.base_color_map.mapList[1] = bitmap
                            else: 
                                material.base_color_map = bitmap
                                material.base_color = 1.0
                        case "roughness" | "glossiness":
                            material.refr_roughness = 1.0
                            material.refr_roughness_map = bitmap
                        case "specular":
                            if "metal" not in textures:
                                material.refl_weight = 1
                                material.refl_weight_map = bitmap
                        case "metal":
                            material.metalness = 1.0
                            material.metalness_map = bitmap
                        case "normal":
                            material.bump_input = rt.rsBumpMap()
                            material.bump_input.flipY = flip_green
                            material.bump_input.input_map = bitmap
                            material.bump_input.inputType = 1
                            # material.normal_shader = normal_map_node
                        case "opacity":
                            material.opacity_color_map = bitmap
                            # mod.enable_general_options = True
                            # mod.opaque = False
                        case "emission":
                            material.emission_weight = 1.0
                            material.emission_color_map = bitmap

                # Transmission and translucency
                transmission = imported_bitmaps.get("transmission", None)
                translucency = imported_bitmaps.get("translucency", None)
                if is_snow:
                    material.ms_radius_scale = 0.1
                    material.ms_mode = 2
                    material.ms_radius = (102, 127.5, 153)
                    if transmission or translucency:
                        material.ms_amount_map = transmission if transmission else translucency
                        material.ms_color = (255, 255, 255)
                        multiplyNode = rt.RGB_Multiply()
                        multiplyNode.map1 = transmission if transmission else translucency
                        multiplyNode.color2 = (64, 64, 64)
                        material.refr_weight_map = multiplyNode
                else:
                    if translucency:
                        material.ms_color_map = translucency
                        material.ms_amount = 0.55
                        material.refr_thin_walled = 1
                    if transmission:
                        material.refr_weight_map = transmission

                # Displacement through geometry modifier
                if displacement_bitmap := imported_bitmaps.get("displacement", None):
                    mod.displacementScale = displacement_scale
                    mod.maxDisplacement = 1
                    disp_node = rt.rsDisplacement()
                    disp_node.scale = 1
                    disp_node.texMap_map = displacement_bitmap
                    disp_node.newrange_min = 0.0
                    disp_node.newrange_max = 1.0
                    disp_node.scale = 1
                    material.displacement_input = disp_node
                    material.displacement_input_enable = True

                # Sheen/fuzz with reusing the base color
                if fuzz := imported_bitmaps.get("fuzz", None):
                    material.sheen_weight_map = fuzz
                    if albedo := imported_bitmaps.get("albedo"):
                        material.sheen_color_map = albedo
            
            elif renderer_id == "octane":
                mod = None

                # # mod.double_sided = True # TODO : could this be used only for opacity ?
                # material.refl_ior = 1.5
                # material.refl_color = (255, 255, 255)

                for channel, bitmap in imported_bitmaps.items():
                    match channel:
                        case "albedo":
                            material.albedo_tex = rt.RGB_image()
                            material.albedo_tex.gamma = 2.2
                            material.albedo_tex.name = "Albedo"
                            material.albedo_tex.filename_bitmaptex = bitmap
                            material.albedo_input_type = 2
                            # if useTransformNode do (
                            #     MAT_NODE_NAME.albedo_tex.transform = TransformNode
                            # )
                        case "roughness" | "glossiness":
                            useRoughness = "roughness" in imported_bitmaps
                            if useRoughness and (channel == "glossiness"):
                                pass
                            else:
                                material.roughness_tex = rt.Grayscale_image()
                                material.roughness_tex.gamma = 1.0
                                material.roughness_tex.name = "Roughness" if useRoughness else "Gloss"
                                material.roughness_input_type = 2
                                # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.roughness_tex true
                                material.roughness_tex.filename_bitmaptex = bitmap
                                # print(useRoughness, channel, bitmap)
                                # bitmap.output.invert = not useRoughness
                                # material.refr_roughness = 1.0
                                # material.refr_roughness_map = bitmap
                                # if channel == "glossiness" and "roughness" not in textures:
                                #     bitmap.output.invert = True
                        case "specular":
                            if "metal" not in textures:
                                material.specular_tex = rt.RGB_image()
                                material.specular_tex.gamma = 2.2
                                material.specular_tex.name = "Specular"
                                material.specular_input_type = 2
                                # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.specular_tex true
                                material.specular_tex.filename_bitmaptex = bitmap
                                # if useTransformNode do (
                                #     MAT_NODE_NAME.specular_tex.transform = TransformNode
                                # )
                        case "metal":
                            material.metallic_tex = rt.Grayscale_image()
                            material.metallic_tex.gamma = 1.0
                            material.metallic_tex.name = "Metalness"
                            material.metallic_input_type = 2
                            # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.metallic_tex true
                            material.metallic_tex.filename_bitmaptex = bitmap
                            # if useTransformNode do (
                            #     MAT_NODE_NAME.metallic_tex.transform = TransformNode
                            # )
                            material.metalness = 1.0
                            material.metalness_map = bitmap
                        case "normal":
                            material.normal_tex = rt.RGB_image ()
                            material.normal_tex.gamma = 1.0
                            material.normal_tex.name = "Normal"
                            material.normal_input_type = 2
                            material.normal_tex.filename_bitmaptex = bitmap
                            # TODO:: add support for flip_green
                            # material.bump_input = rt.rsBumpMap()
                            # material.bump_input.flipY = True
                            # material.bump_input.input_map = bitmap
                            # material.bump_input.inputType = 1
                            # # normal_map_node.invert_y = flip_green
                            # # material.normal_shader = normal_map_node
                        case "opacity":
                            material.opacity_tex = rt.Grayscale_image()
                            material.opacity_tex.gamma = 1.0
                            material.opacity_tex.name = "Opacity"
                            material.opacity_input_type = 2
                            # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.opacity_tex true
                            material.opacity_tex.filename_bitmaptex = bitmap
                            pass
                            # material.opacity_color_map = bitmap
                            # mod.enable_general_options = True
                            # mod.opaque = False
                        case "emission":
                            pass
                            # material.emission_weight = 1.0
                            # material.emission_color_map = bitmap

                # Transmission and translucency
                transmission = imported_bitmaps.get("transmission", None)
                translucency = imported_bitmaps.get("translucency", None)
                if translucency:
                    material.transmission_tex = rt.RGB_image ()
                    material.transmission_tex.gamma = 2.2
                    material.transmission_tex.name = "Translucency"
                    material.transmission_input_type = 2
                    # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.transmission_tex true
                    material.transmission_tex.filename_bitmaptex = translucency
                elif transmission:
                    material.transmission_tex = rt.Grayscale_image ()
                    material.transmission_tex.gamma = 1.0
                    material.transmission_tex.name = "Transmission"
                    material.transmission_input_type = 2
                    material.transmissionType = 1
                    # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.transmission_tex true
                    material.transmission_tex.filename_bitmaptex = bitmap
                    # if useTransformNode do (
                    #     MAT_NODE_NAME.transmission_tex.transform = TransformNode
                    # )

                # Displacement through geometry modifier
                if displacement_bitmap := imported_bitmaps.get("displacement", None):

                    # if nodecheck == undefined do(
                    # )
                    
                    # material.Displacement = rt.Texture_displacement ()
                    material.displacement.texture_input_type = 2
                    material.displacement.amount = displacement_scale
                    material.displacement.black_level = displacement_bias
                    material.displacement.texture_tex = rt.Greyscale_image ()
                    material.displacement.texture_tex.gamma = 1.0
                    material.displacement.texture_tex.name = "Displacement"
                    # showTextureMap MAT_NODE_NAME MAT_NODE_NAME.displacement.texture_tex true
                    material.displacement.texture_tex.filename_bitmaptex = bitmap
                    # if useTransformNode do (
                    #     MAT_NODE_NAME.displacement.texture_tex.transform = TransformNode
                    # )
                    # mod.displacementScale = displacement_scale
                    # mod.maxDisplacement = 1
                    # disp_node = rt.rsDisplacement()
                    # disp_node.scale = 1
                    # disp_node.texMap_map = displacement_bitmap
                    # disp_node.newrange_min = 0.0
                    # disp_node.newrange_max = 1.0
                    # disp_node.scale = 1
                    # material.displacement_input = disp_node
                    # material.displacement_input_enable = True

                # Sheen/fuzz with reusing the base color
                # if fuzz := imported_bitmaps.get("fuzz", None):
                #     material.sheen_weight_map = fuzz
                #     if albedo := imported_bitmaps.get("albedo"):
                #         material.sheen_color_map = albedo

            elif renderer_id == "vray":

                for channel, bitmap in imported_bitmaps.items():
                    match channel:
                        case "albedo":
                            if "occlusion" in imported_bitmaps:
                                comp = rt.CompositeTexturemap()
                                comp.mapEnabled.count = 2
                                comp.blendMode[2] = 5
                                comp.opacity[2] = 100
                                comp.mapList[1] = bitmap
                                comp.mapList[2] = imported_bitmaps["occlusion"]
                                material.texmap_diffuse = comp
                            else:
                                material.texmap_diffuse = bitmap
                        case "roughness" | "glossiness":
                            if channel == "roughness":
                                material.brdf_useRoughness = True
                                material.texmap_roughness = bitmap
                            elif "roughness" not in imported_bitmaps:
                                material.brdf_useRoughness = True
                                material.texmap_reflectionGlossiness = bitmap
                        # case "specular":
                        #     if "metal" not in textures:
                        #         material.reflectMap = bitmap
                        #         material.reflect = (255, 255, 255)
                        case "metal":
                            material.texmap_metalness = bitmap
                        case "normal":
                            material.texmap_bump = rt.VRayNormalMap()
                            material.texmap_bump.flip_green = flip_green
                            material.texmap_bump.normal_map = bitmap
                        case "opacity":
                            material.texmap_opacity = bitmap # TODO : double sided ?
                        case "emission":
                            material.texmap_self_illumination = bitmap
                            material.selfIllumination = (255, 255, 255)
                        # Sheen/fuzz with reusing the base color
                        case "fuzz":
                            if "albedo" in imported_bitmaps:
                                comp = rt.CompositeTexturemap()
                                comp.mapEnabled.count = 2
                                comp.blendMode[2] = 5
                                comp.opacity[2] = 100
                                comp.mapList[1] = bitmap
                                comp.mapList[2] = imported_bitmaps["albedo"]
                                material.texmap_sheen = comp
                            else:
                                material.texmap_sheen = bitmap

                # Transmission and translucency. For now, we drop any notion of snow/plant... and try to handle those in a straightforward way
                transmission = imported_bitmaps.get("transmission", None)
                translucency = imported_bitmaps.get("translucency", None)
                if translucency:
                    # Do a double sided material with VRay2sided
                    two_sided_material = rt.VRay2SidedMtl()
                    two_sided_material.frontMtl = material
                    two_sided_material.backMtl = material
                    two_sided_material.texmap_translucency = translucency
                    material = two_sided_material
                elif transmission:
                    material.texmap_translucency_amount = transmission
                    if "albedo" in imported_bitmaps:
                        material.translucency_color = imported_bitmaps["albedo"]

                # Handles displacement modifier
                if displacement_bitmap := imported_bitmaps.get("displacement", None):
                    mod = rt.VRayDisplacementMod()
                    mod.texmap = displacement_bitmap
                    mod.amount = displacement_scale
                    mod.shift = displacement_bias
                    mod.keepContinuity = True
                    mod.type = 0

            elif renderer_id == "corona":

                # https://docs.chaos.com/display/CRMAX/Corona+Physical+Material

                for channel, bitmap in imported_bitmaps.items():
                    match channel:
                        case "albedo":
                            if "occlusion" in imported_bitmaps:
                                comp = rt.CompositeTexturemap()
                                comp.mapEnabled.count = 2
                                comp.blendMode[2] = 5
                                comp.opacity[2] = 100
                                comp.mapList[1] = bitmap
                                comp.mapList[2] = imported_bitmaps["occlusion"]
                                material.baseTexmap = comp
                            else:
                                material.baseTexmap = bitmap
                        case "roughness" | "glossiness":
                            if channel == "roughness" or ("roughness" not in imported_bitmaps):
                                material.baseRoughnessTexmap = bitmap
                        case "metal":
                            material.metalnessTexmap = bitmap
                        case "normal":
                            normal_node = rt.CoronaNormal()
                            normal_node.flipgreen = flip_green
                            normal_node.normalMap = bitmap
                            material.baseBumpTexmap = normal_node
                        case "opacity":
                            material.opacityTexmap = bitmap
                            material.opacityCutout = True # TODO : for now, consider everything as cutout
                        case "emission":
                            material.selfIllumTexmap = bitmap
                        case "fuzz":
                            material.sheenAmountTexmap = bitmap
                            if "albedo" in imported_bitmaps:
                                material.sheenColorTexmap = imported_bitmaps["albedo"]
                        case "displacement":
                            material.displacementTexmap = bitmap
                            material.displacementMinimum = displacement_bias - 0.5 * displacement_scale
                            material.displacementMaximum = displacement_bias - 0.5 * displacement_scale

                # Handles displacement modifier, a priori can be done through material
                # if displacement_bitmap := imported_bitmaps.get("displacement", None):
                #     mod = rt.CoronaDisplacementMod()
                #     mod.texmap = displacement_bitmap
                #     mod.levelMin = displacement_bias - 0.5 * displacement_scale
                #     mod.levelMax = displacement_bias - 0.5 * displacement_scale

                # Transmission and translucency.
                # For now, we drop any notion of snow/plant... and try to handle those in a straightforward naive way
                transmission = imported_bitmaps.get("transmission", None)
                translucency = imported_bitmaps.get("translucency", None)
                if translucency:
                    material.translucencyColorTexmap = translucency
                elif transmission:
                    material.sssAmountTexmap = transmission

            else:
                return None, None

            return material, mod

        # TODO: we could do this once, prior to importing payloads to improve situation for batch
        max_version, renderer_id, renderer_version = helpers.get_version_and_renderer_info()
        callback_logger.set_options(renderer=str(renderer_id))
        
        # Import the meshes in the payload
        imported_geometries = []
        try:
            before = set(rt.objects)
            for m in payload.models:
                if Path(m.file).suffix.lower().endswith("fbx"):
                    # For FBX files, we can avoid assets having the same name upon import
                    rt.FBXImporterSetParam("Mode", rt.readvalue(rt.StringStream("#create")))
                    rt.importFile(m.file, rt.name("noPrompt"), using=rt.FBXIMP)
                else:
                    # TODO : other formats are more complicated, will need to check if the issue arises
                    rt.importFile(m.file, rt.name("noPrompt"))
                after = set(rt.objects)
                imported_geometries.append({
                    "material_index": m.material_index,
                    "geometries": list(after - before)
                })
                before = after
        except:
            callback_logger.log("critical", "Error importing assets, check 3ds Max console")
            print(traceback.format_exc())
            return 

        imported_materials = []
        if not has_usd:
            if renderer_id in ["arnold", "corona", "octane", "redshift", "vray"]:
                # Create materials
                try:
                    for m in payload.materials:
                        (material, mod) = create_material(m.textures, renderer_id, m.name if m.name else payload.root_name, m.flipnmapgreenchannel)
                        imported_materials.append((material, mod))
                except:
                    callback_logger.log("warning", "Error importing materials, check 3DS Max console")
                    print(traceback.format_exc())
                # Assign materials
                try:
                    for m in imported_geometries:
                        if ((material_index := m["material_index"]) != -1) and (material_index < len(imported_materials)):
                            (material, mod) = imported_materials[material_index]
                            if (material is None) and (mod is None):
                                print("Error: created material and geometry modifier are both None, this should not have happened")
                            for geometry in m.get("geometries"):
                                if material:
                                    geometry.material = material
                                if mod:
                                    rt.addModifier(geometry, mod)
                except:
                    callback_logger.log("warning", "Error assign materials to geometries, check 3DS Max console")
                    print(traceback.format_exc())
            elif len(payload.materials) > 0:
                callback_logger.log("warning", "Only Arnold, Octane, Redshift and V-Ray are currently supported. Materials won't be imported.")

        # Import of native files
        if len(payload.native_files):
            before = set(rt.objects)
            for f in payload.native_files:
                max_file = Path(f)
                if max_file.suffix.lower() in [".chr", ".max"]:
                    merged = rt.mergeMAXFile(str(max_file), rt.Name("autoRenameDups"), rt.Name("select"))
                    if not merged:
                        print("Encountered an issue merging .max file")
            after = set(rt.objects)
            imported_geometries.append(list(after - before))

        # Reparenting / renaming operations
        try:
            new_objects = [o for o in list(rt.objects) if o not in existing_objects]
            top_parents = []
            try:
                for new_object in new_objects:
                    parent = new_object
                    while parent.parent:
                        parent = parent.parent
                    top_parents.append(parent)
                top_parents = list(set(top_parents))
            except:
                print("Failed fetching objects to improve the hierarchy, this should not happen but should not have further consequences")
                print(traceback.format_exc())
                top_parents = []
            try:
                if len(top_parents) == 1:
                    # if there is one and it is an empty node, rename it
                    top_parents[0].name = helpers.generate_unique_name(payload.root_name, rt.objects)
                elif len(top_parents) > 1:
                    # Multiple parents, we create a new empty object
                    new_root = rt.Dummy()
                    new_root.name = helpers.generate_unique_name(payload.root_name, rt.objects)
                    for obj in top_parents:
                        obj.parent = new_root
            except:
                print("Failed reparenting assets, this should not have happened, but should not impact import negatively")
                print(traceback.format_exc())
        except:
            print("Fab: Issue encountered during reparenting, this should not have an effect on the import")
            print(traceback.format_exc())
        
        if len(imported_geometries) == 0 and len(imported_materials) == 0 and len(payload.native_files) == 0:
            callback_logger.log("critical", "No model nor material imported")
        else:
            if len(payload.native_files) and len(imported_geometries) == 0:
                # In the case of native files, we might have no new objects, which would be an issue
                callback_logger.log("critical", "Nothing imported from 3ds max files")
            else:
                callback_logger.log("success", "Finished importing models")
    
    def __init__(self, payload: fabplugins.Payload):

        self.assetData = None
        self.payload = payload
        
        # Interpret Quixel-specific metadata
        Q = payload.metadata.quixel_filtered
        self.is_quixel           = payload.metadata.is_quixel
        prefer_specular_workflow = Q.get("prefer_specular_workflow", False)
        is_high_poly =             Q.get("is_high_poly", False)
        is_metal =                 Q.get("is_metal", False)
        is_snow =                  Q.get("is_snow", False)
        is_fruit =                 Q.get("is_fruit", False)
        is_fabric =                Q.get("is_fabric", False)
        is_scatter =               Q.get("is_scatter", False)
        is_custom =                Q.get("is_custom", False)
        is_sss =                   Q.get("is_sss", False)
        is_plant =                 Q.get("is_plant", False)
        is_colorless =             Q.get("is_colorless", False)
        can_have_displacement =    Q.get("displacement", True)

        # We can directly parse those from the payload data
        self.isSpecularWorkflow = prefer_specular_workflow
        self.useDisplacement = can_have_displacement
        self.isScatterAsset = is_scatter
        self.isCustom = is_custom
        self.isSurfaceSSS = is_sss
        self.isSnow = is_snow
        self.isFruit = is_fruit
        self.isFabric = is_fabric
        self.isMetal = is_metal
        self.isBareMetal = is_colorless and is_metal
        self.isHighPoly = is_high_poly
        self.ID = payload.id
        
        self.Type = payload.metadata.type
        self.isPlant = is_plant
        self.has_alembic = any([Path(m.file).suffix.lower() == ".abc" for m in payload.models])
        self.has_obj = any([Path(m.file).suffix.lower() == ".obj" for m in payload.models])

        apply_material_to_selection = (len(payload.models) == 0) and (len(payload.materials) == 1) and (self.Type == "material")

        # Process texture channels
        # TODO: Only supports one material for now, as that's how the Bridge plugin was designed
        textures = {}
        if len(payload.materials) > 1:
            print("FAB: Multiple material payloads received, only the first one will be processed")
        if len(payload.materials) != 0:
            material_payload = payload.materials[0]
            for channel_type, channel in material_payload.textures.items():
                texture_file = Path(channel)
                if channel_type == "displacement":
                    exr_alternative = texture_file.with_suffix(".exr")
                    if exr_alternative.exists():
                        print("Using .exr texture for displacement channel")
                        texture_file = exr_alternative
                textures[channel_type.lower()] = texture_file
        

        # Setup name and material name
        # TODO: Not ideal
        self.Name = payload.root_name
        self.materialName = self.Name

        self.scanWidth = 1
        self.scanHeight = 1
        self.height = "1"
        self.meta = None
        try:
            if meta := payload.metadata.quixel_json.get("meta", {}):
                self.meta = meta
                self.scanWidth = helpers.GetScanWidth(self.meta)
                self.scanHeight = helpers.GetScanHeight(self.meta)
                height_ = [item for item in self.meta if item["key"].lower() == "height"]
                if len(height_) >= 1:
                    self.height = str( height_[0]["value"].replace('m','') )
                    # Converting inches to meters
                    # dividing by 2 to use half as max and half as minimum
                    # managing displacement value according to the scan area
                    self.height = float(self.height) * (39.37 /2 * (self.scanWidth/2.1))
                    if(self.Type == "3d-model"):
                        self.height = 0.005 * 39.37 
        except:
            pass

        self.assetData = RendererData(textures, self.Type, self.materialName, self.useDisplacement, self.isMetal, self.isBareMetal, self.isFruit, self.isSnow, apply_material_to_selection, self.isSpecularWorkflow, self.scanWidth, self.scanHeight, self.meta)

class RendererData():
    def __init__(self, textures, assetType, materialName, useDisplacement, isMetal, isBareMetal, isFruit, isSnow, applyToSel, isSpecular, width, height, meta):
        self.textures = textures
        self.assetType = assetType
        self.materialName = materialName
        self.useDisplacement = useDisplacement
        self.isMetal = isMetal
        self.isBareMetal = isBareMetal
        self.isFruit = isFruit
        self.isSnow = isSnow
        self.applyToSel = applyToSel
        self.isSpecular = isSpecular
        self.width = width
        self.height = height
        self.meta = meta
