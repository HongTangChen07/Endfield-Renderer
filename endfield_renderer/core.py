"""Reference-shader material adapters; geometry and rigs stay editable."""
import bpy, pathlib, json, hashlib
from mathutils import Vector,Matrix
from .profiles import PROFILES,role_for,CHANNEL_SCHEMA
from . import maps

BASE='Arknights: Endfield_PBRToonBase'
HAIR='Arknights: Endfield_PBRToonBaseHair'

def datablock_name(name):
    encoded=name.encode('utf-8')
    if len(encoded)<=63:return name
    return encoded[:51].decode('utf-8',errors='ignore')+'_'+hashlib.sha256(encoded).hexdigest()[:10]

def node(t,kind,name,x=0,y=0):
    n=t.nodes.new(kind);n.name=name;n.label=name;n.location=(x,y);return n
def set_input(n,name,v):
    if name in n.inputs:n.inputs[name].default_value=v
def tex(t,path,name,x=-650,y=0,data=False):
    n=node(t,'ShaderNodeTexImage',name,x,y)
    im=bpy.data.images.load(str(path),check_existing=True)
    if data:
        # A regenerated map may replace a file already packed in the scene.
        # Read the new disk payload; final project packing happens after validation.
        if im.packed_file:im.unpack(method='USE_ORIGINAL')
        im.reload()
    im.colorspace_settings.name='Non-Color' if data else 'sRGB'
    if data:im.alpha_mode='CHANNEL_PACKED'
    n.image=im;n.interpolation='Linear';n.extension='REPEAT'
    return n
def append_library(path):
    if not pathlib.Path(path).is_file():raise FileNotFoundError(path)
    if BASE not in bpy.data.node_groups:
        with bpy.data.libraries.load(str(path),link=False) as (a,b):
            b.node_groups=[n for n in a.node_groups if n.startswith('Arknights:')]
    for name in [BASE,HAIR]:
        if name not in bpy.data.node_groups:raise RuntimeError('参考资源库中缺少：'+name)
    return [BASE,HAIR]

def head_controls(obj,key,collection):
    if obj.get('ef_custom_profile'):
        from . import custom
        return custom.head_controls(obj,key,collection)
    arm=obj.find_armature()
    if arm is None or '頭' not in arm.data.bones:raise ValueError('此专用配置需要名为“頭”的头部骨骼')
    indices={i for i,m in enumerate(obj.data.materials) if m and (m.get('ef_source_name',m.name) in PROFILES[key]['roles']['face'])}
    ids={v for p in obj.data.polygons if p.material_index in indices for v in p.vertices}
    vs=[obj.matrix_world@obj.data.vertices[i].co for i in ids]
    center=Vector([(min(v[i] for v in vs)+max(v[i] for v in vs))/2 for i in range(3)])
    center.y+=.025
    anchors=[]
    for suffix,offset in [('HC',(0,0,0)),('HF',(0,-.2,0)),('HR',(-.2,0,0)),('HU',(0,0,.2))]:
        name=f'EF_{key}_{suffix}';o=bpy.data.objects.get(name)
        if not o:
            o=bpy.data.objects.new(name,None);collection.objects.link(o);o.empty_display_size=.025
            o.location=center+Vector(offset)
            c=o.constraints.new('CHILD_OF');c.name='Follow head pose';c.target=arm;c.subtarget='頭'
            c.inverse_matrix=(arm.matrix_world@arm.pose.bones['頭'].matrix).inverted()
        anchors.append(o)
    return anchors

