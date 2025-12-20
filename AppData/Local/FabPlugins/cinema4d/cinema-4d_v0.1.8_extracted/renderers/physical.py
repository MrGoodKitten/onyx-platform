import c4d

import helpers

def physical_material(textures, matName, isMetal, has_geometry, is_snow, asset_type):
    try:
        mat = c4d.Material()
    except Exception as e:
        helpers.handle_exception(e, "Failed to create physical material")
        return None

    mat.SetName(matName)

    mat.RemoveReflectionLayerIndex(0) #Remove default specular layer
    mat.AddReflectionLayer() # Add lambertian diffuse layer
    mat.AddReflectionLayer() # Add GGX layer
    
    mat[c4d.MATERIAL_USE_NORMAL] = True
    # TODO: isMetal usage should be standardized more
    mat[c4d.MATERIAL_USE_COLOR] = not (isMetal and (asset_type == "material"))    

    # Setting layers types to lambertian and GGX
    color_layer = mat.GetReflectionLayerIndex(1)
    color_layer.SetName("Base Color")
    cID = color_layer.GetDataID()

    refl_layer = mat.GetReflectionLayerIndex(0) # Get metal/non-metal layer reference
    refl_layer.SetName("Metal" if isMetal else "Non-Metal")
    rID = refl_layer.GetDataID()

    mat[cID + c4d.REFLECTION_LAYER_MAIN_DISTRIBUTION] = 7 
    mat[cID + c4d.REFLECTION_LAYER_MAIN_VALUE_SPECULAR] = 0 # set Specular strength
    mat[cID + c4d.REFLECTION_LAYER_MAIN_VALUE_BUMP_MODE] = 2 # Set Bump strength mode

    mat[rID + c4d.REFLECTION_LAYER_MAIN_DISTRIBUTION] = 3
    mat[rID + c4d.REFLECTION_LAYER_MAIN_VALUE_SPECULAR] = 0.5 # set Specular strength
    mat[rID + c4d.REFLECTION_LAYER_MAIN_VALUE_ROUGHNESS] = 1 # 100% roughness

    # Set layer Fresnel properties according to type.
    if isMetal:
        if asset_type == "material":
            mat[rID + c4d.REFLECTION_LAYER_MAIN_VALUE_ROUGHNESS] = 0.75 # 75% roughness
            mat[rID + c4d.REFLECTION_LAYER_MAIN_VALUE_SPECULAR] = 1 # 100% specular strength
            mat[rID + c4d.REFLECTION_LAYER_FRESNEL_MODE] = 2 #conductor
            mat[rID + c4d.REFLECTION_LAYER_FRESNEL_VALUE_ETA] = 1.52 #IOR
            mat[rID + c4d.REFLECTION_LAYER_FRESNEL_OPAQUE] = True # Opaque
        else:
            mat[refl_layer.GetDataID() + c4d.REFLECTION_LAYER_MAIN_VALUE_SPECULAR] = 0.5 # 50% specular strength
            mat[rID + c4d.REFLECTION_LAYER_FRESNEL_MODE] = 1 #dielectric
            mat[rID + c4d.REFLECTION_LAYER_FRESNEL_VALUE_IOR] = 1.52 #IOR
    else:
        mat[rID + c4d.REFLECTION_LAYER_FRESNEL_MODE] = 1 #dielectric
        mat[rID + c4d.REFLECTION_LAYER_FRESNEL_VALUE_IOR] = 1.52 #IOR
    
    try:
        for channel_type, texture_path in textures.items():
            name = channel_type.capitalize()
            if channel_type == "albedo":
                create_bitmap_shader(mat, texture_path, name, cID + c4d.REFLECTION_LAYER_COLOR_TEXTURE, "srgb")
                if isMetal and asset_type == "material":
                    create_bitmap_shader(mat, texture_path, name, rID + c4d.REFLECTION_LAYER_COLOR_TEXTURE, "srgb")
                else:
                    create_bitmap_shader(mat, texture_path, name, c4d.MATERIAL_COLOR_SHADER, "srgb")
            elif channel_type == "metal":
                create_bitmap_shader(mat, texture_path, name, rID + c4d.REFLECTION_LAYER_TRANS_TEXTURE, "linear", not isMetal)
            elif channel_type == "roughness":
                create_bitmap_shader(mat, texture_path, name, rID + c4d.REFLECTION_LAYER_MAIN_SHADER_ROUGHNESS, "linear")
            elif channel_type == "glossiness" and "roughness" not in textures:
                create_bitmap_shader(mat, texture_path, name, rID + c4d.REFLECTION_LAYER_MAIN_SHADER_ROUGHNESS, "linear", True)
            elif channel_type == "normal":
                create_bitmap_shader(mat, texture_path, name, c4d.MATERIAL_NORMAL_SHADER, "linear")
                create_bitmap_shader(mat, texture_path, name, rID + c4d.REFLECTION_LAYER_MAIN_SHADER_BUMP_CUSTOM, "linear")
            elif channel_type == "displacement" and (asset_type.lower() not in ["3d", "3dplant"]): # TODO: do not use displacement for models ?
                mat[c4d.MATERIAL_USE_DISPLACEMENT] = True
                create_bitmap_shader(mat, texture_path, name, c4d.MATERIAL_DISPLACEMENT_SHADER, "linear")
                mat[c4d.MATERIAL_DISPLACEMENT_HEIGHT] = 1 if has_geometry else 10
                mat[c4d.MATERIAL_DISPLACEMENT_SUBPOLY] = True
            elif channel_type == "opacity":
                mat[c4d.MATERIAL_USE_ALPHA] = True
                create_bitmap_shader(mat, texture_path, name, c4d.MATERIAL_ALPHA_SHADER, "linear")
            elif channel_type == "translucency":
                mat[c4d.MATERIAL_USE_LUMINANCE] = True
                sssShader = create_sss_shader(mat, c4d.MATERIAL_LUMINANCE_SHADER)
                create_bitmap_shader(sssShader, texture_path, name, c4d.XMBSUBSURFACESHADER_SHADER, "srgb")
        
        # Specific handling for Quixel snow assets
        translucency_texture = textures.get("translucency")
        transmission_texture = textures.get("transmission")
        if translucency_texture or transmission_texture:
            mat[c4d.MATERIAL_USE_LUMINANCE] = True
            sss_strength = 1 if is_snow else 0.5
            sss_length = 0.5 if is_snow else 0.1
            sssShader = create_sss_shader(mat, c4d.MATERIAL_LUMINANCE_SHADER, c4d.Vector(1,1,1), sss_strength, sss_length, is_snow)
            create_bitmap_shader(
                sssShader, 
                translucency_texture if translucency_texture else transmission_texture, 
                "Translucency" if translucency_texture else "Transmission", 
                c4d.XMBSUBSURFACESHADER_SHADER,
                "srgb",
                False,
                is_snow
            )

    except Exception as e:
        helpers.handle_exception(e, "Failed to import textures")
        return None

    # Only available after R23
    mat[c4d.MATERIAL_DISPLAY_USE_LUMINANCE] = False

    mat.Message(c4d.MSG_UPDATE)
    mat.Update(True, True)
    doc = c4d.documents.GetActiveDocument()
    doc.InsertMaterial(mat)
    return mat

