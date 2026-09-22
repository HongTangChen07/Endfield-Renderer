"""Live adapters for the six geometry-node modifiers in the supplied reference.

Wrappers isolate material regions on combined
MMD meshes. Base topology and shape keys are never baked or deleted.
"""
import bpy,pathlib,json
from .core import node,head_controls
from .profiles import PROFILES

REF_NAMES=['日光方向传递','脸方向向量','平滑描边','光线投射','眼透位移','Shadow Proxy']
MATS=['Only Shadow Proxy','42Commom_outline','42FaceCommom_outline','42hair_outline']

def load_library(path):
    path=pathlib.Path(path)
    if not path.is_file():raise FileNotFoundError(path)
    missing=[n for n in REF_NAMES if 'EF Ref | '+n not in bpy.data.node_groups]
    mm=[n for n in MATS if 'EF Ref | '+n not in bpy.data.materials]
    with bpy.data.libraries.load(str(path),link=False) as (a,b):
        b.node_groups=[('EF Ref | '+n if 'EF Ref | '+n in a.node_groups else n) for n in missing]
        b.materials=[('EF Ref | '+n if 'EF Ref | '+n in a.materials else n) for n in mm]
    for n,g in zip(missing,b.node_groups):
        if g is None:raise ValueError('参考库中缺少修改器：'+n)
        g.name='EF Ref | '+n;g['ef_reference_source']=n
    for n,m in zip(mm,b.materials):
        if m is None:raise ValueError('参考库中缺少材质：'+n)
        m.name='EF Ref | '+n
    # Keep the untouched templates through save/reopen, even when only their
    # adapted copies are in the live stack. Appending does not retain fake users.
    for n in REF_NAMES:bpy.data.node_groups['EF Ref | '+n].use_fake_user=True
    for n in MATS:bpy.data.materials['EF Ref | '+n].use_fake_user=True

def group(name):
    g=bpy.data.node_groups.get(name)
    if g:g.nodes.clear()
    else:
        g=bpy.data.node_groups.new(name,'GeometryNodeTree')
        g.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        g.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    gi=node(g,'NodeGroupInput','Original geometry',-800,300)
    go=node(g,'NodeGroupOutput','Modified geometry',900,300)
    return g,gi,go

def ngmod(obj,name,g):
    m=obj.modifiers.get(name) or obj.modifiers.new(name,'NODES')
    m.node_group=g;m.show_viewport=True;m.show_render=True;m.show_in_editmode=True
    return m

def selection(g,materials,label,x=-700,y=0):
    last=None
    for i,mat in enumerate(materials):
        n=node(g,'GeometryNodeMaterialSelection',label+' / '+mat.name,x,y-i*120);n.inputs['Material'].default_value=mat
        if last is None:last=n.outputs[0]
        else:
            combine=node(g,'FunctionNodeBooleanMath',label+' union '+str(i),x+210,y-i*120);combine.operation='OR';g.links.new(last,combine.inputs[0]);g.links.new(n.outputs[0],combine.inputs[1]);last=combine.outputs[0]
    if last is None:raise ValueError('材质区域为空：'+label)
    return last

def region(g,geometry,materials,label,x=-450,y=0):
    mask=selection(g,materials,label,x-450,y-200)
    sep=node(g,'GeometryNodeSeparateGeometry',label,x,y);sep.domain='FACE';g.links.new(geometry,sep.inputs['Geometry']);g.links.new(mask,sep.inputs['Selection'])
    return sep

def copy_ref(name,destination):
    g=bpy.data.node_groups.get(destination)
    if g:return g
    g=bpy.data.node_groups['EF Ref | '+name].copy();g.name=destination;g['ef_reference_source']=name;return g