def bind_attributes(obj,key,light,collection):
    anchors=head_controls(obj,key,collection)
    name=f'EF_{key}_Attributes';g=bpy.data.node_groups.get(name)
    if g is None:g=bpy.data.node_groups.new(name,'GeometryNodeTree')
    else:g.nodes.clear()
    if not len(g.interface.items_tree):
        g.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        g.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
    gi=node(g,'NodeGroupInput','Mesh',0,200);go=node(g,'NodeGroupOutput','Mesh + lighting attributes',1500,200)
    infos=[]
    for i,o in enumerate(anchors+[light]):
        n=node(g,'GeometryNodeObjectInfo',o.name,0,-i*220);n.transform_space='ORIGINAL';n.inputs['Object'].default_value=o;infos.append(n)
    vals={'headCenter':infos[0].outputs['Location']}
    for i,attr in enumerate(['headForward','headRight','headUp'],1):
        sub=node(g,'ShaderNodeVectorMath',attr+' delta',230,-i*230);sub.operation='SUBTRACT';g.links.new(infos[i].outputs['Location'],sub.inputs[0]);g.links.new(infos[0].outputs['Location'],sub.inputs[1])
        norm=node(g,'ShaderNodeVectorMath',attr+' unit',430,-i*230);norm.operation='NORMALIZE';g.links.new(sub.outputs[0],norm.inputs[0]);vals[attr]=norm.outputs[0]
    rot=node(g,'ShaderNodeVectorRotate','Sun direction',300,-1000);rot.rotation_type='EULER_XYZ';rot.inputs['Vector'].default_value=(0,0,1);g.links.new(infos[4].outputs['Rotation'],rot.inputs['Rotation']);vals['LightDirection']=rot.outputs[0]
    geometry=gi.outputs['Geometry']
    for i,(attr,value) in enumerate(vals.items()):
        st=node(g,'GeometryNodeStoreNamedAttribute',attr,650+i*180,200);st.data_type='FLOAT_VECTOR';st.domain='POINT';st.inputs['Name'].default_value=attr
        g.links.new(geometry,st.inputs['Geometry']);g.links.new(value,st.inputs['Value']);geometry=st.outputs['Geometry']
    g.links.new(geometry,go.inputs['Geometry'])
    mod=obj.modifiers.get('EF Lighting Attributes') or obj.modifiers.new('EF Lighting Attributes','NODES');mod.node_group=g;mod.show_viewport=True;mod.show_render=True
    return anchors

def soft_face_group():
    name='EF Adaptive Soft Face v1'
    if name in bpy.data.node_groups:return bpy.data.node_groups[name]
    g=bpy.data.node_groups.new(name,'ShaderNodeTree')
    for n,st,io,default in [('Color','NodeSocketColor','INPUT',(1,1,1,1)),('Shadow Tint','NodeSocketColor','INPUT',(.64,.49,.48,1)),('Brightness','NodeSocketFloat','INPUT',1.0),('Shader','NodeSocketShader','OUTPUT',None)]:
        s=g.interface.new_socket(name=n,in_out=io,socket_type=st)
        if default is not None:s.default_value=default
    gi=node(g,'NodeGroupInput','Face controls',-700,300);out=node(g,'NodeGroupOutput','Face result',700,300)
    # Smooth facial response without borrowing another character's UV-dependent SDF.
    geo=node(g,'ShaderNodeNewGeometry','Smooth face normal',-700,0)
    hf=node(g,'ShaderNodeAttribute','Head forward',-700,-250);hf.attribute_name='headForward'
    mix=node(g,'ShaderNodeVectorMath','Bias toward head front',-450,-150);mix.operation='SCALE';mix.inputs['Scale'].default_value=.32;g.links.new(hf.outputs['Vector'],mix.inputs[0])
    add=node(g,'ShaderNodeVectorMath','Face normal blend',-250,-100);add.operation='ADD';g.links.new(geo.outputs['Normal'],add.inputs[0]);g.links.new(mix.outputs[0],add.inputs[1])
    norm=node(g,'ShaderNodeVectorMath','Normalized face normal',-50,-100);norm.operation='NORMALIZE';g.links.new(add.outputs[0],norm.inputs[0])
    diff=node(g,'ShaderNodeBsdfDiffuse','Real shadow receiver',-450,100);diff.inputs['Color'].default_value=(1,1,1,1);g.links.new(norm.outputs[0],diff.inputs['Normal'])
    rgb=node(g,'ShaderNodeShaderToRGB','EEVEE lighting',-250,100);g.links.new(diff.outputs[0],rgb.inputs[0])
    ramp=node(g,'ShaderNodeValToRGB','Soft light transition',-50,160);ramp.color_ramp.interpolation='EASE';ramp.color_ramp.elements[0].position=.12;ramp.color_ramp.elements[0].color=(0,0,0,1);ramp.color_ramp.elements[1].position=.70;ramp.color_ramp.elements[1].color=(1,1,1,1);g.links.new(rgb.outputs[0],ramp.inputs[0])
    tint=node(g,'ShaderNodeMixRGB','Face light / shadow',150,200);tint.blend_type='MIX';tint.inputs[2].default_value=(1,1,1,1);g.links.new(ramp.outputs[0],tint.inputs[0]);g.links.new(gi.outputs['Shadow Tint'],tint.inputs[1])
    mul=node(g,'ShaderNodeMixRGB','Preserve face colors',350,300);mul.blend_type='MULTIPLY';mul.inputs[0].default_value=1;g.links.new(gi.outputs['Color'],mul.inputs[1]);g.links.new(tint.outputs[0],mul.inputs[2])
    em=node(g,'ShaderNodeEmission','Face radiance',550,300);g.links.new(mul.outputs[0],em.inputs['Color']);g.links.new(gi.outputs['Brightness'],em.inputs['Strength']);g.links.new(em.outputs[0],out.inputs[0])
    g['ef_note']='Adaptive smooth facial lighting; no claim of original game SDF reconstruction.'
    return g

