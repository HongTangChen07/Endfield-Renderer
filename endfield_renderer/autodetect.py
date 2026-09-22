"""Read-only material/texture discovery. Image loading is deferred until configuration starts."""
import bpy,pathlib,re,json
from . import resources

IMAGE_FIELDS={'D':'base_image','N':'normal_image','P':'packed_image','HN':'hair_normal_image','E':'emission_image','Roughness':'roughness_image','Metallic':'metallic_image','AO':'ao_image','RMO':'rmo_image'}
SUFFIXES={'D':['d','da','basecolor','base_color','albedo','diffuse','diff','color'], 'N':['n','normal','normalgl','normal_gl','nrm','nor'], 'P':['p','endfield_p'], 'HN':['hn','hairnormal','hair_normal'], 'E':['e','emission','emissive','emit'], 'Roughness':['roughness','rough','r'], 'Metallic':['metallic','metalness','metal'], 'AO':['ao','occlusion','ambientocclusion'], 'RMO':['rmo']}
EXTENSIONS={'.png','.tga','.jpg','.jpeg','.bmp','.tif','.tiff','.exr','.dds'}

def named_role(name):
    n=re.sub(r'\.\d{3}$','',name.lower());words=set(re.split(r'[^a-z]+',n))
    # Expression/shadow planes are tested before any broad face/hair keywords.
    for role,terms in [
        ('overlay',['hairshadow','eyeshadow','eyewhiteshadow','hairline','blush','emotion','expression','tear','涙','泪','淚','照れ','赤面','脸红','脸影','发影','髮影','目影','表情']),
        ('brow',['eyelash','eyebrow','brow','lash','まつげ','睫','眉']),
        ('detail',['eyewhite','eye_white','sclera','mouth','teeth','tooth','tongue','lip','白目','目白','眼白','口','齿','歯','舌','唇','鼻線']),
        ('eye',['iris','瞳']),('metal',['metal','armor','armour','金属','髮饰','髪飾','发饰','头饰','头飾']),
        ('hair',['hair','髪','髮','头发','发丝']),('skin',['skin','肌','皮肤']),
        ('face',['face','顔','颜','面部','脸部']),('fur',['fur','plush','fuzz','绒','毛皮']),
        ('glass',['glass','lens','玻璃','镜片']),('cloth',['cloth','coat','dress','shirt','fabric','sock','衣','裙','袖','袜','帯','带','腰带'])]:
        if any(t in n for t in terms):return role
    if n in ['面','脸']:return 'face'
    if n in ['发','毛']:return 'hair'
    if n in ['目','眼','eyes','eye'] or 'eyes' in words:return 'eye'
    if 'body' in words:return 'skin'
    return None

def available(value):
    return resources.usable_image(value) if isinstance(value,bpy.types.Image) else bool(value and pathlib.Path(value).is_file())

def image_key(value):
    if isinstance(value,bpy.types.Image):return value.name
    return str(value or '')

def upstream(socket,seen=None):
    seen=set() if seen is None else seen
    for link in socket.links:
        n=link.from_node
        if n.as_pointer() in seen:continue
        seen.add(n.as_pointer())
        if n.type=='TEX_IMAGE' and n.image:return n.image
        for inp in n.inputs:
            if inp.is_linked:
                im=upstream(inp,seen)
                if im:return im
    return None

def base_image(material):
    mat=resources.original_material(material);im=resources.base_image(mat)
    if im:return im
    if not mat.node_tree:return None
    for n in mat.node_tree.nodes:
        if n.type not in ['BSDF_PRINCIPLED','GROUP']:continue
        for name in ['Base Color','Base Tex','_D(sRGB)R.G.B','Color']:
            if name in n.inputs and n.inputs[name].is_linked:
                im=upstream(n.inputs[name])
                if im:return im
    for n in mat.node_tree.nodes:
        if n.type=='TEX_IMAGE' and n.image and channel(n.image.filepath or n.image.name)=='D':return n.image
    return None

def channel(name):
    stem=pathlib.Path(re.sub(r'\.\d{3}$','',name)).stem.lower()
    for kind,suffixes in SUFFIXES.items():
        if any(stem.endswith('_'+s) or stem.endswith('-'+s) for s in suffixes):return kind
    return None