def bind_light(obj,key,light,controls):
    pointers=[]
    for name,z in [('EF_Reference_LC',0),('EF_Reference_LF',-1)]:
        o=bpy.data.objects.get(name)
        if not o:o=bpy.data.objects.new(name,None);o.empty_display_size=.025
        if o.name not in bpy.context.scene.objects:controls.objects.link(o)
        o.parent=light;o.location=(0,0,z);o.rotation_euler=(0,0,0);o.scale=(1,1,1);pointers.append(o)
    g=copy_ref('日光方向传递','EF Reference Sun Direction')
    # Source subtracts LC - LF; retain the reference math and rebind its points.
    g.nodes['物体信息.001'].inputs['Object'].default_value=pointers[0]
    g.nodes['物体信息'].inputs['Object'].default_value=pointers[1]
    ngmod(obj,'EF 01 日光方向传递',g)

def bind_head(obj,key,controls):
    anchors=head_controls(obj,key,controls)
    g=copy_ref('脸方向向量','EF Reference Head Direction (MMD basis)')
    # These imported rigs use forward -Y, character-right -X, and up +Z.
    # Adapt the reference's cross-product order without moving rig controls.
    cross=g.nodes['Vector Math.004']
    g.links.new(g.nodes['转接点.001'].outputs[0],cross.inputs[0])
    g.links.new(g.nodes['转接点'].outputs[0],cross.inputs[1])
    g['ef_coordinate_adapter']='headUp = headRight cross headForward'
    m=ngmod(obj,'EF 02 脸方向向量',g)
    m['Socket_0']=anchors[0];m['Socket_2']=anchors[1];m['Socket_3']=anchors[2];m['Socket_4']=False
    return anchors

def prepare_normals(obj,key):
    g,gi,go=group(f'EF {key} Outline Attributes')
    normal=node(g,'GeometryNodeInputNormal','Evaluated surface normal',-600,0)
    st=node(g,'GeometryNodeStoreNamedAttribute','smoothnormalWS',-200,300);st.data_type='FLOAT_VECTOR';st.domain='POINT';st.inputs['Name'].default_value='smoothnormalWS'
    g.links.new(gi.outputs[0],st.inputs['Geometry']);g.links.new(normal.outputs[0],st.inputs['Value'])
    uv=node(g,'GeometryNodeInputNamedAttribute','Original UV',-600,-200);uv.data_type='FLOAT_VECTOR';uv.inputs['Name'].default_value=obj.data.uv_layers.active.name
    su=node(g,'GeometryNodeStoreNamedAttribute','Reference UV0 alias',150,300);su.data_type='FLOAT_VECTOR';su.domain='CORNER';su.inputs['Name'].default_value='UV0'
    g.links.new(st.outputs[0],su.inputs['Geometry']);g.links.new(uv.outputs['Attribute'],su.inputs['Value']);g.links.new(su.outputs[0],go.inputs[0])
    ngmod(obj,'EF 03 描边法线与UV',g)

def outline_material(key,role):
    suffix={'face':'42FaceCommom_outline','hair':'42hair_outline','body':'42Commom_outline'}[role]
    name=f'EF::{key}::Outline {role}'
    m=bpy.data.materials.get(name)
    if not m:m=bpy.data.materials['EF Ref | '+suffix].copy();m.name=name
    m.use_backface_culling=True;m.shadow_method='NONE'
    if role=='hair':
        col={'Nico':(.11,.060,.024,1),'Suomi':(.065,.034,.020,1),'Tevelos':(.055,.025,.07,1)}.get(key,(.055,.035,.025,1))
        n=m.node_tree.nodes.get('混合.001')
        if n:
            for s in n.inputs:
                if s.identifier=='A_Color':s.default_value=col
    return m

