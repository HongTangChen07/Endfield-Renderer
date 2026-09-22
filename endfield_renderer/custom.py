"""Explicit material mapping for additional rigged or static characters."""
import bpy,pathlib,hashlib,json
from mathutils import Vector,Matrix
from . import core,resources,faces

ROLES=[('UNASSIGNED','请选择用途','请检查此材质'),('face','面部','通用卡通面部着色，不套用其他角色的面部 SDF'),('skin','皮肤','身体及颈部皮肤'),('hair','头发','各向异性头发着色，可自动生成 HN/P 贴图'),('eye','虹膜／眼睛','保留原始眼睛颜色'),('brow','眉毛／睫毛','已映射眼睛时，启用透过头发显示的叠加层'),('detail','口腔／眼白','面部细节'),('cloth','布料','织物及绘制的装饰细节'),('metal','金属','金属表面'),('fur','毛绒','粗糙柔软的纤维表面'),('glass','玻璃','具有光泽的风格化玻璃'),('overlay','透明叠加层','透明的绘制叠加层'),('skip','保留原材质','保留原始着色器')]
AXES={'NEG_Y':Vector((0,-1,0)),'POS_Y':Vector((0,1,0)),'POS_Z':Vector((0,0,1)),'NEG_Z':Vector((0,0,-1)),'POS_X':Vector((1,0,0)),'NEG_X':Vector((-1,0,0))}

def key(obj):
    existing=obj.get('ef_character','')
    anchor=bpy.data.objects.get('EF_'+str(existing)+'_HC')
    return existing if str(existing).startswith('Custom_') and anchor and anchor.get('ef_custom_owner')==obj else 'Custom_'+hashlib.sha256(obj.name.encode()).hexdigest()[:8]

def guess_role(name):
    from . import autodetect
    return autodetect.named_role(name) or 'UNASSIGNED'

def infer_image(mat):
    original=resources.original_material(mat)
    im=resources.base_image(original)
    if im:return im
    if not original.node_tree:return None
    for n in original.node_tree.nodes:
        if n.type=='BSDF_PRINCIPLED' and n.inputs['Base Color'].is_linked:
            src=n.inputs['Base Color'].links[0].from_node
            if src.type=='TEX_IMAGE':return src.image
    return next((n.image for n in original.node_tree.nodes if n.type=='TEX_IMAGE' and n.image and n.image.colorspace_settings.name=='sRGB'),None)

def populate(obj):
    from . import autodetect
    return autodetect.apply_plan(obj,autodetect.analyze(obj))

def validate(obj):
    cfg=obj.ef_custom
    if not cfg.confirmed:raise ValueError(obj.name+'：请检查所有材质用途，然后勾选“启用此映射”。')
    mapping={r.material.name:r for r in cfg.materials if r.material}
    for mat in obj.data.materials:
        original=resources.original_material(mat);row=mapping.get(original.name)
        if not row or row.role=='UNASSIGNED':raise ValueError(obj.name+'：请为此材质选择用途：'+original.name)
        for field in ['base_image','normal_image','packed_image','hair_normal_image','emission_image','roughness_image','metallic_image','ao_image','rmo_image']:
            im=getattr(row,field)
            if im and not resources.usable_image(im):raise ValueError('贴图丢失：'+im.name)
    if not any(r.role=='face' for r in mapping.values()):raise ValueError(obj.name+'：至少需要将一个材质设为“面部”，以创建头部控制点。')
    face_slots={i for i,m in enumerate(obj.data.materials) if mapping[resources.original_material(m).name].role=='face'}
    if not any(p.material_index in face_slots for p in obj.data.polygons):raise ValueError(obj.name+'：“面部”材质必须实际分配给面片。')
    arm=obj.find_armature()
    if arm and cfg.head_bone not in arm.data.bones:raise ValueError(obj.name+'：请选择头部骨骼。')
    if abs(AXES[cfg.forward_axis].dot(AXES[cfg.up_axis]))>.01:raise ValueError('前方轴和上方轴必须使用不同的坐标轴。')
    return mapping

