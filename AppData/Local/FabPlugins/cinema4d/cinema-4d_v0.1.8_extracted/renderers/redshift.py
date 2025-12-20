import helpers
import c4d, maxon
import maxon.frameworks.nodespace
from pathlib import Path

def get_input(node, id):
    return node.GetInputs().FindChild(id)

def get_output(node, id):
    return node.GetOutputs().FindChild(id)

def setup_texture(graph, channel_type, texture_path, connect_output_to, srgb=False, use_r=False):

    ID_TexSampler = "com.redshift3d.redshift4c4d.nodes.core.texturesampler"
    ID_ColorSplitter = f"com.redshift3d.redshift4c4d.nodes.core.rscolorsplitter"

    # Create a named texture node
    node = graph.AddChild(maxon.Id(), maxon.Id(ID_TexSampler))
    node.SetValue(maxon.NODE.BASE.NAME, maxon.String(f"{channel_type.capitalize()} Map"))
    # Connect the texture path to the input
    in_path = get_input(node, ID_TexSampler + ".tex0").FindChild("path")
    in_path.SetPortValue(texture_path)
    # Setup the colorspace
    in_colorspace = get_input(node, ID_TexSampler + ".tex0").FindChild("colorspace")
    in_colorspace.SetPortValue("RS_INPUT_COLORSPACE_SRGB" if srgb else "RS_INPUT_COLORSPACE_RAW")
    
    # Connect its output where needed
    out_color = get_output(node, ID_TexSampler + ".outcolor")
    if use_r:
        node_splitter = graph.AddChild(maxon.Id(), maxon.Id(ID_ColorSplitter))
        out_color.Connect(get_input(node_splitter, ID_ColorSplitter+".input"))
        get_output(node_splitter, ID_ColorSplitter+".outr").Connect(connect_output_to)
    else:
        out_color.Connect(connect_output_to)

    return node, in_path, out_color