def add_outline(obj,key,roles):
    g,gi,go=group(f'EF {key} Material Scoped Outlines');remaining=gi.outputs[0]
    joins=node(g,'GeometryNodeJoinGeometry','Join three outline regions',650,300)
    exclusions={'裙内','裙内2','带内','Cloth1Alpha1','Cloth1Alpha2','Cloth2Alpha','Cloth6Alpha','Cloth1B','Hair.001'}
    report={}
    for i,role in enumerate(['body','hair','face']):
        if role=='body':mats=[m for m in obj.data.materials if roles[m.name] in ['skin','cloth','metal','glass','fur'] and m.get('ef_source_name',m.name) not in exclusions]
        else:mats=[m for m in obj.data.materials if roles[m.name]==role and m.get('ef_source_name',m.name) not in exclusions]
        if not mats:continue
        sep=region(g,remaining,mats,role,-200,-i*400)
        ref=node(g,'GeometryNodeGroup','平滑描边 | '+role,200,-i*400);ref.node_tree=bpy.data.node_groups['EF Ref | 平滑描边']
        g.links.new(sep.outputs['Selection'],ref.inputs[0]);remaining=sep.outputs['Inverted']
        widths={'body':.00065,'hair':.0006,'face':.00045} if obj.get('ef_style_matched') else {'body':.0010,'hair':.00085,'face':.00055}
        ref.inputs['描边宽度'].default_value=widths[role]
        ref.inputs['描边材质'].default_value=outline_material(key,role)
        ref.inputs['使用顶点色控制'].default_value=False;ref.inputs['使用ST'].default_value=False;ref.inputs['Use material filtering'].default_value=False
        if key=='Tevelos' and role=='hair':
            source=bpy.data.materials['发'].node_tree.nodes['mmd_base_tex'].image
            path=pathlib.Path(bpy.path.abspath(source.filepath)).parent.parent/'other tex/T_actor_typhoea_hair_01_ST.png'
            if path.is_file():
                im=bpy.data.images.load(str(path),check_existing=True);im.colorspace_settings.name='Non-Color';ref.inputs['_ST'].default_value=im;ref.inputs['使用ST'].default_value=True
        g.links.new(ref.outputs[0],joins.inputs[0]);report[role]={'materials':[m.name for m in mats],'width':ref.inputs['描边宽度'].default_value,'ST':ref.inputs['使用ST'].default_value}
    g.links.new(remaining,joins.inputs[0]);g.links.new(joins.outputs[0],go.inputs[0]);ngmod(obj,'EF 04 平滑描边',g)
    return report

def add_raycast(obj,key,roles):
    # FaceMat explicitly references the corresponding target face material.
    m=ngmod(obj,'EF 05 光线投射',bpy.data.node_groups['EF Ref | 光线投射'])
    m['Socket_2']=next(m for m in obj.data.materials if roles[m.name]=='face')

def overlay_material(base,key,role):
    from .autodetect import base_image,alpha_of
    name=f'EF::{key}::{role} Through Hair'
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name);m.use_nodes=True;t=m.node_tree;t.nodes.clear()
    m.blend_method='BLEND';m.shadow_method='NONE';m.show_transparent_back=False;m.use_backface_culling=True
    image=base_image(base)
    if image:
        d=node(t,'ShaderNodeTexImage','Original eye / brow texture',-600,200);d.image=image;color=d.outputs['Color'];alpha=d.outputs['Alpha']
    else:
        d=node(t,'ShaderNodeRGB','Original eye / brow color',-600,200);d.outputs[0].default_value=base.diffuse_color;color=d.outputs[0];alpha=None
    n=node(t,'ShaderNodeGroup','Reference Endfield Alpha',-200,200);n.node_tree=bpy.data.node_groups['Arknights: Endfield_Alpha'];n.inputs['Alpha Offset'].default_value=.80
    t.links.new(color,n.inputs['Color'])
    trans=node(t,'ShaderNodeBsdfTransparent','Texture cutout',-100,-100);mix=node(t,'ShaderNodeMixShader','Keep texture alpha',150,200)
    opacity=node(t,'ShaderNodeMath','Original eye opacity',-350,-100);opacity.operation='MULTIPLY';opacity.inputs[0].default_value=1.;opacity.inputs[1].default_value=base.get('ef_custom_opacity',alpha_of(base))
    if alpha:t.links.new(alpha,opacity.inputs[0])
    t.links.new(opacity.outputs[0],mix.inputs[0]);t.links.new(trans.outputs[0],mix.inputs[1]);t.links.new(n.outputs[0],mix.inputs[2])
    out=node(t,'ShaderNodeOutputMaterial','Output',400,200);t.links.new(mix.outputs[0],out.inputs['Surface'])
    return m