def head_controls(obj,instance,collection):
    cfg=obj.ef_custom;forward=AXES[cfg.forward_axis];up=AXES[cfg.up_axis];right=forward.cross(up)
    mapping={r.material.name:r.role for r in cfg.materials if r.material}
    ids={v for p in obj.data.polygons if mapping.get(resources.original_material(obj.data.materials[p.material_index]).name)=='face' for v in p.vertices}
    points=[obj.data.vertices[v].co for v in ids]
    if not points:raise ValueError('映射为“面部”的材质没有分配给任何面片。')
    center=Vector([(min(v[i] for v in points)+max(v[i] for v in points))/2 for i in range(3)])
    size=max((max(v[i] for v in points)-min(v[i] for v in points) for i in range(3)))
    # Move the reference center slightly behind the facial surface.
    center-=forward*size*.12
    arm=obj.find_armature();pose=Matrix.Identity(4)
    if arm:
        bone=arm.data.bones[cfg.head_bone];pose=arm.matrix_world@arm.pose.bones[cfg.head_bone].matrix@bone.matrix_local.inverted()@arm.matrix_world.inverted()
    basis=pose@obj.matrix_world;anchors=[]
    for suffix,offset in [('HC',Vector((0,0,0))),('HF',forward*.2),('HR',right*.2),('HU',up*.2)]:
        name=f'EF_{instance}_{suffix}';empty=bpy.data.objects.get(name)
        if not empty:
            empty=bpy.data.objects.new(name,None);collection.objects.link(empty);empty.empty_display_size=size*.08;empty.location=basis@(center+offset);empty['ef_owned']=True
        empty['ef_custom_owner']=obj
        for c in list(empty.constraints):
            if c.name=='Follow mapped head':empty.constraints.remove(c)
        empty.parent=None;empty.matrix_world=Matrix.Translation(basis@(center+offset))
        if arm:
            c=empty.constraints.new('CHILD_OF');c.name='Follow mapped head';c.target=arm;c.subtarget=cfg.head_bone;c.inverse_matrix=(arm.matrix_world@arm.pose.bones[cfg.head_bone].matrix).inverted()
        else:
            empty.parent=obj;empty.matrix_parent_inverse=obj.matrix_world.inverted()
        anchors.append(empty)
    return anchors

def image_path(im,folder):
    path=pathlib.Path(bpy.path.abspath(im.filepath))
    if path.is_file():return str(path)
    if not im.packed_file:raise ValueError('图像丢失：'+im.name)
    path=pathlib.Path(folder)/(path.name or im.name+'.png');path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():path.write_bytes(bytes(im.packed_file.data))
    return str(path)

