import c4d
import helpers

def create_arnold_shader(mat, ID, x, y, name = None, filename = None, clrspace = None):
    msg = c4d.BaseContainer()
    msg.SetInt32(1000, 1029)
    msg.SetInt32(2001, 1033990)
    msg.SetInt32(2002, ID)
    msg.SetInt32(2003, x)
    msg.SetInt32(2004, y)
    mat.Message(c4d.MSG_BASECONTAINER, msg)
    node = msg.GetLink(2011)
    if name:
        node.SetName(name)
    if filename:
        node.GetOpContainerInstance().SetFilename(1737748425, filename)
    if clrspace:
        node.GetOpContainerInstance().SetString(868305056, clrspace)
    return node

def arnold_set_base_shader(mat, shader, rootPortId):
    msg = c4d.BaseContainer()
    msg.SetInt32(1000, 1033)
    msg.SetLink(2001, shader)
    msg.SetInt32(2002, 0)
    msg.SetInt32(2003, rootPortId)
    mat.Message(c4d.MSG_BASECONTAINER, msg)
    return msg.GetBool(2011)

def arnold_mat_connection(mat, srcNode, dstNode, dstPortId):
    msg = c4d.BaseContainer()
    msg.SetInt32(1000, 1031)
    msg.SetLink(2001, srcNode)
    msg.SetInt32(2002, 0)
    msg.SetLink(2003, dstNode)
    msg.SetInt32(2004, dstPortId)
    mat.Message(c4d.MSG_BASECONTAINER, msg)
    return msg.GetBool(2011)

def arnold_material(textures, matName, isMetal):
    doc = c4d.documents.GetActiveDocument()
    try:
        mat = c4d.BaseMaterial(1033991)
    except Exception as e:
        helpers.handle_exception(e, "Failed to create Arnold material")
        return False
    if mat is None:
        return False
    
    mat.SetName(matName)
    doc.InsertMaterial(mat)

    # Create master node and set it's properties.
    standard = create_arnold_shader(mat, 314733630, 500, 100, matName)
    arnold_set_base_shader(mat, standard, 537905099) # Connect to Arnold beauty output.
    arnold_set_base_shader(mat, standard, 537906863) # Connect to Arnold  viewport.
    standard.SetName(matName)
    standard.GetOpContainerInstance().SetString(1630484996, "custom")
    standard.GetOpContainerInstance().SetFloat(1182964519, 1) # Base: Weight
    standard.GetOpContainerInstance().SetFloat(1876347704, 0) # Specular Roughness Value
    standard.GetOpContainerInstance().SetFloat(1046994997, 0) # Specular Weight Value
    standard.GetOpContainerInstance().SetFloat(220096084, 1.52) # Specular IOR
    standard.GetOpContainerInstance().SetFloat(1875191464, 1 if isMetal else 0) # Metalness value

    try:
        for channel_type, texture_path in textures.items():
            if channel_type == "albedo":
                albedo_node = create_arnold_shader(mat, 262700200, 0, 50, "Albedo", texture_path, "sRGB")
                arnold_mat_connection(mat, albedo_node, standard, 1044225467)
                if ao_texture_path := textures.get("ao", None):
                    ao_node = create_arnold_shader(mat, 262700200, -250, 50, "AO", ao_texture_path, "linear")
                    arnold_mat_connection(mat, ao_node, albedo_node, 1426019114) #Multiply with Albedo
            elif channel_type == "metal" :
                metalness_node = create_arnold_shader(mat, 262700200, 0, 150, "Metalness", texture_path, "linear")
                arnold_mat_connection(mat, metalness_node, standard, 1875191464)
            elif channel_type == "normal":
                normal_node = create_arnold_shader(mat, 262700200, 0, 200, "Normal Map", texture_path, "linear")
                arnold_normal_node = create_arnold_shader(mat, 1512478027, 250, 200, "Arnold Normal Node")
                arnold_mat_connection(mat, normal_node, arnold_normal_node, 2075543287)
                arnold_mat_connection(mat, arnold_normal_node, standard, 244376085)
            elif channel_type == "glossiness" and "roughness" not in textures:
                gloss_node = create_arnold_shader(mat, 262700200, 0, 100, "Gloss", texture_path, "linear")
                gloss_cc_node = create_arnold_shader(mat, 1211336267, 250, 100, "Invert Gloss")
                gloss_cc_node.GetOpContainerInstance().SetBool(1952672187, True)
                gloss_cc_node.GetOpContainerInstance().SetFloat(1582985598, 0) # Exposure
                arnold_mat_connection(mat, gloss_node, gloss_cc_node, 2023242509)
                arnold_mat_connection(mat, gloss_cc_node, standard, 2099493681)
            elif channel_type == "roughness":
                roughness_node = create_arnold_shader(mat, 262700200, 0, 100, "Roughness", texture_path, "linear")
                arnold_mat_connection(mat, roughness_node, standard, 2099493681)
            elif channel_type == "displacement":
                disp_node = create_arnold_shader(mat, 262700200, 400, 350, "Displacement", texture_path, "linear")
                arnold_nrm_disp_node = create_arnold_shader(mat, 1270483482, 630, 300)
                arnold_nrm_disp_node.GetOpContainerInstance().SetInt32(748850620, 1) # Displacement scale.
                arnold_nrm_disp_node.GetOpContainerInstance().SetFloat(1762879056, 0.5) # Displacement scalar zero value.
                arnold_mat_connection(mat, disp_node, arnold_nrm_disp_node, 276937581)
                arnold_set_base_shader(mat, arnold_nrm_disp_node, 537905100)
            elif channel_type == "opacity":
                opacity_node = create_arnold_shader(mat, 262700200, 0, 250, "Opacity", texture_path, "linear")
                arnold_mat_connection(mat, opacity_node, standard, 784568645)
            elif channel_type == "translucency":
                standard.GetOpContainerInstance().SetFloat(639969601, 0.1)
                standard.GetOpContainerInstance().SetFloat(657869786, 0.4)
                standard.GetOpContainerInstance().SetFloat(110275456, 1)
                standard.GetOpContainerInstance().SetVector(276268506, c4d.Vector(1,1,1))
                translucency_node = create_arnold_shader(mat, 262700200, 0, 300, "Translucency (SSS)", texture_path, "sRGB")
                arnold_mat_connection(mat, translucency_node, standard, 676401187)
            elif channel_type == "transmission":
                transmission_node = create_arnold_shader(mat, 262700200, 0, 350, "Transmission", texture_path, "linear")
                arnold_mat_connection(mat, transmission_node, standard, 1053345482)

    except Exception as e:
        helpers.handle_exception(e, "Failed to import textures for Arnold")
        return None

    mat.Update(True, True)
    return mat