def stem_for(value):
    name=value.filepath or value.name if isinstance(value,bpy.types.Image) else str(value)
    stem=pathlib.Path(re.sub(r'\.\d{3}$','',name)).stem
    for suffix in sorted(SUFFIXES['D'],key=len,reverse=True):
        if stem.lower().endswith(('_'+suffix,'-'+suffix)):return stem[:-(len(suffix)+1)]
    return stem

def alpha_of(mat):
    if mat.node_tree:
        n=mat.node_tree.nodes.get('mmd_shader')
        if n and 'Alpha' in n.inputs:return float(n.inputs['Alpha'].default_value)
        n=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if n:return float(n.inputs['Alpha'].default_value)
    return float(mat.diffuse_color[3])

def related_maps(mat,base):
    found={};evidence={}
    if mat.node_tree:
        for n in mat.node_tree.nodes:
            if n.type=='BSDF_PRINCIPLED':
                for socket,kind in [('Normal','N'),('Roughness','Roughness'),('Metallic','Metallic'),('Emission Color','E')]:
                    if socket in n.inputs and n.inputs[socket].is_linked:
                        im=upstream(n.inputs[socket])
                        if available(im):found[kind]=im;evidence[kind]='原材质节点连接'
            if n.type=='GROUP':
                for name,kind in [('_N(非色彩Non_Color)','N'),('_HN(非色彩Non_Color)R.G.B','HN'),('_P(非色彩Non_Color)R.G.B','P'),('_E（非色彩）','E')]:
                    if name in n.inputs and n.inputs[name].is_linked:
                        im=upstream(n.inputs[name])
                        if available(im):found[kind]=im;evidence[kind]='原材质节点连接'
    if not base:return found,evidence
    stem=stem_for(base).lower()
    path=pathlib.Path(bpy.path.abspath(base.filepath)) if isinstance(base,bpy.types.Image) else pathlib.Path(base)
    dirs=[path.parent,path.parent/'normalmap',path.parent/'normal',path.parent/'maps',path.parent.parent/'other tex',path.parent.parent/'textures']
    files={}
    for directory in dirs:
        if directory.is_dir():
            for p in sorted(directory.iterdir()):
                if p.is_file() and p.suffix.lower() in EXTENSIONS:files.setdefault(p.stem.lower(),p)
    # Match the full atlas stem; never borrow another character's similarly named map.
    for kind,suffixes in SUFFIXES.items():
        if kind=='D' or kind in found:continue
        names=[stem+sep+s for s in suffixes for sep in ['_','-']]
        p=next((files[n] for n in names if n in files),None)
        if p:found[kind]=str(p);evidence[kind]='同名纹理文件'
        else:
            im=next((i for i in bpy.data.images if i.packed_file and pathlib.Path(bpy.path.abspath(i.filepath)).stem.lower() in names and pathlib.Path(bpy.path.abspath(i.filepath)).parent in dirs),None)
            if im:found[kind]=im;evidence[kind]='同目录已打包纹理'
    return found,evidence

def role_of(mat,base):
    names=[mat.name,getattr(getattr(mat,'mmd_material',None),'name_j','')]
    for name in names:
        role=named_role(name)
        if role:return role,.95,'材质名称：'+name
    if base:
        name=base.name if isinstance(base,bpy.types.Image) else pathlib.Path(base).name
        role=named_role(name)
        if role:return role,.85,'基础颜色文件名：'+name
    if mat.node_tree:
        n=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
        if n and not n.inputs['Metallic'].is_linked and n.inputs['Metallic'].default_value>.5:return 'metal',.7,'原材质金属度参数'
    return 'cloth',.25,'未识别具体部位，采用通用布料参数，可手动调整'

def head_bone(obj):
    arm=obj.find_armature()
    if not arm:return ''
    for name in ['頭','Head','head','头','Bip001 Head','mixamorig:Head','DEF-head']:
        if name in arm.data.bones:return name
    return next((b.name for b in arm.data.bones if re.search(r'(^|[_.: ])head($|[_. ])',b.name.lower()) and not any(s in b.name.lower() for s in ['end','tip','ik'])),'')