# Create a bitmap shader to load a texture
def create_bitmap_shader(mat, texPath, name, link_name, colorspace, invert = False, is_snow = False):
    shader = c4d.BaseList2D(c4d.Xbitmap)
    shader[c4d.BITMAPSHADER_FILENAME] = texPath
    if invert:
        shader[c4d.BITMAPSHADER_BLACKPOINT] = 1
        shader[c4d.BITMAPSHADER_WHITEPOINT] = 0
    if is_snow: # TODO: might conflict with invert
        shader[c4d.BITMAPSHADER_BLACKPOINT] = 1
        shader[c4d.BITMAPSHADER_WHITEPOINT] = 0
    shader[c4d.BITMAPSHADER_COLORPROFILE] = 1 if colorspace == "linear" else 2
    shader.SetName(name)
    mat[link_name] = shader
    mat.InsertShader(shader)
    return shader

# Create a sss shader
def create_sss_shader(mat, link_name, sss_color, strength, length, snow = False):
    shader = c4d.BaseList2D(1025614)
    shader[c4d.XMBSUBSURFACESHADER_DIFFUSE] = sss_color
    shader[c4d.XMBSUBSURFACESHADER_STRENGTH] = strength
    shader[c4d.XMBSUBSURFACESHADER_LENGTH] = length  
    if snow:
        shader[c4d.XMBSUBSURFACESHADER_LENGTH_R] = 1.02
        shader[c4d.XMBSUBSURFACESHADER_LENGTH_G] = 1.275
        shader[c4d.XMBSUBSURFACESHADER_LENGTH_B] = 1.53
    mat[link_name] = shader
    mat.InsertShader(shader)
    return shader
