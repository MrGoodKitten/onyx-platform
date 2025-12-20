import helpers
import ms_snippets as ms

class GenericRenderer():

    def __init__(self, assetData, fromSME = False):

        self.assetData = assetData
        self.script = ms.GetActiveSMEView() if fromSME else ""

        # Parse data from asset_data
        self.uses_displacement = assetData.useDisplacement
        self.is_snow = assetData.isSnow
        self.root_material_name = assetData.materialName
        self.asset_type = assetData.assetType
        self.is_bare_metal = assetData.isBareMetal

        # Multi material info
        self.has_multi_material, self.materials_data, self.num_materials = helpers.get_multi_material_info(assetData.meta)
        self.root_node_name = "MutliMaterial" if self.has_multi_material else "MatNode"

    def get_script(self):

        if self.has_multi_material:
            self.script += ms.CreateMultiSubMaterial(self.root_node_name, self.root_material_name, self.num_materials)
            for index, data in enumerate(self.materials_data):
                material_name = f"{self.root_material_name}_{index+1}"
                node_name = f"MatNode_{index+1}"
                self.script += self.multi_material_script(node_name, material_name, data.matType == "glass")
                # TODO, that was done like this before which feels not OK (node_name used as material name)
                self.script += ms.AssignMaterialToMultiSlots(self.root_node_name, node_name, data.matIDs)
        else:
            self.script += self.single_material_script(self.root_node_name, self.root_material_name)

        self.script += self.post_material_script()

        return self.script
    
    def multi_material_script(self, node_name, mat_name, is_glass) -> str:
        raise NotImplementedError
    
    def single_material_script(self, node_name, mat_name) -> str:
        raise NotImplementedError
    
    def post_material_script(self, show = True, deselect = False, rearrange=False) -> str:
        post = ms.CreateNodeInSME(self.root_node_name, 0, 0)
        post += ms.AssignMaterialToObjects(self.root_node_name)
        if show: post += ms.ShowInViewport(self.root_node_name)
        # TODO : in some renderers, this was not added to the script correctly
        # For now, we keep the behaviour same as Bridge
        if rearrange: post += ms.RearrangeMaterialGraph()
        if deselect: post += ms.DeselectEverything()
        return post