def eye_group():
    name='EF Reference Eye Overlay (Scoped)'
    if name in bpy.data.node_groups:return bpy.data.node_groups[name]
    g=copy_ref('眼透位移',name);gi=next(n for n in g.nodes if n.type=='GROUP_INPUT')
    # Source duplicates its entire input twice. Isolate only iris/brow faces in
    # the two overlay branches, retaining one original copy of all geometry.
    for matnode,setpos,label in [('材质选择','设置位置','Iris'),('材质选择.001','设置位置.001','Brow')]:
        sep=node(g,'GeometryNodeSeparateGeometry','EF '+label+' only',-400,0);sep.domain='FACE'
        g.links.new(gi.outputs[0],sep.inputs['Geometry']);g.links.new(g.nodes[matnode].outputs[0],sep.inputs['Selection']);g.links.new(sep.outputs['Selection'],g.nodes[setpos].inputs['Geometry'])
    sock=g.interface.new_socket(name='Overlay distance',in_out='INPUT',socket_type='NodeSocketFloat');sock.default_value=.025;sock.min_value=0;sock.max_value=.15
    g.links.new(gi.outputs['Overlay distance'],g.nodes['矢量运算.002'].inputs['Scale'])
    return g

def add_eyes(obj,key,roles):
    if obj.get('ef_custom_profile'):
        iris=next((m for m in obj.data.materials if roles[m.name]=='eye'),None)
        brow=next((m for m in obj.data.materials if roles[m.name]=='brow'),None)
        if not iris or not brow:return
        irisname=iris.get('ef_source_name',iris.name);browname=brow.get('ef_source_name',brow.name)
    else:
        irisname={'Nico':'目','Tevelos':'目.001','Suomi':'Eyes'}[key]
        browname={'Nico':'睫眉','Tevelos':'眉','Suomi':'Brows'}[key]
    iris=next(m for m in obj.data.materials if m.get('ef_source_name',m.name)==irisname)
    brow=next(m for m in obj.data.materials if m.get('ef_source_name',m.name)==browname)
    g=eye_group();m=ngmod(obj,'EF 07 眼透位移',g)
    m['Socket_4']=iris;m['Socket_5']=brow;m['Socket_6']=overlay_material(iris,key,'Iris');m['Socket_7']=overlay_material(brow,key,'Brows')
    socket=next(s for s in g.interface.items_tree if s.name=='Overlay distance');m[socket.identifier]=.025

def add_shadow_proxy(obj,key,roles):
    mats=[m for m in obj.data.materials if roles[m.name]=='hair']
    if not mats:return
    g,gi,go=group(f'EF {key} Hair Shadow Proxy')
    sep=region(g,gi.outputs[0],mats,'Hair only',-250,200)
    ref=node(g,'GeometryNodeGroup','Reference Shadow Proxy',100,200);ref.node_tree=bpy.data.node_groups['EF Ref | Shadow Proxy']
    ref.inputs['Shadow Proxy'].default_value=bpy.data.materials['EF Ref | Only Shadow Proxy'];ref.inputs['Pos Offset'].default_value=-.08;ref.inputs['Pos Debug'].default_value=False
    g.links.new(sep.outputs['Selection'],ref.inputs[0]);join=node(g,'GeometryNodeJoinGeometry','Hair proxy + rest',550,300);g.links.new(ref.outputs[0],join.inputs[0]);g.links.new(sep.outputs['Inverted'],join.inputs[0]);g.links.new(join.outputs[0],go.inputs[0])
    ngmod(obj,'EF 06 Shadow Proxy',g)

