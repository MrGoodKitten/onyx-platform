def DeselectEverything():
    return '''
    actionMan.executeAction 0 "40043"  -- Selection: Select None
    '''

def ShowInViewport(nodeName = "mat" ):
    return f'''
    {nodeName}.showInViewport = true
    '''

def GetActiveSMEView():
    return '''
    ActiveSMEView = sme.GetView (sme.activeView)
    '''

def CreateNodeInSME(nodeName, x, y):
    return f'''
    ActiveSMEView.CreateNode {nodeName} [{x}, {y}]
    '''

def AssignMaterialToObjects(materialName = "mat"):
    return f'''
    select CurOBJs
    for o in selection do o.material = {materialName}
    '''

def OpenObjImpFile():
    # Obj import settings modification
    # Ref: https://help.autodesk.com/view/MAXDEV/2021/ENU/?guid=GUID-639CF6E0-1B9F-4B05-9CE8-D6418162E0CE
    return '''
    objIniFile =objimp.getIniName()
    getIniSetting objIniFile
    '''
    
def GetObjSetting(parent, child, varName):
    return f'''
    {varName} = getIniSetting objIniFile "{parent}""{child}"
    '''

def ChangeObjSetting(parent, child, varValue):
    return f'''
    setIniSetting objIniFile "{parent}""{child}" "{varValue}"
    '''

def ResetObjIniValue(parent, child, varName):
    return f'''
    setIniSetting objIniFile "{parent}""{child}" {varName}
    '''

def SelectObjects():
    return '''
    select CurOBJs
    '''

def SetWidthAndHeight(scanWidth, scanHeight):
    return f'''
    scanWidth = {scanWidth}
    scanHeight = {scanHeight}
    '''

def ConnectNodeToMaterial(connectionName, nodeName):
    return f'''
    mat.{connectionName} = {nodeName}
    '''

def AddNormalProperties(textureTypes, is3DAsset = False):
    # TODO : this could be improved
    return f'''
    hasNormal = {"normal" in textureTypes}
    hasBump = {("bump" in textureTypes) and not is3DAsset}
    '''

def AlembicImportSettings():
    return '''
    AlembicImport.Visibility = True
    AlembicImport.UVs = True
    AlembicImport.Normals = True
    AlembicImport.VertexColors = True
    AlembicImport.ImportToRoot = True
    AlembicImport.CoordinateSystem = #YUp
    AlembicImport.FitTimeRange = False
    AlembicImport.SetStartTime = False
    AlembicImport.ExtraChannels = False
    AlembicImport.Velocity = False
    AlembicImport.MaterialIDs = False
    AlembicImport.ShapeSuffix = False
    '''

def RearrangeMaterialGraph():
    return '''
    actionMan.executeAction 369891408 "40060"
    '''

def ShowMessageDialog(title, message):
    return f'''
    messagebox "{message}" title: "{title}"
    '''

def AssignMaterialToMultiSlots(multiNodeName, matName, slotsToAssignTo):
    return ''.join([f'''
    {multiNodeName}.materialList[{x}] = {matName}
    ''' for x in slotsToAssignTo])

def CreateMultiSubMaterial(multiNodeName, matName, matsAmount):
    multi_node_script = f'''
    {multiNodeName} = multiSubMaterial()
    {multiNodeName}.name = "{matName}"
    {multiNodeName}.numsubs = {matsAmount}
    '''
    # Removing default PBR materials. Also we add 1 to index because material list starts from index number 1.
    for x in range(matsAmount):
        multi_node_script += f'''
        {multiNodeName}.materialList[{x + 1}] = undefined
        '''
    return multi_node_script