def simple_material(m,source,role,alpha,diffuse,preserve_tint=False):
    t=m.node_tree;t.nodes.clear();out=node(t,'ShaderNodeOutputMaterial','Output',700,100)
    if source:
        d=tex(t,source,'Base Color | original sRGB');color=d.outputs['Color']
    else:
        d=None;c=node(t,'ShaderNodeRGB','Original diffuse');c.outputs[0].default_value=diffuse;color=c.outputs[0]
    if d and preserve_tint and any(abs(c-1)>1e-5 for c in diffuse[:3]):
        tint=node(t,'ShaderNodeMixRGB','Original diffuse tint',-280,100);tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1.;tint.inputs[2].default_value=diffuse;t.links.new(color,tint.inputs[1]);color=tint.outputs[0]
    if role in ['face','detail']:
        n=node(t,'ShaderNodeGroup','Adaptive Face',0,150);n.node_tree=soft_face_group();t.links.new(color,n.inputs['Color']);n.inputs['Brightness'].default_value=1.03 if role=='face' else .97
    else:
        n=node(t,'ShaderNodeEmission','Eye / overlay radiance',0,150);t.links.new(color,n.inputs['Color']);n.inputs['Strength'].default_value=1.05 if role=='eye' else 1.0
    shader=n.outputs[0]
    # Keep imported opacity, including disabled expressions and hair highlight overlays.
    transparent=node(t,'ShaderNodeBsdfTransparent','Transparent',200,-150)
    fac=node(t,'ShaderNodeMath','Original alpha',0,-200);fac.operation='MULTIPLY';fac.inputs[1].default_value=alpha
    if d:t.links.new(d.outputs['Alpha'],fac.inputs[0])
    else:fac.inputs[0].default_value=1
    mix=node(t,'ShaderNodeMixShader','Opacity',450,100);t.links.new(fac.outputs[0],mix.inputs[0]);t.links.new(transparent.outputs[0],mix.inputs[1]);t.links.new(shader,mix.inputs[2]);t.links.new(mix.outputs[0],out.inputs['Surface'])

