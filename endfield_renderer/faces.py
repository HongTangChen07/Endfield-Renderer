"""Target-specific face lighting, preserving the imported facial features.

Nico's original UV atlas and head controls drive this shader. It deliberately
does not sample a different character's facial SDF or shade the lips with a
smooth diffuse lobe. The generated node graph is the editable procedural asset.
"""
import bpy
import json
from . import core

NICO_GROUP='EF Nico Toon Face v1'
NICO_SKIN_TINT=(1.04,.90,.83,1)
NICO_BRIGHTNESS=.90

def reconcile_jaw_normals(obj):
    """Share only Nico's existing face/neck boundary normals; retain originals."""
    import numpy as np
    from mathutils import Vector
    me=obj.data
    if 'ef_nico_jaw_normals_backup' in me:
        saved=json.loads(me['ef_nico_jaw_normals_backup'])
        if saved['loop_count']!=len(me.loops):raise ValueError('下颌法线备份与当前网格拓扑不匹配')
        return {'shared_positions':saved['shared_positions'],'changed_corners':len(saved['normals'])}
    face={i for i,m in enumerate(me.materials) if m.get('ef_role')=='face'}
    neck={i for i,m in enumerate(me.materials) if m.get('ef_source_name')=='肌'}
    groups={}
    for poly in me.polygons:
        if poly.material_index not in face|neck:continue
        label='face' if poly.material_index in face else 'neck'
        for li in poly.loop_indices:
            co=me.vertices[me.loops[li].vertex_index].co
            if not 1.5<co.z<1.565:continue
            groups.setdefault(tuple(round(x,5) for x in co),{}).setdefault(label,[]).append(li)
    normals=np.empty(len(me.corner_normals)*3,dtype=np.float32);me.corner_normals.foreach_get('vector',normals);normals=normals.reshape(-1,3)
    backup={};positions=0
    for by_material in groups.values():
        if len(by_material)!=2:continue
        loops=by_material['face']+by_material['neck'];normal=Vector(np.mean(normals[loops],axis=0)).normalized();positions+=1
        for li in loops:backup[str(li)]=normals[li].tolist();normals[li]=normal
    if not backup:raise ValueError('未找到尼可面部与颈部的交界处')
    me['ef_nico_jaw_normals_backup']=json.dumps({'loop_count':len(me.loops),'shared_positions':positions,'normals':backup})
    me.normals_split_custom_set(normals.tolist());me.update()
    return {'shared_positions':positions,'changed_corners':len(backup)}

def restore_jaw_normals(obj):
    """Restore the imported boundary normals without altering other normals."""
    import numpy as np
    me=obj.data
    if 'ef_nico_jaw_normals_backup' not in me:return
    saved=json.loads(me['ef_nico_jaw_normals_backup'])
    if saved['loop_count']!=len(me.loops):raise ValueError('创建法线备份后，网格拓扑发生了变化')
    normals=np.empty(len(me.corner_normals)*3,dtype=np.float32);me.corner_normals.foreach_get('vector',normals);normals=normals.reshape(-1,3)
    for li,normal in saved['normals'].items():normals[int(li)]=normal
    me.normals_split_custom_set(normals.tolist());me.update();del me['ef_nico_jaw_normals_backup']