def analyze(obj):
    cfg=obj.ef_custom;existing={r.material.name:r for r in cfg.materials if r.material};records=[];seen=set()
    for material in obj.data.materials:
        if not material:continue
        mat=resources.original_material(material)
        if mat.name in seen:continue
        seen.add(mat.name);row=existing.get(mat.name);base=base_image(mat)
        auto_images=json.loads(row.auto_images or '{}') if row and hasattr(row,'auto_images') else {}
        manual=bool(row and row.role!='UNASSIGNED' and ((row.auto_role and row.role!=row.auto_role) or (not row.auto_role and cfg.confirmed)))
        if row and available(row.base_image):base=row.base_image
        auto_role,confidence,reason=role_of(mat,base);role=row.role if manual else auto_role
        if manual:reason='保留手动用途';confidence=1.
        channels,evidence=related_maps(mat,base)
        for kind,field in IMAGE_FIELDS.items():
            if kind=='D' or not row:continue
            value=getattr(row,field,None)
            # Manual selections win; automatically generated images are refreshed
            # from source/hash on the next run rather than treated as native maps.
            if available(value) and image_key(value)!=auto_images.get(kind):channels[kind]=value;evidence[kind]='手动指定贴图'
        alpha=alpha_of(mat)
        if row and ((row.auto_opacity>=0 and abs(row.opacity-row.auto_opacity)>1e-5) or (row.auto_opacity<0 and cfg.confirmed)):alpha=row.opacity
        if base and not available(base):base=None;reason+='；基础颜色文件不可用，使用材质纯色'
        records.append({'material':mat,'role':role,'auto_role':auto_role,'confidence':confidence,'reason':reason,'base':base,'maps':channels,'evidence':evidence,'opacity':alpha})
    bone=cfg.head_bone if obj.find_armature() and cfg.head_bone in obj.find_armature().data.bones else head_bone(obj)
    return {'records':records,'head_bone':bone}

def validate_plan(obj,plan):
    face_names={r['material'].name for r in plan['records'] if r['role']=='face'}
    slots={i for i,m in enumerate(obj.data.materials) if m and resources.original_material(m).name in face_names}
    if not any(p.material_index in slots for p in obj.data.polygons):raise ValueError(obj.name+'：未识别到实际面部，请在映射表中将面部材质设为“面部”。')
    if obj.find_armature() and not plan['head_bone']:raise ValueError(obj.name+'：未识别到头部骨骼，请在映射表中指定。')

def candidate(obj):
    if obj.type!='MESH' or not obj.data.materials:return False
    # Unselected scenery does not enter the automatic scene-wide character scan.
    return bool(head_bone(obj) and any(named_role(resources.original_material(m).name)=='face' or (base_image(m) and named_role(base_image(m).name)=='face') for m in obj.data.materials if m))

def load_image(value):
    return value if isinstance(value,bpy.types.Image) or value is None else bpy.data.images.load(str(value),check_existing=True)

def apply_plan(obj,plan):
    cfg=obj.ef_custom;existing={r.material.name:r for r in cfg.materials if r.material}
    for item in plan['records']:
        mat=item['material'];row=existing.get(mat.name) or cfg.materials.add();row.material=mat
        row.role=item['role'];row.auto_role=item['auto_role'];row.opacity=item['opacity'];row.auto_opacity=alpha_of(mat)
        row.confidence=item['confidence'];row.detection_note=item['reason'];row.base_image=load_image(item['base'])
        auto={}
        for kind,field in IMAGE_FIELDS.items():
            if kind=='D':continue
            image=load_image(item['maps'].get(kind));setattr(row,field,image)
            if item['evidence'].get(kind)!='手动指定贴图':auto[kind]=image_key(image)
        row.auto_images=json.dumps(auto,ensure_ascii=False)
        missing=[k for k in (['P','HN'] if row.role=='hair' else ['P','N']) if k not in item['maps']] if row.role in ['skin','hair','cloth','metal','fur','glass'] else []
        row.map_status=('已关联：'+', '.join(item['maps']) if item['maps'] else '使用基础颜色')+('；待生成：'+', '.join(missing) if missing else '')
    cfg.head_bone=plan['head_bone'];cfg.confirmed=True
    cfg.detection_summary=f"已识别 {len(plan['records'])} 个材质；{sum(len(r['maps']) for r in plan['records'])} 项已有贴图"
    return plan