def setup(obj,key,library,light,material_roles=None):
    if (key not in PROFILES and not obj.get('ef_custom_profile')) or obj.type!='MESH':raise ValueError('请选择受支持的角色网格')
    if light is None or light.type!='LIGHT':raise ValueError('请选择主光源')
    if not obj.data.uv_layers.active:raise ValueError('角色需要可用的活动 UV 贴图')
    if not obj.get('ef_custom_profile') and (obj.find_armature() is None or '頭' not in obj.find_armature().data.bones):raise ValueError('角色需要导入时的“頭”骨骼')
    if material_roles is None and not all(m and m.get('ef_character')==key for m in obj.data.materials):raise ValueError('请先应用终末地材质配置')
    roles=material_roles or {m.name:m.get('ef_custom_role',m.get('ef_role')) for m in obj.data.materials}
    if 'Arknights: Endfield_Alpha' not in bpy.data.node_groups:raise ValueError('请先加载提供的终末地着色器资源库')
    load_library(library)
    from . import studio
    controls=studio.collection(bpy.context.scene,'EF_Controls')
    old=obj.modifiers.get('EF Lighting Attributes')
    if old:obj.modifiers.remove(old)
    # Copy the body seam weld at the reference distance, restricted to skin.
    vg=obj.vertex_groups.get('EF Body Weld') or obj.vertex_groups.new(name='EF Body Weld')
    vg.remove(list(range(len(obj.data.vertices))))
    inds={i for i,m in enumerate(obj.data.materials) if roles[m.name]=='skin'}
    verts=sorted({v for f in obj.data.polygons if f.material_index in inds for v in f.vertices})
    if verts:vg.add(verts,1.,'REPLACE')
    weld=obj.modifiers.get('EF 00 身体接缝焊接') or obj.modifiers.new('EF 00 身体接缝焊接','WELD');weld.merge_threshold=.00001;weld.mode='ALL';weld.vertex_group=vg.name
    weld.show_viewport=True;weld.show_render=True
    bind_light(obj,key,light,controls);bind_head(obj,key,controls);prepare_normals(obj,key)
    if 'hair' not in roles.values():
        old=obj.modifiers.get('EF 06 Shadow Proxy')
        if old:obj.modifiers.remove(old)
    if obj.get('ef_custom_profile') and not all(r in roles.values() for r in ['eye','brow']):
        old=obj.modifiers.get('EF 07 眼透位移')
        if old:obj.modifiers.remove(old)
    outlines=add_outline(obj,key,roles);add_raycast(obj,key,roles);add_shadow_proxy(obj,key,roles);add_eyes(obj,key,roles)
    # Reapplication preserves a predictable stack order.
    names=['EF 00 身体接缝焊接','EF 01 日光方向传递','EF 02 脸方向向量','EF 03 描边法线与UV','EF 04 平滑描边','EF 05 光线投射','EF 06 Shadow Proxy','EF 07 眼透位移']
    active_names=[name for name in names if obj.modifiers.get(name)]
    base=len([m for m in obj.modifiers if m.name not in names])
    for i,name in enumerate(active_names):obj.modifiers.move(obj.modifiers.find(name),base+i)
    obj['ef_reference_modifiers']=True;obj['ef_modifiers_library']=str(library)
    obj.update_tag()
    return {'object':obj.name,'reference_groups':REF_NAMES,'modifiers':active_names,'outlines':outlines,'weld_vertices':len(verts),'weld_threshold':.00001,'eye_overlay_distance':.025 if obj.modifiers.get('EF 07 眼透位移') else None,'hair_proxy_offset':-.08 if obj.modifiers.get('EF 06 Shadow Proxy') else None,'excluded_reference_modifier':'Mesh-specific 45-degree Edge Split on Laevat cloth2; no equivalent source part in the combined target meshes. Existing target armatures retained.'}