def source_adapter(original,row,instance,config):
    name=core.datablock_name(f'EF Source / {instance} / {original.name}');proxy=bpy.data.materials.get(name)
    if not proxy:proxy=original.copy();proxy.name=name
    proxy.use_fake_user=True;proxy.use_nodes=True
    for prop in ['ef_source_name','ef_resolved_source_path']:
        if prop in proxy:del proxy[prop]
    im=row.base_image
    folder=pathlib.Path(config['textures_dir'])/'mapped_sources'/instance
    if im:path=image_path(im,folder)
    else:
        import numpy as np
        from . import maps
        color=tuple(original.diffuse_color)
        if original.node_tree:
            bsdf=next((n for n in original.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
            if bsdf:color=tuple(bsdf.inputs['Base Color'].default_value)
        rgba=np.ones((16,16,4),np.float32);rgb=np.array(color[:3]);rgba[:,:,:3]=np.where(rgb<=.0031308,rgb*12.92,1.055*np.power(np.maximum(rgb,0),1/2.4)-.055)
        folder.mkdir(parents=True,exist_ok=True);path=str(folder/(hashlib.sha256(original.name.encode()).hexdigest()[:12]+'_color.png'));maps.png_write(path,rgba);im=bpy.data.images.load(path,check_existing=True)
    n=proxy.node_tree.nodes.get('mmd_base_tex') or core.node(proxy.node_tree,'ShaderNodeTexImage','mmd_base_tex');n.image=im
    proxy['ef_resolved_source_path']=path
    group=bpy.data.node_groups.get('EF Mapped Source Controls')
    if not group:
        group=bpy.data.node_groups.new('EF Mapped Source Controls','ShaderNodeTree')
        a=group.interface.new_socket(name='Alpha',in_out='INPUT',socket_type='NodeSocketFloat');a.default_value=1.
        a=group.interface.new_socket(name='Diffuse Color',in_out='INPUT',socket_type='NodeSocketColor');a.default_value=(1,1,1,1)
    old=proxy.node_tree.nodes.get('mmd_shader')
    if old:proxy.node_tree.nodes.remove(old)
    controls=core.node(proxy.node_tree,'ShaderNodeGroup','mmd_shader');controls.node_tree=group;controls.inputs['Alpha'].default_value=row.opacity
    source_controls=original.node_tree.nodes.get('mmd_shader') if original.node_tree else None
    if row.base_image and source_controls and 'Diffuse Color' in source_controls.inputs:
        controls.inputs['Diffuse Color'].default_value=source_controls.inputs['Diffuse Color'].default_value
    return proxy

def apply_material(obj,row,instance,config,cache):
    original=row.material;original.use_fake_user=True
    if row.role=='skip':
        name=core.datablock_name(f'EF::{instance}::{original.name}');mat=bpy.data.materials.get(name) or original.copy();mat.name=name
        mat['ef_source_name']=original.name;mat['ef_character']=instance;mat['ef_role']='skip';mat['ef_custom_role']='skip';return mat,{'material':mat.name,'role':'skip'}
    proxy=source_adapter(original,row,instance,config);role='detail' if row.role=='brow' else row.role
    options=dict(config);options['map_overrides']={};options['material_name']=f'EF::{instance}::{original.name}';options['preserve_diffuse_tint']=True
    folder=pathlib.Path(config['textures_dir'])/'mapped_sources'/instance
    for field,channel in [('normal_image','N'),('packed_image','P'),('hair_normal_image','HN'),('emission_image','E'),('roughness_image','Roughness'),('metallic_image','Metallic'),('ao_image','AO'),('rmo_image','RMO')]:
        im=getattr(row,field)
        if im:options['map_overrides'][channel]=image_path(im,folder)
    mat,record=core.apply_material(proxy,role,instance,options,cache)
    from .autodetect import IMAGE_FIELDS
    auto=json.loads(row.auto_images or '{}')
    for kind,path in record.get('maps',{}).items():
        if kind=='D' or kind not in IMAGE_FIELDS or not isinstance(path,str):continue
        field=IMAGE_FIELDS[kind]
        if not getattr(row,field):
            im=bpy.data.images.load(path,check_existing=True);setattr(row,field,im);auto[kind]=im.name
    row.auto_images=json.dumps(auto,ensure_ascii=False)
    if record.get('maps'):row.map_status='贴图已就绪：'+', '.join(k for k in ['N','P','HN','E'] if k in record['maps'])
    mat['ef_source_name']=original.name;mat['ef_custom_role']=row.role;mat['ef_custom_opacity']=row.opacity;record['source']=original.name
    if role not in ['face','eye','detail','overlay']:
        t=mat.node_tree;out=next(n for n in t.nodes if n.type=='OUTPUT_MATERIAL');surface=out.inputs['Surface'].links[0].from_socket
        alpha=core.node(t,'ShaderNodeMath','Mapped opacity',250,-200);alpha.operation='MULTIPLY';alpha.inputs[1].default_value=row.opacity
        diffuse=t.nodes.get('D | Original base color')
        if diffuse:t.links.new(diffuse.outputs['Alpha'],alpha.inputs[0])
        else:alpha.inputs[0].default_value=1.
        tr=core.node(t,'ShaderNodeBsdfTransparent','Mapped cutout',250,-350);mix=core.node(t,'ShaderNodeMixShader','Mapped alpha',500,100)
        t.links.new(alpha.outputs[0],mix.inputs[0]);t.links.new(tr.outputs[0],mix.inputs[1]);t.links.new(surface,mix.inputs[2]);t.links.new(mix.outputs[0],out.inputs[0])
    return mat,record

def finish(obj,instance,data):
    from . import skin_match
    for mat in obj.data.materials:
        role=mat.get('ef_role')
        if role=='skip':continue
        if role=='face':pass  # Calibrate after all body skin presets are ready.
        else:
            sh=next((n for n in mat.node_tree.nodes if n.type=='GROUP' and n.node_tree and n.node_tree.name in [core.BASE,core.HAIR]),None)
            if sh:
                preset='M_actor_pelica_hair_01' if role=='hair' else ('M_actor_laevat_body_01' if role=='skin' else 'M_actor_pelica_cloth_01')
                values=next(v for v in data['materials'][preset] if v['group']==sh.node_tree.name)['values']
                for n,v in values.items():
                    if n in sh.inputs and not sh.inputs[n].is_linked and not n.startswith('_D'):core.set_input(sh,n,v)
                if role in ['skin','fur','cloth']:core.set_input(sh,'MetallicMax',0. if role in ['skin','fur'] else 1.)
                if role=='hair':
                    for n,v in [('Rim_ColorStrength',2.),('Rim_width_X',.02),('Rim_width_Y',.012),('BaseColor',(.9,.9,.9,1))]:core.set_input(sh,n,v)
                skin_match.surface_defaults(sh,role,mat)
        mat['ef_style_preset']='Mapped '+str(role)
    for mat in obj.data.materials:
        if mat.get('ef_role')=='face':skin_match.apply(obj,mat,getattr(obj.ef_custom,'auto_skin_tone',True))
    from . import style
    style.bind_uv(obj);obj['ef_style_matched']=True

def export_mapping(obj):
    cfg=obj.ef_custom
    from .autodetect import IMAGE_FIELDS
    return {'schema':1,'head_bone':cfg.head_bone,'forward_axis':cfg.forward_axis,'up_axis':cfg.up_axis,'auto_skin_tone':getattr(cfg,'auto_skin_tone',True),'materials':[{'material':r.material.name,'role':r.role,'opacity':r.opacity,**{f:(getattr(r,f).name if getattr(r,f) else None) for f in IMAGE_FIELDS.values()}} for r in cfg.materials if r.material]}

def import_mapping(obj,data):
    if data.get('schema')!=1:raise ValueError('不支持此材质映射格式')
    cfg=obj.ef_custom;populate(obj)
    for field in ['head_bone','forward_axis','up_axis']:setattr(cfg,field,data[field])
    cfg.auto_skin_tone=data.get('auto_skin_tone',True)
    source={r['material']:r for r in data['materials']}
    for row in cfg.materials:
        found=source.get(row.material.name)
        if not found:continue
        row.role=found['role'];row.opacity=found.get('opacity',1.)
        row.auto_role='IMPORTED';row.auto_images='{}'
        from .autodetect import alpha_of
        row.auto_opacity=alpha_of(row.material)
        from .autodetect import IMAGE_FIELDS
        for f in IMAGE_FIELDS.values():
            setattr(row,f,bpy.data.images.get(found.get(f) or ''))
    cfg.confirmed=False