def resolve_maps(source,role,key,out_dir,cache,resolution=2048,seed=9877,overrides=None):
    source=pathlib.Path(source);identity=(str(source),role,key,tuple(sorted((overrides or {}).items())))
    if identity in cache:return cache[identity]
    result={'D':str(source)}
    if overrides:result.update(overrides)
    if key=='Tevelos':
        directory=source.parent.parent/'other tex'
        stem=source.stem[:-2] if source.stem.endswith('_D') else source.stem
        for kind in ['P','N','HN','E']:
            path=directory/f'{stem}_{kind}.png'
            if path.is_file():result[kind]=str(path)
    if key=='Suomi':
        prefix=source.stem
        for suffix in ['_da','_d']:
            if prefix.endswith(suffix):prefix=prefix[:-len(suffix)];break
        directory=source.parent/'normalmap';rmo=directory/f'{prefix}_rmo.png';normal=directory/f'{prefix}_n.png'
        if rmo.is_file():
            dest=pathlib.Path(out_dir)/key/f'{prefix}_Endfield_P.png';dest.parent.mkdir(parents=True,exist_ok=True)
            result.update(maps.convert_rmo(rmo,dest,resolution=resolution))
        if normal.is_file():result['N']=str(normal)
    if 'P' not in result and 'RMO' in result and role!='hair':
        dest=pathlib.Path(out_dir)/key/(source.stem+'_'+hashlib.sha256(pathlib.Path(result['RMO']).read_bytes()).hexdigest()[:10]+'_Endfield_P.png')
        result.update(maps.convert_rmo(result['RMO'],dest,resolution=resolution))
    required=['P','HN'] if role=='hair' else ['P','N']
    missing={k for k in required if k not in result}
    if missing:
        kinds=missing|({k for k in ['Roughness','Metallic','AO'] if k not in result} if 'P' in missing else set())
        manifest=maps.generate(source,pathlib.Path(out_dir)/key,role,resolution=resolution,seed=seed,kinds=kinds)
        for kind,path in manifest['paths'].items():result.setdefault(kind,path)
        result['procedural_manifest']=manifest
    if 'P' in missing and overrides:
        result['P']=maps.compose_p(result['P'],overrides,pathlib.Path(out_dir)/key,role,resolution)
    cache[identity]=result;return result

