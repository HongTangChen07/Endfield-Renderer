"""Explicit, reviewable adapters for the three supplied MMD imports."""
PROFILES = {
 'Nico': {'object':'尼可_mesh','roles':{
    'face':['颜'], 'detail':['睫眉','白目','口线','口舌','齿','星目'], 'eye':['目'],
    'hair':['前髪','髮'], 'overlay':['髮+'], 'skin':['肌','肌_2','肌1','肌1_2'],
    'metal':['髮饰','帽饰','饰','饰2','体饰','头饰'], 'glass':['神之眼'],
    'cloth':['帽','体','体2','后带1','后带2','袖','带','袜','裙内','带内','裙内2'] }},
 'Tevelos': {'object':'提弗洛斯_mesh','roles':{
    'face':['面'],'detail':['目白','睫','眉','口内'], 'eye':['目.001','目HL'],
    'overlay':['目影','发影','表情'],'skin':['肌.001'],'hair':['发'],
    'cloth':['Cloth1','Cloth2','Cloth1Alpha1','Cloth1Alpha2','Cloth2Alpha','Cloth6','Cloth6Alpha']}},
 'Suomi': {'object':'GirlsFrontline SuomiDefault_mesh','roles':{
    'face':['Face'],'detail':['Mouth','Teeth','Teeth.001','Tongue','EyeWhite','EyeLid','Brows','Lashes'],
    'eye':['Eyes'], 'overlay':['Eyes+','EyeShadow','Emotions1','Emotions2'],
    'skin':['BodySkin'],'cloth':['Cloth1A','Cloth1B','Socks'],'metal':['Cloth2(metalic)'],
    'glass':['Lanterns'],'fur':['Fur'],'hair':['Hair','Hair.001']}}
}

def role_for(character, material):
    for role,names in PROFILES[character]['roles'].items():
        if material in names:return role
    raise ValueError(f'未分类的材质：{character}/{material}')

CHANNEL_SCHEMA = {'Endfield_P':{'R':'metallic','G':'reserved/source shader auxiliary mask','B':'ambient occlusion','A':'perceptual smoothness'},
                  'Endfield_Hair_P':{'R':'directional normal blend','G':'anisotropic highlight mask','B':'occlusion','A':'highlight attenuation'},
                  'Endfield_HN':{'R':'primary normal X','G':'primary normal Y','B':'highlight normal X','A':'highlight normal Y'},
                  'Suomi_RMO':{'R':'roughness','G':'metallic','B':'occlusion'},
                  'Normal':'OpenGL tangent +Y, RGB; reference DecodeNormal reconstructs Z from RG'}