def redshift_material(textures, matName, isMetal, is_snow):

    # Create the material node and gather its inputs/outputs
    try:
        doc = c4d.documents.GetActiveDocument()
        c4d.CallCommand(1036759, 1000)
        mat = c4d.BaseMaterial(c4d.Mmaterial)
        mat.SetName(matName)

        redshift_nodespace_id = maxon.NodeSpaceIdentifiers.RedshiftMaterial
        node_material = mat.GetNodeMaterialReference()
        graph = node_material.CreateEmptyGraph(redshift_nodespace_id)
        
        doc.InsertMaterial(mat)
        c4d.EventAdd()

        # ID retrieval
        root_id = "com.redshift3d.redshift4c4d"
        ID_RSStandardMat = f"{root_id}.nodes.core.standardmaterial"
        ID_Output = f"{root_id}.node.output"
        ID_TexSampler = f"{root_id}.nodes.core.texturesampler"
        ID_BumpNode = f"{root_id}.nodes.core.bumpmap"
        ID_DispNode = f"{root_id}.nodes.core.displacement"
        ID_ColorInvert = f"{root_id}.nodes.core.rsmathinvcolor"
        ID_Multiply = f"{root_id}.nodes.core.rsmathmul"
        ID_BumpInputType = f"{root_id}.nodes.core.bumpmap.inputtype"
        ID_DisplacementSpaceType = f"{root_id}.nodes.core.displacement.space_type"
        
        # Set some graph specific options and get inputs/outpus
        with graph.BeginTransaction() as transaction:

            # Create the standard mat node
            RSStandardMat = graph.AddChild(maxon.Id(), maxon.Id(ID_RSStandardMat))

            # Gather inputs
            def get_material_input(suffix):
                return RSStandardMat.GetInputs().FindChild(f"{ID_RSStandardMat}{suffix}")
            IN_RSStandardMat_baseClr = get_material_input(".base_color")
            IN_RSStandardMat_mtlnss = get_material_input(".metalness")
            IN_RSStandardMat_reflRough = get_material_input(".refl_roughness")
            IN_RSStandardMat_reflWeight = get_material_input(".refl_weight")
            IN_RSStandardMat_reflIOR = get_material_input(".refl_ior")
            IN_RSStandardMat_bmpInput = get_material_input(".bump_input")
            IN_RSStandardMat_SSClr = get_material_input(".ms_color")
            IN_RSStandardMat_SSWeight = get_material_input(".ms_amount")
            IN_RSStandardMat_SSMode = get_material_input(".ms_mode")
            IN_RSStandardMat_SSRadius = get_material_input(".ms_radius")
            IN_RSStandardMat_SSScale = get_material_input(".ms_radius_scale")
            IN_RSStandardMat_transWeight = get_material_input(".refr_weight")
            IN_RSStandardMat_Opacity = get_material_input(".opacity_color")  
            IN_RSStandardMat_GeoThinWall = get_material_input(".refr_thin_walled")

            IN_RSStandardMat_reflIOR.SetPortValue(1.5)
            if "metal" not in textures:
                IN_RSStandardMat_mtlnss.SetPortValue(1) if isMetal else IN_RSStandardMat_mtlnss.SetPortValue(0)
            
            # Output node and connections
            Output = graph.AddChild(maxon.Id(), maxon.Id(ID_Output))
            IN_Output_Srfc = Output.GetInputs().FindChild(ID_Output + ".surface")
            IN_Output_disp = Output.GetInputs().FindChild(ID_Output + ".displacement")
            
            # Connect the material to the output
            OUT_RSStandardMat_outClr = RSStandardMat.GetOutputs().FindChild(ID_RSStandardMat + ".outcolor")
            OUT_RSStandardMat_outClr.Connect(IN_Output_Srfc)
            
            transaction.Commit()

    except Exception as e:
        helpers.handle_exception(e, "Failed to create redshift material")
        return None

    # Create other nodes, link textures...
    try:
        with graph.BeginTransaction() as transaction:
            for channel_type, texture_path in textures.items():
                extension = Path(texture_path).suffix.lower()
                if channel_type == "albedo":
                    # exr should not be set as srgb
                    node_albedo, _, output_albedo = setup_texture(graph, channel_type, texture_path, IN_RSStandardMat_baseClr, srgb = extension!=".exr")
                    if ao_texture_path := textures.get("ao"):
                        setup_texture(graph, "ao", ao_texture_path, get_input(node_albedo, ID_TexSampler + ".color_multiplier"), srgb = False, use_r=True)
                    # Use the base color for SSS color in case there is a transmission map
                    if (not is_snow) and ("transmission" in textures):
                        output_albedo.Connect(IN_RSStandardMat_SSClr)
                elif channel_type == "glossiness" and "roughness" not in textures:
                    # Connect the output of gloss to an invert node
                    node_invert = graph.AddChild(maxon.Id(), maxon.Id(ID_ColorInvert))
                    in_invert, out_invert = get_input(node_invert, ID_ColorInvert + ".input"), get_output(node_invert, ID_ColorInvert + ".outcolor")
                    setup_texture(graph, channel_type, texture_path, in_invert, srgb = False, use_r=True)
                    out_invert.Connect(IN_RSStandardMat_reflRough)
                elif channel_type == "roughness":
                    # Should only use R maybe
                    setup_texture(graph, channel_type, texture_path, IN_RSStandardMat_reflRough, srgb = False, use_r=True)
                elif channel_type == "metal":
                    setup_texture(graph, channel_type, texture_path, IN_RSStandardMat_mtlnss, srgb = False, use_r=True)
                elif channel_type == "specular":
                    setup_texture(graph, channel_type, texture_path, IN_RSStandardMat_reflWeight, srgb = False, use_r=True)
                elif channel_type == "normal":
                    # Connect the output of the normal to a bump node
                    node_bump = graph.AddChild(maxon.Id(), maxon.Id(ID_BumpNode))
                    get_input(node_bump, ID_BumpInputType).SetPortValue(1)
                    get_output(node_bump, ID_BumpNode + ".out").Connect(IN_RSStandardMat_bmpInput)
                    setup_texture(graph, channel_type, texture_path, get_input(node_bump, ID_BumpNode + ".input"), srgb = False)
                elif channel_type == "opacity":
                    # TODO: we might have issues with R channel vs b/w
                    setup_texture(graph, channel_type, texture_path, IN_RSStandardMat_Opacity, srgb = False, use_r=True)
                elif channel_type == "displacement":
                    # TODO: previously, displacement was not explicitely set to raw for exr, probably a compatible default ?
                    # Connect the displacement to a displacement map node
                    node_displacement_map = graph.AddChild(maxon.Id(), maxon.Id(ID_DispNode))
                    get_input(node_displacement_map, ID_DisplacementSpaceType).SetPortValue(2)
                    setup_texture(graph, channel_type, texture_path, get_input(node_displacement_map, ID_DispNode + ".texmap"), srgb = False, use_r=True)
                    get_output(node_displacement_map, ID_DispNode + ".out").Connect(IN_Output_disp)
            
            # Handle translucency/transmission separately
            translucency_texture = textures.get("translucency")
            transmission_texture = textures.get("transmission")
            if translucency_texture or transmission_texture:
                if is_snow:
                    # Connect a multiply node to the material trans weight
                    node_multiply = graph.AddChild(maxon.Id(), maxon.Id(ID_Multiply))
                    get_input(node_multiply, ID_Multiply + ".input2").SetPortValue(0.25)
                    get_output(node_multiply, ID_Multiply + ".out").Connect(IN_RSStandardMat_transWeight)
                    # Connect the map to the first multiply node input
                    connect_to = get_input(node_multiply, ID_Multiply + ".input1")
                    if translucency_texture:
                        _, _, texture_output = setup_texture(graph, "translucency", translucency_texture, connect_to, srgb = True)
                    else:
                        _, _, texture_output = setup_texture(graph, "transmission", transmission_texture, connect_to, srgb = False, use_r=True)
                    ## Adjusting some SS properties
                    IN_RSStandardMat_SSClr.SetPortValue(maxon.Vector(1,1,1))
                    IN_RSStandardMat_SSMode.SetPortValue(2)
                    IN_RSStandardMat_SSRadius.SetPortValue(maxon.Vector(0.4,0.5,0.6))
                    IN_RSStandardMat_SSScale.SetPortValue(0.1)
                    # Also connect the texture output to subsurface weight
                    texture_output.Connect(IN_RSStandardMat_SSWeight)
                else:
                    if translucency_texture:
                        # Could potentially do the same for the snow case
                        setup_texture(graph, "translucency", translucency_texture, IN_RSStandardMat_SSClr, srgb = True)
                        IN_RSStandardMat_SSWeight.SetPortValue(0.5)
                        IN_RSStandardMat_GeoThinWall.SetPortValue(1)
                    else:
                        # TODO: We connect to IN_RSStandardMat_SSWeight instead of transmission, as transmission matches refraction
                        setup_texture(graph, "transmission", transmission_texture, IN_RSStandardMat_SSWeight, srgb = False, use_r=True)
                        # An additional setup was done when treating the albedo case: linking albedo to sss color
                        IN_RSStandardMat_SSScale.SetPortValue(0.1)
            mat.Update(True, True)
            transaction.Commit()

        return mat
    except Exception as e:
        helpers.handle_exception(e, "Failed to setup the redshift material")
        return None