def apply_material(source_mat,role,key,config,map_cache):
    old=source_mat
    if old.get('ef_source_name'):
        old=bpy.data.materials.get(old['ef_source_name'])
        if old is None:raise RuntimeError('原始材质备份丢失')
    name=datablock_name(config.get('material_name') or f'EF::{key}::{old.name}')
    m=bpy.data.materials.get(name) or old.copy();m.name=name;m.use_nodes=True
    old.use_fake_user=True;m['ef_source_name']=old.name;m['ef_character']=key;m['ef_role']=role;m['ef_version']='0.1.1'
    nodes=old.node_tree.nodes;d=nodes.get('mmd_base_tex');src=old.get('ef_resolved_source_path') or (bpy.path.abspath(d.image.filepath) if d and d.image else None)
    original=nodes.get('mmd_shader');alpha=original.inputs['Alpha'].default_value if original else 1;diffuse=list(original.inputs['Diffuse Color'].default_value) if original else [1,1,1,1]
    m.surface_render_method='DITHERED';m.use_backface_culling=False
    if hasattr(m,'use_transparent_shadow'):m.use_transparent_shadow=True
    record={'material':m.name,'source':old.name,'role':role,'base_color':src,'opacity':alpha}
    if key=='Nico' and old.name=='髮+':
        alpha=0.;record['opacity']=0.;record['adaptation']='Legacy painted highlight overlay disabled; Endfield HN/P hair shader supplies highlights.'
    if role in ['face','eye','detail','overlay'] or not src:
        simple_material(m,src,role,alpha,diffuse,config.get('preserve_diffuse_tint',False))
        if role=='overlay':
            # Goo's legacy EEVEE path needs alpha blending and no overlay shadow;
            # HASHED emission overlays contaminate Shader-to-RGB facial shading.
            m.blend_method='BLEND';m.shadow_method='NONE';m.show_transparent_back=False
        record['shader']='adaptive_face' if role in ['face','detail'] else 'original_color_overlay';return m,record
    paths=resolve_maps(src,role,key,config['textures_dir'],map_cache,resolution=config.get('resolution',2048),seed=config.get('seed',9877),overrides=config.get('map_overrides'));record['maps']=paths
    t=m.node_tree;t.nodes.clear();out=node(t,'ShaderNodeOutputMaterial','Output',700,150)
    shader=node(t,'ShaderNodeGroup','Endfield | '+role,100,200);shader.node_tree=bpy.data.node_groups[HAIR if role=='hair' and 'HN' in paths else BASE];shader.width=340
    # Use validated, restrained values; source look-up tables stay in the reference library.
    defaults={'BaseColor':(1.08,1.08,1.08,1),'SmoothnessMax':.8,'MetallicMax':1.0,'RemaphalfLambert_center':.45,'RemaphalfLambert_sharp':.16,
      'CastShadow_center':0.,'CastShadow_sharp':.17,'dirLight_lightColor':(1.,.96,.94,1),'SpecularColor':(1.25,1.25,1.25,1),
      'NormalStrength':.7,'fresnelInsideColor':(1.,1.,1.,1),'fresnelOutsideColor':(.55,.6,.68,1),'ToonfresnelPow':1.7,
      '_ToonfresnelSMO_L':0.,'_ToonfresnelSMO_H':.65,'Rim_ColorStrength':.7,'Rim_width_X':.008,'Rim_width_Y':.006,
      'GlobalShadowBrightnessAdjustment':-1.4,'Color desaturation in shaded areas attenuation':.8,'Alpha':1.0,
      'Use NormalTex?':True,'Use RS_Eff?':False,'Use Simple transmission？':False,'Emission Color':(1,1,1,1)}
    if role=='skin':defaults.update({'Is Skin?':True,'MetallicMax':0.,'SmoothnessMax':.55,'SpecularColor':(.65,.62,.61,1),'Rim_ColorStrength':.3})
    if role=='hair':defaults.update({'MetallicMax':0.,'SmoothnessMax':.15,'Use anisotropy?':True,'Aniso_SmoothnessMaxT':.2,'Aniso_SmoothnessMaxB':.65,'HighLightColorA':(.12,.11,.10,1),'HighLightColorB':(.25,.23,.22,1),'FHighLightPos':.4,'Highlight length':.035,'HNormalStrength':.5,'Final brightness':1.1,'GlobalShadowBrightnessAdjustment':-1.0,'CastShadow_center':.2,'RemaphalfLambert_center':.5,'RemaphalfLambert_sharp':.24})
    if role=='fur':defaults.update({'SmoothnessMax':.2,'MetallicMax':0.,'NormalStrength':.25})
    for k,v in defaults.items():set_input(shader,k,v)
    dn=tex(t,paths['D'],'D | Original base color',-750,400);t.links.new(dn.outputs['Color'],shader.inputs['_D(sRGB)R.G.B'])
    # D alpha is a game shading mask, not MMD opacity. Supply neutral AO for skin.
    set_input(shader,'_D(sRGB).A',1.)
    pn=tex(t,paths['P'],'P | Metal / Aux / AO / Smoothness',-750,0,True);t.links.new(pn.outputs['Color'],shader.inputs['_P(非色彩Non_Color)R.G.B']);t.links.new(pn.outputs['Alpha'],shader.inputs['_P(非色彩Non_Color)A'])
    if shader.node_tree.name==HAIR:
        nn=tex(t,paths['HN'],'HN | original hair normals',-750,-400,True);t.links.new(nn.outputs['Color'],shader.inputs['_HN(非色彩Non_Color)R.G.B']);t.links.new(nn.outputs['Alpha'],shader.inputs['_HN(非色彩Non_Color)A'])
    else:
        nn=tex(t,paths['N'],'N | tangent normal +Y',-750,-400,True);t.links.new(nn.outputs['Color'],shader.inputs['_N(非色彩Non_Color)'])
    if 'E' in paths and '_E（非色彩）' in shader.inputs:
        en=tex(t,paths['E'],'E | original emission',-750,-800,True);t.links.new(en.outputs['Color'],shader.inputs['_E（非色彩）'])
    # Only materials actually declared as alpha/cutout use D alpha for visibility.
    alpha_names={'Cloth1Alpha1','Cloth1Alpha2','Cloth2Alpha','Cloth6Alpha','Cloth1A','Cloth1B','Hair.001'}
    if old.name in alpha_names:
        tr=node(t,'ShaderNodeBsdfTransparent','Transparent',300,-250);mix=node(t,'ShaderNodeMixShader','Cutout alpha',520,150);t.links.new(dn.outputs['Alpha'],mix.inputs[0]);t.links.new(tr.outputs[0],mix.inputs[1]);t.links.new(shader.outputs[0],mix.inputs[2]);t.links.new(mix.outputs[0],out.inputs['Surface'])
    else:t.links.new(shader.outputs[0],out.inputs['Surface'])
    record['shader']=shader.node_tree.name;return m,record

