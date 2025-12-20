import os
import c4d
import helpers

class OctaneSetup():
    def __init__(self, textures, assetType, hasGeomtry, matName, isSpecularWorkflow, isMetal):
        self.mat = None
        self.connectToTransformNode = False
        self.textures = textures
        self.hasGeometry = hasGeomtry
        self.isSpecularWorkflow = isSpecularWorkflow
        self.doc = c4d.documents.GetActiveDocument()
        self.isMetal = isMetal
        self.assetType = assetType
        self.matName = matName

    def CreateMaterial(self):
        try:
            self.CreateMasterMaterialNode()
            self.SetupTextures()
            self.mat.Update(True, True)
            self.doc.InsertMaterial(self.mat)
            return self.mat
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
            return None

    def CreateMasterMaterialNode(self):
        try:
            self.mat = c4d.BaseMaterial(1029501)
            self.mat[c4d.OCT_MATERIAL_TYPE] = 2516
            self.mat.SetName(self.matName)
            self.mat.Update(True, True)
            self.doc.InsertMaterial(self.mat)

            if self.isMetal:
                self.mat[c4d.OCT_MATERIAL_INDEX] = 8
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
        
        # Set BRDF model to GGX, this wasn't avaliable in older Octane versions
        try:
            self.mat[c4d.OCT_MAT_BRDF_MODEL] = 2
        except:
            pass

    def SetupTextures(self):
        try:
            if self.assetType.lower() not in ["3d","3dplant"]:
                self.CreateTransformNode()

            if "albedo" in self.textures:
                albedoNode = self.CreateImageTextureNode("albedo", "Albedo", 0, 2.2)
                if albedoNode:
                    ccAlbedoNode = self.CreateCCNode(albedoNode)
                    if "ao" in self.textures and not self.isMetal:
                        aoNode = self.CreateImageTextureNode("ao", "AO")
                        if aoNode:
                            self.CreateMultiplyNode(ccAlbedoNode, aoNode, c4d.OCT_MATERIAL_DIFFUSE_LINK)
                    else:
                        self.mat[c4d.OCT_MATERIAL_DIFFUSE_LINK] = ccAlbedoNode
            
            if self.isSpecularWorkflow:
                if "specular" in self.textures:
                    self.CreateImageTextureNode("specular", "Specular", 0, 2.2, False, c4d.OCT_MATERIAL_SPECULAR_LINK)
                
                if "glossiness" in self.textures:
                    glossNode = self.CreateImageTextureNode("glossiness", "Gloss", 1, 1, True)
                    if glossNode:
                        ccGlossNode = self.CreateCCNode(glossNode)
                        self.mat[c4d.OCT_MATERIAL_ROUGHNESS_LINK] = ccGlossNode
                elif "roughness" in self.textures:
                    roughnessNode = self.CreateImageTextureNode("roughness", "Roughness")
                    if roughnessNode:
                        ccRoughnessNode = self.CreateCCNode(roughnessNode)
                        self.mat[c4d.OCT_MATERIAL_ROUGHNESS_LINK] = ccRoughnessNode
            else:
                if "metal" in self.textures:
                    self.CreateImageTextureNode("metal", "Metalness", 1, 1, False, c4d.OCT_MAT_SPECULAR_MAP_LINK)
                if "roughness" in self.textures:
                    roughnessNode = self.CreateImageTextureNode("roughness", "Roughness")
                    if roughnessNode:
                        ccRoughnessNode = self.CreateCCNode(roughnessNode)
                        self.mat[c4d.OCT_MATERIAL_ROUGHNESS_LINK] = ccRoughnessNode

                elif "glossiness" in self.textures:
                    glossNode = self.CreateImageTextureNode("glossiness", "Gloss", 1, 1, True)
                    if glossNode:
                        ccGlossNode = self.CreateCCNode(glossNode)
                        self.mat[c4d.OCT_MATERIAL_ROUGHNESS_LINK] = ccGlossNode
                
            if "bump" in self.textures:  
                self.CreateImageTextureNode("bump", "Bump", 1, 1, False, c4d.OCT_MATERIAL_BUMP_LINK)

            if "normal" in self.textures:  
                self.CreateImageTextureNode("normal", "Normal", 0, 1, False, c4d.OCT_MATERIAL_NORMAL_LINK)
            
            if "displacement" in self.textures:
                displacementNode = self.CreateDisplacementNode(c4d.OCT_MATERIAL_DISPLACEMENT_LINK)
                if displacementNode:
                    displacementSlotName = c4d.DISPLACEMENT_TEXTURE
                    displacementNode[displacementSlotName] = self.CreateImageTextureNode("displacement", "Displacement")

            if "opacity" in self.textures:  
                self.CreateImageTextureNode("opacity", "Opacity", 1, 1, False, c4d.OCT_MATERIAL_OPACITY_LINK)

            if "translucency" in self.textures:  
                self.CreateImageTextureNode("translucency", "Translucency", 0, 2.2, False, c4d.OCT_MATERIAL_TRANSMISSION_LINK)
                self.mat[c4d.UNIVMAT_TRANSMISSION_TYPE] = 1
            elif "transmission" in self.textures:  
                self.CreateImageTextureNode("transmission", "Transmission", 1, 1, False, c4d.OCT_MATERIAL_TRANSMISSION_LINK)
                self.mat[c4d.UNIVMAT_TRANSMISSION_TYPE] = 1
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")

    def CreateImageTextureNode(self, textureType, nodeName, textureMode = 1, gamma = 1, invert = False, parentNode = None):
        try:
            texturePath = self.GetTexturePath(textureType)
            if texturePath and os.path.exists(texturePath):
                imageTextureNode = c4d.BaseList2D(1029508)
                imageTextureNode[c4d.IMAGETEXTURE_FILE] = texturePath
                imageTextureNode[c4d.IMAGETEXTURE_INVERT] = invert
                imageTextureNode[c4d.IMAGETEXTURE_GAMMA] = gamma
                imageTextureNode[c4d.IMAGETEXTURE_MODE] = textureMode # 1 = Float and 0 is Normal (Color)
                imageTextureNode.SetName(nodeName)
                
                if self.connectToTransformNode:
                    imageTextureNode[c4d.IMAGETEXTURE_TRANSFORM_LINK] = self.transformNode
                
                if parentNode:
                    self.mat[parentNode] = imageTextureNode
                self.mat.InsertShader(imageTextureNode)
            
                return imageTextureNode
            else:
                print("Quixel Bridge Plugin::Failed to find the " + textureType + " texture.")
                return None
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
            return None
    
    def CreateTransformNode(self):
        try:
            self.transformNode = c4d.BaseList2D(1030961)
            self.mat.InsertShader(self.transformNode)
            self.connectToTransformNode = True
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")

    def CreateMultiplyNode(self, imageTexture1, imageTexture2, parentNode = None):
        try:
            multiplyNode = c4d.BaseList2D(1029516)
            multiplyNode[c4d.MULTIPLY_TEXTURE1] = imageTexture1
            multiplyNode[c4d.MULTIPLY_TEXTURE2] = imageTexture2
            
            if parentNode:
                self.mat[parentNode] = multiplyNode
            self.mat.InsertShader(multiplyNode)
            
            return multiplyNode
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
            return None

    def CreateCCNode(self, imageTexture):
        try:
            colorCorrectionNode = c4d.BaseList2D(1029512)
            colorCorrectionNode[c4d.COLORCOR_TEXTURE_LNK] = imageTexture
            self.mat.InsertShader(colorCorrectionNode)
            return colorCorrectionNode
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
            return None

    def CreateDisplacementNode(self, parentNode = None):
        try:
            displacementNode = c4d.BaseList2D(1031901)
            displacementNode[c4d.DISPLACEMENT_AMOUNT] = 1 if self.assetType.lower() in ["3d","3dplant"] else 10
            displacementNode[c4d.DISPLACEMENT_MID] = 0.5
            self.mat[c4d.OCT_MAT_USE_DISPLACEMENT] = not self.hasGeometry
            
            if parentNode:
                self.mat[parentNode] = displacementNode
            self.mat.InsertShader(displacementNode)

            return displacementNode
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
            return None

    def GetTexturePath(self, textureType):
        try:
            return self.textures.get(textureType, "").replace("\\", "/")
        except Exception as e:
            helpers.handle_exception(e, "Failed to create octane material")
            return None

def octane_material(textureList, matName, isMetal, assetType, hasGeometry, isSpecularWorkflow):
    octane_setup = OctaneSetup(textureList, assetType, hasGeometry, matName, isSpecularWorkflow, isMetal)
    return octane_setup.CreateMaterial()
