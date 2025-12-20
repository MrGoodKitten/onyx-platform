import helpers
import ms_snippets as ms
from renderers._generic import GenericRenderer

class Vray(GenericRenderer):

    # TODO: compared to other renderers, this one stores its setup in VRayRenderSetup
    # Ideally, we'd like to clean this to make it more straightforward

    def __init__(self, assetData):
        GenericRenderer.__init__(self, assetData, fromSME=True)
        self.roughnessUsed = False
        self.VrayRenderSetup = ""
        self.VrayRenderSetup = ms.SetWidthAndHeight(self.assetData.width * 100, self.assetData.height * 100)

    def multi_material_script(self, node_name, mat_name, is_glass):
        if is_glass:
            return self.GetGlassMultiMaterial(node_name, mat_name)
        elif self.is_bare_metal:
            self.CreateBareMetalMaterial()
            return ""
        else:
            return self.GetOpaqueMultiMaterial(node_name, mat_name)
    
    def single_material_script(self, node_name, mat_name):
        # The VRay setup is strange in Bridge, but we keep the same flow here
        if self.assetData.isBareMetal:
            self.CreateBareMetalMaterial()
        else:
            self.CreateOpaqueMaterial()
        return ""
    
    def post_material_script(self):
        # Normal post import is only used for multi materials in Bridge
        if self.has_multi_material:
            self.script += super().post_material_script(show=True, deselect=False, rearrange=False)

        # Now update some VRayRenderSetup data, and append the normal script to it
        if self.roughnessUsed:
            self.UseRoughness()
        self.VrayRenderSetup += ms.DeselectEverything()
        self.VrayRenderSetup += self.script
        self.script = ""
        return self.VrayRenderSetup # This will override self.script

  
    def GetGlassMultiMaterial(self,nodeName, matName):
        assetType = self.assetData.assetType.lower()
        script = ''
        script += self.CreateMatNode()
         
        if "specular" in self.assetData.textures:
            script += self.CreateHDRINode("texmap_reflection", True, "specular", 2, -300, 612)
        if "glossiness" in self.assetData.textures:
            script += self.CreateHDRINode("texmap_reflectionGlossiness", True, "glossiness", 1, -300, 780)
        elif "roughness" in self.assetData.textures:
            script+= self.CreateHDRINode("texmap_reflectionGlossiness", True, "roughness", 1, -300, 780)
            self.roughnessUsed = True

        script += ms.AddNormalProperties(self.assetData.textureTypes, assetType == "3d")
        if "normal" in self.assetData.textures or "bump" in self.assetData.textures:
            script += self.CreateNormalNode("texmap_bump", True, "Nrm + Bump", "normal", "bump", 1, 1, -300, 680, -600, 670, -600, 690)
        
        if "opacity" in self.assetData.textures:
            script += self.CreateHDRINode("texmap_opacity", True, "opacity", 1, -300, 830)
        
        script += 'mat.Refraction = color 225 225 225'
        
        return script.replace('mat', nodeName)
    
    def GetOpaqueMultiMaterial(self,nodeName, matName):
        assetType = self.assetData.assetType.lower()
        script = ''
        script += self.CreateMatNode()
        
        if "albedo" in self.assetData.textures:
            if "ao" in self.assetData.textures:
                script += self.CreateComplexNode("texmap_diffuse", True, "Albedo + AO", "albedo", "ao", 2, 1, -300, 512, -600, 500, -600, 540)
            else:
                script += self.CreateHDRINode("texmap_diffuse", True, "albedo", 2, -300, 540)
        
        if "specular" in self.assetData.textures:
            script += self.CreateHDRINode("texmap_reflection", True, "specular", 2, -300, 612)
        if "glossiness" in self.assetData.textures:
            script += self.CreateHDRINode("texmap_reflectionGlossiness", True, "glossiness", 1, -300, 780)
        elif "roughness" in self.assetData.textures:
            script+= self.CreateHDRINode("texmap_reflectionGlossiness", True, "roughness", 1, -300, 780)
            self.roughnessUsed = True
        
        script += ms.AddNormalProperties(self.assetData.textureTypes, assetType == "3d")
        if "normal" in self.assetData.textures or "bump" in self.assetData.textures:
            script += self.CreateNormalNode("texmap_bump", True, "Nrm + Bump", "normal", "bump", 1, 1, -300, 680, -600, 670, -600, 690)
        
        if "cavity" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_cavity", False, "cavity", 1, -300, 1050)
            
        if "fuzz" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_fuzz", False, "fuzz", 1, -300, 1150)

        if "opacity" in self.assetData.textures:
            script += self.CreateHDRINode("texmap_opacity", True, "opacity", 1, -300, 830)

        if "translucency" in self.assetData.textures:
            script += self.CreateHDRINode("", False, "translucency", 2, 0, 950)
            self.ConnectTranslucencyTexture()
        
        elif "transmission" in self.assetData.textures:
            script += self.CreateHDRINode("", False, "transmission", 1, 0, 950)
            self.ConnectTranslucencyTexture()

        if "displacement" in self.assetData.textures and self.assetData.useDisplacement and assetType not in ["3dplant"]:
            script += ms.SelectObjects()
            script += self.CreateHDRINode("", False, "displacement", 1, -300, 830)
            if(assetType == "3d"):
                self.SetupDisplacement(2)
            else:
                self.SetupDisplacement(8)                
        return script.replace('mat', nodeName)
    
    def CreateOpaqueMaterial(self):

        assetType = self.assetData.assetType.lower()
        isPlant = assetType == "3dplant"

        if isPlant:
            self.CreateTwoSidedMatNode()
        elif "transmission" in self.assetData.textures or "translucency" in self.assetData.textures:
            self.CreateSSSMatNode()
        else:
            self.VrayRenderSetup += self.CreateMatNode()

        self.StandardIORSetup()

        if "albedo" in self.assetData.textures:
            if "ao" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateComplexNode("texmap_diffuse", True, "Albedo + AO", "albedo", "ao", 2, 1, -300, 512, -600, 500, -600, 540)
                if isPlant:
                    self.AlbedoFor3DPlant()
            else:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_diffuse", True, "albedo", 2, -300, 540)
        
        if self.assetData.isSpecular:
            if "specular" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_reflection", True, "specular", 2, -300, 612)
            if "glossiness" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_reflectionGlossiness", True, "glossiness", 1, -300, 780)
            elif "roughness" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_reflectionGlossiness", True, "roughness", 1, -300, 780)
                self.roughnessUsed = True

        else:
            if "metal" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_metalness", True, "metal", 1, -300, 612)
            if "roughness" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_reflectionGlossiness", True, "roughness", 1, -300, 780)
                self.roughnessUsed = True

            elif "glossiness" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_reflectionGlossiness", True, "glossiness", 1, -300, 780)

        self.VrayRenderSetup += ms.AddNormalProperties(self.assetData.textureTypes)
        if "normal" in self.assetData.textures or "bump" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateNormalNode("texmap_bump", True, "Nrm + Bump", "normal", "bump", 1, 1, -300, 680, -600, 670, -600, 690)

        if "opacity" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_opacity", True, "opacity", 1, -300, 830)

        if "cavity" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_cavity", False, "cavity", 1, -300, 1050)
        
        if "fuzz" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_fuzz", False, "fuzz", 1, -300, 1150)

        if "translucency" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("", False, "translucency", 2, 0, 950)
            self.ConnectTranslucencyTexture()
        
        elif "transmission" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("", False, "transmission", 1, 0, 950)
            self.ConnectTranslucencyTexture()

        if "displacement" in self.assetData.textures and self.assetData.useDisplacement and assetType not in ["3dplant"]:
            self.VrayRenderSetup += ms.SelectObjects()
            self.VrayRenderSetup += self.CreateHDRINode("", False, "displacement", 1, -300, 830)
            if(assetType == "3d"):
                self.SetupDisplacement(2)
            else:
                self.SetupDisplacement(8)
        
        if (assetType not in ["3d", "3dplant"])or assetType in ["3d", "3dplant"]: #If asset is a surface or 3d/3dplant
            self.VrayRenderSetup += ms.AssignMaterialToObjects("mat_2sided" if isPlant else "mat")

    def CreateBareMetalMaterial(self):
        self.VrayRenderSetup += self.CreateMatNode()
        self.MetalIORSetup()
        
        if "specular" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_reflection", True, "specular", 2, -300, 612)
        else:
            if "albedo" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_diffuse", True, "albedo", 2, -300, 540)
        
            if "metal" in self.assetData.textures:
                self.VrayRenderSetup += self.CreateHDRINode("texmap_metalness", True, "metal", 1, -300, 612)

        self.VrayRenderSetup += ms.AddNormalProperties(self.assetData.textureTypes)
        if "normal" in self.assetData.textures or "bump" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateNormalNode("texmap_bump", True, "Nrm + Bump", "normal", "bump", 1, 1, -300, 680, -600, 670, -600, 690)
        
        if "glossiness" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_reflectionGlossiness", True, "glossiness", 1, -300, 780)
        elif "roughness" in self.assetData.textures:
            self.VrayRenderSetup += self.CreateHDRINode("texmap_reflectionGlossiness", True, "roughness", 1, -300, 780)
            self.roughnessUsed = True

        
        #if self.assetData.applyToSel:
        self.VrayRenderSetup += ms.AssignMaterialToObjects()

    def CreateMatNode(self, MatXLoc = 0, MatYLoc = 512, defaultRefl = 128):
        matScript = ("""
        
        mat = VRayMtl()
        ActiveSMEView = sme.GetView (sme.activeView)
        ActiveSMEView.CreateNode mat [MatXLoc, MatYLoc]
        mat.name = "MS_MATNAME"
        mat.brdf_type = 4

        isPlant = False
        useRealWorldScale = False

        -- Sets the reflection color to a 0.5 grayscale value.
        mat.Reflection = color defaultRefl defaultRefl defaultRefl
        
        """).replace("MS_MATNAME", self.assetData.materialName).replace("MatXLoc", str(MatXLoc)).replace("MatYLoc", str(MatYLoc)).replace("defaultRefl", str(defaultRefl))
        return matScript    
    def CreateTwoSidedMatNode(self, MatXLoc = 0, MatYLoc = 512, defaultRefl = 128):
        matScript = ("""
        
        mat = VRayMtl()
        ActiveSMEView = sme.GetView (sme.activeView)
        mat.name = "MS_MATNAME"

        mat_2sided = VRay2SidedMtl()
        mat_2sided.name = "MS_MATNAME"
        mat_2sided.frontMtl = mat
        mat_2sided.backMtl = mat

        ActiveSMEView.CreateNode mat_2sided [150,650]
        ActiveSMEView.CreateNode mat [MatXLoc, MatYLoc]

        mat.brdf_type = 4

        mat.showInViewport = true

        isPlant = True
        useRealWorldScale = False

        -- Sets the reflection color to a 0.5 grayscale value.
        mat.Reflection = color defaultRefl defaultRefl defaultRefl
        
        """).replace("MS_MATNAME", self.assetData.materialName).replace("MatXLoc", str(MatXLoc)).replace("MatYLoc", str(MatYLoc)).replace("defaultRefl", str(defaultRefl))
        self.VrayRenderSetup += matScript
    
    def CreateSSSMatNode(self, MatXLoc = 0, MatYLoc = 512, defaultRefl = 128):
        matScript = ("""
        
        mat = VRayMtl()
        ActiveSMEView = sme.GetView (sme.activeView)
        mat.name = "MS_MATNAME"

        mat_2sided = VRay2SidedMtl()
        mat_2sided.name = "MS_MATNAME"
        mat_2sided.frontMtl = mat

        ActiveSMEView.CreateNode mat_2sided [150,650]
        ActiveSMEView.CreateNode mat [MatXLoc, MatYLoc]

        mat.brdf_type = 4

        mat.showInViewport = true

        mat.translucency_on = 3

        isPlant = False
        useRealWorldScale = False

        -- Sets the reflection color to a 0.5 grayscale value.
        mat.Reflection = color defaultRefl defaultRefl defaultRefl
        
        """).replace("MS_MATNAME", self.assetData.materialName).replace("MatXLoc", str(MatXLoc)).replace("MatYLoc", str(MatYLoc)).replace("defaultRefl", str(defaultRefl))
        self.VrayRenderSetup += matScript

    def CreateHDRINode(self, connectionName, connectToMat, texType, colorspace, nodeXLoc, nodeYLoc):
        hdriScript = ("""

        -- NodeName setup
        hdriMapNode = VRayHDRI()
        hdriMapNode.name = "NodeName"
        hdriMapNode.HDRIMapName =   "TexPath"
        hdriMapNode.color_space = colorspace
        
        if useRealWorldScale do (
            hdriMapNode.coords.realWorldScale = on 
            hdriMapNode.coords.U_Tiling = scanWidth
            hdriMapNode.coords.V_Tiling = scanHeight
        )

        hdriMapNode.coords.blur = 0.01

        ActiveSMEView.CreateNode hdriMapNode [nodeXLoc, nodeYLoc]


        """).replace("NodeName", texType.capitalize()).replace("TexPath", helpers.GetTexturePath(self.assetData.textures, texType))
        hdriScript = hdriScript.replace("colorspace", str(colorspace)).replace("nodeXLoc", str(nodeXLoc)).replace("nodeYLoc", str(nodeYLoc))

        if connectToMat:
            hdriScript += ms.ConnectNodeToMaterial(connectionName, "hdriMapNode")
            
        return hdriScript

    def CreateComplexNode(self, connectionName, connectToMat, nodeName, texAType, texBType, aColorspace, bColorspace, NodeXLoc, NodeYLoc, aNodeXLoc, aNodeYLoc, bNodeXLoc, bNodeYLoc):
        complexNodeScript = ("""

        -- NodeName setup
        complexNode = VRayCompTex ()
        complexNode.name = "NodeName"
        complexNode.operator = 3

        complexNode.sourceA  = VRayHDRI()
        complexNode.sourceA.name = "NodeAName"
        complexNode.sourceA.HDRIMapName =   "aTexPath"
        complexNode.sourceA.color_space = aColorspace

        complexNode.sourceB  = VRayHDRI()
        complexNode.sourceB.name = "NodeBName"
        complexNode.sourceB.HDRIMapName =   "bTexPath"
        complexNode.sourceB.color_space = bColorspace

        if useRealWorldScale do (
            complexNode.sourceA.coords.realWorldScale = on 
            complexNode.sourceA.coords.U_Tiling = scanWidth
            complexNode.sourceA.coords.V_Tiling = scanHeight

            complexNode.sourceB.coords.realWorldScale = on 
            complexNode.sourceB.coords.U_Tiling = scanWidth
            complexNode.sourceB.coords.V_Tiling = scanHeight
        )

        complexNode.sourceA.coords.blur = 0.01
        complexNode.sourceB.coords.blur = 0.01

        ActiveSMEView.CreateNode complexNode [PosX, PosY]
        ActiveSMEView.CreateNode complexNode.sourceA [aPosX, aPosY]
        ActiveSMEView.CreateNode complexNode.sourceB [bPosX, bPosY]

        """).replace("NodeName", nodeName).replace("NodeAName", texAType).replace("aTexPath", helpers.GetTexturePath(self.assetData.textures, texAType))
        complexNodeScript = complexNodeScript.replace("aColorspace", str(aColorspace)).replace("NodeBName", texBType).replace("bTexPath", helpers.GetTexturePath(self.assetData.textures, texBType))
        complexNodeScript = complexNodeScript.replace("bColorspace", str(bColorspace))
        complexNodeScript = complexNodeScript.replace("aPosX", str(aNodeXLoc)).replace("aPosY", str(aNodeYLoc)).replace("bPosX", str(bNodeXLoc))
        complexNodeScript = complexNodeScript.replace("bPosY", str(bNodeYLoc)).replace("PosX", str(NodeXLoc)).replace("PosY", str(NodeYLoc))

        if connectToMat:
            complexNodeScript += ms.ConnectNodeToMaterial(connectionName, "complexNode")

        return complexNodeScript
    
    def CreateNormalNode(self, connectionName, connectToMat, nodeName, texAType, texBType, aColorspace, bColorspace, NodeXLoc, NodeYLoc, aNodeXLoc, aNodeYLoc, bNodeXLoc, bNodeYLoc):
        normalNodeScript = ("""

        -- NodeName setup
        normalNode = VRayNormalMap ()
        normalNode.name = "NodeName"

        if hasNormal do (
            normalNode.normal_map  = VRayHDRI()
            normalNode.normal_map.name = "NodeAName"
            normalNode.normal_map.HDRIMapName =   "aTexPath"
            normalNode.normal_map.color_space = aColorspace
            normalNode.normal_map.coords.blur = 0.01
            ActiveSMEView.CreateNode normalNode.normal_map [aPosX, aPosY]
        )

        if hasBump do (
            normalNode.bump_map  = VRayHDRI()
            normalNode.bump_map.name = "NodeBName"
            normalNode.bump_map.HDRIMapName =   "bTexPath"
            normalNode.bump_map.color_space = bColorspace
            normalNode.bump_map.coords.blur = 0.01
            ActiveSMEView.CreateNode normalNode.bump_map [bPosX, bPosY]
        )

        if useRealWorldScale do (
            if hasNormal do (
            normalNode.normal_map.coords.realWorldScale = on 
            normalNode.normal_map.coords.U_Tiling = scanWidth
            normalNode.normal_map.coords.V_Tiling = scanHeight
            )

            if hasBump do (
                normalNode.bump_map.coords.realWorldScale = on 
                normalNode.bump_map.coords.U_Tiling = scanWidth
                normalNode.bump_map.coords.V_Tiling = scanHeight
            )
        )

        ActiveSMEView.CreateNode normalNode [PosX, PosY]

        """).replace("NodeName", nodeName).replace("NodeAName", texAType.capitalize()).replace("aTexPath", helpers.GetTexturePath(self.assetData.textures, texAType))
        normalNodeScript = normalNodeScript.replace("aColorspace", str(aColorspace)).replace("NodeBName", texBType.capitalize()).replace("bTexPath", helpers.GetTexturePath(self.assetData.textures, texBType))
        normalNodeScript = normalNodeScript.replace("bColorspace", str(bColorspace))
        normalNodeScript = normalNodeScript.replace("aPosX", str(aNodeXLoc)).replace("aPosY", str(aNodeYLoc)).replace("bPosX", str(bNodeXLoc))
        normalNodeScript = normalNodeScript.replace("bPosY", str(bNodeYLoc)).replace("PosX", str(NodeXLoc)).replace("PosY", str(NodeYLoc))

        if connectToMat:
            normalNodeScript += ms.ConnectNodeToMaterial(connectionName, "normalNode")

        return normalNodeScript

    def StandardIORSetup(self):
        IORScript = ("""
        mat.reflection_lockIOR = off
        mat.reflection_ior = 1.5
        """)
        self.VrayRenderSetup += IORScript

    def MetalIORSetup(self):
        IORScript = ("""
        mat.Diffuse = color 0 0 0
        mat.reflection_lockIOR = off
        mat.reflection_ior = 100
        """)
        self.VrayRenderSetup += IORScript

    def UseRoughness(self):
        useRoughnessScript = ("""
        mat.brdf_useRoughness = on
        """)
        self.VrayRenderSetup += useRoughnessScript
    
    def UseRealWorldScale(self):
        useRealWorldScaleScript = ("""
        useRealWorldScale = True
        """)
        self.VrayRenderSetup += useRealWorldScaleScript

    def SetupDisplacement(self, displacementValue):
        dispScript = ("""
        max modify mode
        dispMod = VRayDisplacementMod ()
        dispMod.type = 1
        dispMod.amount = displacementValue
        dispMod.texmap = hdriMapNode
        modPanel.addModToSelection (dispMod)
        max create mode
        """).replace("displacementValue", str(displacementValue))
        self.VrayRenderSetup += dispScript

    def AlbedoFor3DPlant(self):
        twoSidedMatScript = ("""
        mat.texmap_diffuse = complexNode.SourceA
        """)
        self.VrayRenderSetup += twoSidedMatScript

    def ConnectTranslucencyTexture(self):
        translucencyScript = ("""
        mat_2sided.texmap_translucency = hdriMapNode
        """)
        self.VrayRenderSetup += translucencyScript