def apply_all(config):
    # Reject incompatible scenes before creating or assigning any materials.
    for key,profile in PROFILES.items():
        obj=bpy.data.objects.get(profile['object'])
        if obj is None or obj.type!='MESH':raise ValueError('角色网格丢失：'+profile['object'])
        if obj.find_armature() is None or '頭' not in obj.find_armature().data.bones:raise ValueError(key+' 需要导入时的“頭”骨骼')
        for m in obj.data.materials:
            if m is None:raise ValueError(key+' 含有空材质槽')
            role_for(key,m.get('ef_source_name',m.name))
    append_library(config['reference_library'])
    from . import studio
    coll=studio.collection(bpy.context.scene,'EF_Controls')
    light=bpy.data.objects.get(config.get('light','EF_Key'))
    if not light or light.type!='LIGHT':raise ValueError('请为终末地渲染配置选择已有的灯光')
    result={'schema':CHANNEL_SCHEMA,'characters':{},'config':config}
    cache={}
    for key,profile in PROFILES.items():
        obj=bpy.data.objects.get(profile['object'])
        if not obj:raise ValueError('角色丢失：'+profile['object'])
        anchors=head_controls(obj,key,coll) if obj.get('ef_reference_modifiers') else bind_attributes(obj,key,light,coll)
        records=[]
        for i,old in enumerate(list(obj.data.materials)):
            source=old.get('ef_source_name',old.name);role=role_for(key,source)
            m,record=apply_material(old,role,key,config,cache);obj.data.materials[i]=m;records.append(record)
        obj['ef_character']=key;obj['ef_source_materials']=json.dumps([r['source'] for r in records],ensure_ascii=False)
        if obj.get('ef_reference_modifiers'):
            from . import modifiers
            modifiers.setup(obj,key,obj['ef_modifiers_library'],light)
        result['characters'][key]={'object':obj.name,'materials':records,'controls':[a.name for a in anchors]}
    if bpy.context.scene.get('ef_style_matched'):
        from . import style
        style.apply_characters()
        result['reference_style']='Applied supplied reference presets and validated face adapters'
    return result

def restore_materials(obj):
    if 'ef_source_materials' not in obj:raise ValueError('此物体没有终末地材质备份')
    names=json.loads(obj['ef_source_materials'])
    missing=[n for n in names if n not in bpy.data.materials]
    if missing:raise ValueError('原始材质丢失：'+', '.join(missing))
    if 'ef_nico_jaw_normals_backup' in obj.data:
        from . import faces
        faces.restore_jaw_normals(obj)
    for i,name in enumerate(names):obj.data.materials[i]=bpy.data.materials[name]
    for modifier in obj.modifiers:
        if modifier.name.startswith('EF '):modifier.show_viewport=False;modifier.show_render=False