def nico_group():
    if NICO_GROUP in bpy.data.node_groups:return bpy.data.node_groups[NICO_GROUP]
    g=bpy.data.node_groups.new(NICO_GROUP,'ShaderNodeTree')
    for name,typ,io,value in [
        ('Color','NodeSocketColor','INPUT',(1,1,1,1)),
        ('Skin Tint','NodeSocketColor','INPUT',NICO_SKIN_TINT),
        ('Shadow Tint','NodeSocketColor','INPUT',(.68,.49,.46,1)),
        ('Shadow Softness','NodeSocketFloat','INPUT',.065),
        ('Nose Shadow','NodeSocketFloat','INPUT',.30),
        ('Nose Highlight','NodeSocketFloat','INPUT',.10),
        ('Brightness','NodeSocketFloat','INPUT',NICO_BRIGHTNESS),
        ('Shader','NodeSocketShader','OUTPUT',None)]:
        sock=g.interface.new_socket(name=name,in_out=io,socket_type=typ)
        if value is not None:sock.default_value=value
    ni=0
    def node(typ,name):
        nonlocal ni
        n=core.node(g,typ,name,(ni%6)*220-1320,-(ni//6)*220);ni+=1;return n
    def setval(socket,value):
        if isinstance(value,bpy.types.NodeSocket):g.links.new(value,socket)
        else:socket.default_value=value
    def math(op,name,a,b=None):
        n=node('ShaderNodeMath',name);n.operation=op;setval(n.inputs[0],a)
        if b is not None:setval(n.inputs[1],b)
        return n.outputs[0]
    def vector(op,name,a,b=None):
        n=node('ShaderNodeVectorMath',name);n.operation=op;setval(n.inputs[0],a)
        if b is not None:setval(n.inputs['Scale'] if op=='SCALE' else n.inputs[1],b)
        return n.outputs['Value'] if op in ['DOT_PRODUCT','LENGTH','DISTANCE'] else n.outputs[0]
    def ramp(name,value,low,high):
        n=node('ShaderNodeMapRange',name);n.clamp=True;n.interpolation_type='SMOOTHSTEP'
        setval(n.inputs['Value'],value);setval(n.inputs['From Min'],low);setval(n.inputs['From Max'],high)
        return n.outputs[0]
    def mix(name,a,b,fac=1.,blend='MIX'):
        n=node('ShaderNodeMixRGB',name);n.blend_type=blend;setval(n.inputs[0],fac);setval(n.inputs[1],a);setval(n.inputs[2],b);return n.outputs[0]
    gi=node('NodeGroupInput','Face controls')
    attrs={}
    for name in ['LightDirection','headCenter','headRight','headForward','headUp']:
        n=node('ShaderNodeAttribute',name);n.attribute_name=name;attrs[name]=n.outputs['Vector']
    geo=node('ShaderNodeNewGeometry','Original surface')
    rel=vector('SUBTRACT','Position relative to animated head',geo.outputs['Position'],attrs['headCenter'])
    # A head-space radial lighting normal suppresses lip/chin bulges without
    # changing a vertex, custom normal, shape key or rig weight.
    x=vector('DOT_PRODUCT','Head-space cheek position',rel,attrs['headRight'])
    x=math('MULTIPLY','Cheek width / Nico profile',x,1.10)
    f=vector('DOT_PRODUCT','Original face depth',rel,attrs['headForward'])
    smooth=vector('ADD','Feature-neutral lighting normal',vector('SCALE','Cheek component',attrs['headRight'],x),vector('SCALE','Front component',attrs['headForward'],f))
    smooth=vector('NORMALIZE','Normalized radial face lighting',smooth)
    light=vector('NORMALIZE','Normalized reference light',attrs['LightDirection'])
    ndl=vector('DOT_PRODUCT','Head lighting',smooth,light)
    lit=ramp('Toon cheek boundary',ndl,.12,math('ADD','Boundary softness',.12,gi.outputs['Shadow Softness']))
    # Head-forward diffuse receives cast shadows without reintroducing the
    # unwanted smooth nose and lip shading from the original surface normal.
    diffuse=node('ShaderNodeBsdfDiffuse','Hair cast-shadow receiver');diffuse.inputs['Color'].default_value=(1,1,1,1);setval(diffuse.inputs['Normal'],attrs['headForward'])
    rgb=node('ShaderNodeShaderToRGB','EEVEE cast shadow');setval(rgb.inputs[0],diffuse.outputs[0])
    cast=ramp('Cast shadow threshold',rgb.outputs[0],.055,.16)
    lit=math('MINIMUM','Combined toon and cast shadows',lit,cast)
    shade=mix('Warm reference-style shadow',gi.outputs['Shadow Tint'],(1,1,1,1),lit)
    # The native atlas puts the nose tip near (0.5, 0.442). Keep the accent
    # on that landmark; the mouth region receives no extra normal-based lobe.
    uv=node('ShaderNodeUVMap','Nico native face UV');uv.uv_map='UVMap'
    sep=node('ShaderNodeSeparateXYZ','Native face coordinates');setval(sep.inputs[0],uv.outputs[0])
    ux=math('DIVIDE','Nose horizontal radius',math('SUBTRACT','Nose center U',sep.outputs[0],.5),.023)
    vy=math('DIVIDE','Nose vertical radius',math('SUBTRACT','Nose center V',sep.outputs[1],.442),.038)
    radius=math('ADD','Nose ellipse',math('MULTIPLY','Nose U squared',ux,ux),math('MULTIPLY','Nose V squared',vy,vy))
    mask=math('SUBTRACT','Native nose mask',1.,ramp('Nose mask feather',radius,.45,1.))
    normal_light=vector('DOT_PRODUCT','Nose surface light',geo.outputs['Normal'],light)
    dark=math('SUBTRACT','Nose shadow side',1.,ramp('Small nose shadow boundary',normal_light,.32,.43))
    dark=math('MULTIPLY','Nose shadow amount',math('MULTIPLY','Nose shadow mask',mask,dark),gi.outputs['Nose Shadow'])
    shade=mix('Controlled nose shadow',shade,gi.outputs['Shadow Tint'],dark)
    bright=math('MULTIPLY','Small nose highlight',math('MULTIPLY','Lit nose mask',mask,ramp('Nose highlight boundary',normal_light,.84,.91)),gi.outputs['Nose Highlight'])
    bright=math('MULTIPLY','Highlight only in light',bright,lit)
    shade=mix('Subtle nose highlight',shade,(1.3,1.24,1.18,1),bright)
    color=mix('Original texture and skin tint',gi.outputs['Color'],gi.outputs['Skin Tint'],blend='MULTIPLY')
    color=mix('Texture-preserving toon lighting',color,shade,blend='MULTIPLY')
    em=node('ShaderNodeEmission','Face radiance');setval(em.inputs['Color'],color);setval(em.inputs['Strength'],gi.outputs['Brightness'])
    out=node('NodeGroupOutput','Face result');setval(out.inputs[0],em.outputs[0])
    g['ef_note']='Nico native UV/head-space toon adaptation; no recovered game SDF claim.'
    return g

def jaw_transition(obj,t,color,face_shader):
    """Blend the underside into the same Endfield skin response as the neck.

    The lower mouth stays outside this mask. Head-space positions make the
    transition follow the existing rig without modifying mesh normals or UVs.
    """
    neck=next(m for m in obj.data.materials if m.get('ef_source_name')=='肌')
    source=next(n for n in neck.node_tree.nodes if n.type=='GROUP' and n.node_tree.name==core.BASE)
    skin=core.node(t,'ShaderNodeGroup','Jaw uses neck skin shading',250,-350);skin.node_tree=source.node_tree
    for i in source.inputs:
        if hasattr(i,'default_value') and not i.is_linked:
            core.set_input(skin,i.name,i.default_value)
    t.links.new(color,skin.inputs['_D(sRGB)R.G.B'])
    core.set_input(skin,'Use NormalTex?',False)
    core.set_input(skin,'_P(非色彩Non_Color)R.G.B',(0,.5,1))
    core.set_input(skin,'_P(非色彩Non_Color)A',.45)
    geo=core.node(t,'ShaderNodeNewGeometry','Jaw original surface',-1600,-450)
    attrs={}
    for j,name in enumerate(['headCenter','headForward','headUp']):
        n=core.node(t,'ShaderNodeAttribute','Jaw '+name,-1800,-650-j*170);n.attribute_name=name;attrs[name]=n.outputs['Vector']
    def vec(op,name,a,b,x,y):
        n=core.node(t,'ShaderNodeVectorMath',name,x,y);n.operation=op;t.links.new(a,n.inputs[0]);t.links.new(b,n.inputs[1]);return n.outputs['Value'] if op=='DOT_PRODUCT' else n.outputs[0]
    rel=vec('SUBTRACT','Jaw relative to animated head',geo.outputs['Position'],attrs['headCenter'],-1400,-600)
    depth=vec('DOT_PRODUCT','Jaw head-space depth',rel,attrs['headForward'],-1200,-650)
    height=vec('DOT_PRODUCT','Jaw head-space height',rel,attrs['headUp'],-1200,-850)
    down=vec('DOT_PRODUCT','Jaw downward surface',geo.outputs['Normal'],attrs['headUp'],-1200,-1050)
    def mask(name,v,a,b,x,y):
        n=core.node(t,'ShaderNodeMapRange',name,x,y);n.clamp=True;n.interpolation_type='SMOOTHSTEP';t.links.new(v,n.inputs['Value'])
        for k,value in [('From Min',a),('From Max',b),('To Min',1.),('To Max',0.)]:n.inputs[k].default_value=value
        return n.outputs[0]
    def math(op,name,a,b,x,y):
        n=core.node(t,'ShaderNodeMath',name,x,y);n.operation=op;t.links.new(a,n.inputs[0]);t.links.new(b,n.inputs[1]);return n.outputs[0]
    back=mask('Jaw rear transition',depth,.034,.048,-950,-450)
    lower=mask('Keep transition below cheeks',height,-.037,-.017,-950,-650)
    rear=math('MULTIPLY','Rear jaw region',back,lower,-700,-500)
    chin=mask('Keep chin response below mouth',height,-.080,-.074,-950,-850)
    underside=mask('Under-chin normal region',down,-.90,-.30,-950,-1050)
    chin=math('MULTIPLY','Under-chin region',chin,underside,-700,-900)
    region=math('MAXIMUM','Jaw and chin transition mask',rear,chin,-450,-650)
    mix=core.node(t,'ShaderNodeMixShader','Continuous face-to-neck shading',550,200);t.links.new(region,mix.inputs[0]);t.links.new(face_shader,mix.inputs[1]);t.links.new(skin.outputs[0],mix.inputs[2])
    return mix.outputs[0]

def apply_nico(obj,material=None):
    reconcile_jaw_normals(obj)
    mat=material or next(m for m in obj.data.materials if m.get('ef_role')=='face')
    source=bpy.data.materials[mat['ef_source_name']].node_tree.nodes['mmd_base_tex'].image
    t=mat.node_tree;t.nodes.clear()
    uv=core.node(t,'ShaderNodeUVMap','Original material UV',-750,200);uv.uv_map='UVMap'
    tex=core.node(t,'ShaderNodeTexImage','Original face color',-500,200);tex.image=source;t.links.new(uv.outputs[0],tex.inputs[0])
    sh=core.node(t,'ShaderNodeGroup','Nico native feature-preserving toon face',-100,200);sh.node_tree=nico_group();sh.width=300;t.links.new(tex.outputs['Color'],sh.inputs['Color'])
    # Set the calibrated tone explicitly when rebuilding an older saved group.
    sh.inputs['Skin Tint'].default_value=NICO_SKIN_TINT
    sh.inputs['Brightness'].default_value=NICO_BRIGHTNESS
    shader=jaw_transition(obj,t,tex.outputs['Color'],sh.outputs[0])
    trans=core.node(t,'ShaderNodeBsdfTransparent','Original cutouts',100,-150)
    mix=core.node(t,'ShaderNodeMixShader','Preserve original face alpha',800,200);t.links.new(tex.outputs['Alpha'],mix.inputs[0]);t.links.new(trans.outputs[0],mix.inputs[1]);t.links.new(shader,mix.inputs[2])
    out=core.node(t,'ShaderNodeOutputMaterial','Output',1050,200);t.links.new(mix.outputs[0],out.inputs['Surface'])
    mat['ef_face_adapter']='Nico native toon face with continuous jaw/neck shading v2'
    mat['ef_style_preset']='Nico facial features / reference lighting'
    return mat
