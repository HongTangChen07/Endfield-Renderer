"""Reference-look application, including scene settings and cross-game face masks."""
import bpy,json,pathlib
from . import core,face_transfer

def image_file(path):
    path=pathlib.Path(path)
    if path.is_file():return bpy.data.images.load(str(path),check_existing=True)
    im=next((i for i in bpy.data.images if pathlib.Path(bpy.path.abspath(i.filepath)).name==path.name and i.packed_file),None)
    if im:return im
    raise FileNotFoundError(path)

def reference_data(scene):
    if 'ef_reference_style_json' in scene:return json.loads(scene['ef_reference_style_json'])
    path=pathlib.Path(bpy.path.abspath(scene.ef_settings.reference_library)).parent/'reference_style.json'
    return json.loads(path.read_text(encoding='utf-8'))

def native_directory(material):
    old=bpy.data.materials[material['ef_source_name']]
    return pathlib.Path(old.get('ef_resolved_source_path') or bpy.path.abspath(old.node_tree.nodes['mmd_base_tex'].image.filepath)).parent.parent/'other tex'

def face_group(key,native=None):
    name='EF Tevelos Native Face' if key=='Tevelos' else 'EF '+key+' Fitted Reference Face'
    if name in bpy.data.node_groups:return bpy.data.node_groups[name]
    g=bpy.data.node_groups['Arknights: Endfield_PBRToonBaseFace'].copy();g.name=name
    if key=='Tevelos':
        for n in g.nodes:
            if n.type=='TEX_IMAGE' and n.image and 'female_face_01_SDF' in n.image.name:
                n.image=image_file(native/'T_actor_common_female_face_02_SDF.png');n.image.colorspace_settings.name='Non-Color'
        return g
    uv=core.node(g,'ShaderNodeUVMap','Fitted Endfield face-mask UV');uv.uv_map='EF_FaceUV'
    for n in list(g.nodes):
        if n.type=='UVMAP':n.uv_map='EF_FaceUV'
        if n.type=='TEX_COORD':
            for link in list(n.outputs['UV'].links):g.links.new(uv.outputs[0],link.to_socket)
        if n.type=='TEX_IMAGE' and not n.inputs['Vector'].is_linked:g.links.new(uv.outputs[0],n.inputs['Vector'])
    # Target eye whites are separate materials. Reference-specific eye, mouth,
    # blush and chin feature masks do not fit these unrelated face topologies.
    mix=g.nodes['混合.020']
    for link in list(mix.inputs[0].links):g.links.remove(link)
    mix.inputs[0].default_value=0.
    cm=g.nodes['图像纹理.002'];rgb=core.node(g,'ShaderNodeRGB','Neutral foreign facial feature masks');rgb.outputs[0].default_value=(0,0,0,1)
    alpha=core.node(g,'ShaderNodeValue','No foreign feature alpha');alpha.outputs[0].default_value=0.
    for link in list(cm.outputs['Color'].links):g.links.new(rgb.outputs[0],link.to_socket)
    for link in list(cm.outputs['Alpha'].links):g.links.new(alpha.outputs[0],link.to_socket)
    return g

def apply_face(obj,key,data):
    if key=='Nico':
        from . import faces
        return faces.apply_nico(obj)
    mat=next(m for m in obj.data.materials if m.get('ef_role')=='face')
    source=bpy.data.materials[mat['ef_source_name']].node_tree.nodes['mmd_base_tex'].image
    native=native_directory(mat) if key=='Tevelos' else None
    if key!='Tevelos' and 'EF_FaceUV' not in obj.data.uv_layers:
        surface=pathlib.Path(bpy.context.scene['ef_reference_directory'])/'reference_face_surface.npz'
        face_transfer.fit_mask_uv(obj,surface)
    g=face_group(key,native);t=mat.node_tree;t.nodes.clear()
    d=core.node(t,'ShaderNodeTexImage','Original face color',-550,250);d.image=image_file(native/'T_actor_typhoea_face_01_D.png') if native else source
    sh=core.node(t,'ShaderNodeGroup','Reference Endfield Face',50,200);sh.node_tree=g
    preset='M_actor_laevat_face_01' if key=='Tevelos' else 'M_actor_pelica_face_01'
    for name,value in data['materials'][preset][0]['values'].items():core.set_input(sh,name,value)
    t.links.new(d.outputs['Color'],sh.inputs['_D(sRGB)R.G.B'])
    if native:t.links.new(d.outputs['Alpha'],sh.inputs['_D(sRGB).A'])
    else:
        core.set_input(sh,'_D(sRGB).A',1.);core.set_input(sh,'BaseColor',(1.03,1.03,1.03,1));core.set_input(sh,'Face Final brightness',1.0)
    shader=sh.outputs[0]
    if key=='Suomi':
        # The closest-surface fit is unstable at the unrelated mouth UV seams.
        # Blend to target-normal shading in head space below the nose.
        soft=core.node(t,'ShaderNodeGroup','Lower-face geometry shading',50,-200);soft.node_tree=core.soft_face_group();t.links.new(d.outputs['Color'],soft.inputs['Color']);soft.inputs['Brightness'].default_value=1.
        geo=core.node(t,'ShaderNodeNewGeometry','Face position',-800,-400)
        center=core.node(t,'ShaderNodeAttribute','Head center',-1000,-600);center.attribute_name='headCenter'
        up=core.node(t,'ShaderNodeAttribute','Head up',-1000,-800);up.attribute_name='headUp'
        sub=core.node(t,'ShaderNodeVectorMath','Relative to head center',-550,-450);sub.operation='SUBTRACT';t.links.new(geo.outputs['Position'],sub.inputs[0]);t.links.new(center.outputs['Vector'],sub.inputs[1])
        dot=core.node(t,'ShaderNodeVectorMath','Height in head space',-330,-450);dot.operation='DOT_PRODUCT';t.links.new(sub.outputs[0],dot.inputs[0]);t.links.new(up.outputs['Vector'],dot.inputs[1])
        ramp=core.node(t,'ShaderNodeMapRange','Smooth lower-face transition',-100,-450);ramp.interpolation_type='SMOOTHERSTEP'
        for n,v in [('From Min',-.035),('From Max',.005),('To Min',1),('To Max',0)]:ramp.inputs[n].default_value=v
        t.links.new(dot.outputs['Value'],ramp.inputs['Value'])
        mix=core.node(t,'ShaderNodeMixShader','Fitted SDF + original lower face',350,100);t.links.new(ramp.outputs[0],mix.inputs[0]);t.links.new(sh.outputs[0],mix.inputs[1]);t.links.new(soft.outputs[0],mix.inputs[2]);shader=mix.outputs[0]
    if key!='Tevelos':
        trans=core.node(t,'ShaderNodeBsdfTransparent','Original face cutouts',350,-200);mix=core.node(t,'ShaderNodeMixShader','Preserve eye and mouth openings',600,100)
        t.links.new(d.outputs['Alpha'],mix.inputs[0]);t.links.new(trans.outputs[0],mix.inputs[1]);t.links.new(shader,mix.inputs[2]);shader=mix.outputs[0]
    out=core.node(t,'ShaderNodeOutputMaterial','Output',850,200);t.links.new(shader,out.inputs['Surface'])
    mat['ef_style_preset']=preset;mat['ef_face_adapter']='native female_face_02 SDF' if native else 'fitted reference SDF with target-specific feature handling'

def bind_uv(obj):
    for mat in obj.data.materials:
        if mat.get('ef_role')=='skip':continue
        t=mat.node_tree
        if t is None:continue
        uv=t.nodes.get('Original material UV') or core.node(t,'ShaderNodeUVMap','Original material UV',-1100,400);uv.uv_map=obj.data.uv_layers.active.name
        for n in list(t.nodes):
            if n.type=='TEX_IMAGE' and not n.inputs['Vector'].is_linked:t.links.new(uv.outputs[0],n.inputs['Vector'])

def apply_characters(scene=None,targets=None):
    scene=scene or bpy.context.scene;data=reference_data(scene)
    targets=targets or [(key,bpy.data.objects[profile['object']]) for key,profile in core.PROFILES.items()]
    for key,obj in targets:
        for mat in obj.data.materials:
            role=mat.get('ef_role');sh=next((n for n in mat.node_tree.nodes if n.type=='GROUP' and n.node_tree and n.node_tree.name in [core.BASE,core.HAIR]),None)
            if not sh:continue
            if role=='hair':preset='M_actor_laevat_hair_01' if key=='Tevelos' else 'M_actor_pelica_hair_01'
            elif role=='skin':preset='M_actor_laevat_body_01'
            else:preset={'Nico':'M_actor_pelica_cloth_01','Tevelos':'M_actor_laevat_cloth_01','Suomi':'M_actor_chen_cloth_01'}[key]
            values=next(x for x in data['materials'][preset] if x['group']==sh.node_tree.name)['values']
            for name,value in values.items():
                if name in sh.inputs and not sh.inputs[name].is_linked and not name.startswith('_D'):core.set_input(sh,name,value)
            if role=='skin':core.set_input(sh,'BaseColor',(1.16,1.16,1.16,1));core.set_input(sh,'MetallicMax',0.)
            if role=='fur':core.set_input(sh,'MetallicMax',0.);core.set_input(sh,'SmoothnessMax',.5)
            if role=='hair':
                if key=='Tevelos':core.set_input(sh,'HighLightColorB',(.58,.42,.72,1));core.set_input(sh,'fresnelInsideColor',(1.6,1.25,1.85,1))
                else:
                    for name,value in [('Rim_ColorStrength',2.),('Rim_width_X',.02),('Rim_width_Y',.012),('BaseColor',(.90,.90,.90,1))]:core.set_input(sh,name,value)
            if key=='Tevelos':
                dn=next((n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.name.startswith('D |')),None)
                original=bpy.data.materials[mat['ef_source_name']].node_tree.nodes['mmd_base_tex'].image
                path=native_directory(mat)/pathlib.Path(bpy.path.abspath(original.filepath)).name
                if dn:dn.image=image_file(path);dn.image.colorspace_settings.name='sRGB'
                core.set_input(sh,'_D(sRGB).A',1.)
                cutout=mat.node_tree.nodes.get('Cutout alpha')
                if cutout:
                    op=mat.node_tree.nodes.get('MMD original opacity') or core.node(mat.node_tree,'ShaderNodeTexImage','MMD original opacity',-750,700);op.image=original
                    mat.node_tree.links.new(op.outputs['Alpha'],cutout.inputs[0])
            mat['ef_style_preset']=preset
        apply_face(obj,key,data);bind_uv(obj)
        group=bpy.data.node_groups.get('EF '+key+' Material Scoped Outlines')
        if group:
            for n in group.nodes:
                if n.type=='GROUP' and n.node_tree and n.node_tree.get('ef_reference_source')=='平滑描边':
                    n.inputs['描边宽度'].default_value=.00065 if n.name.endswith('body') else (.0006 if n.name.endswith('hair') else .00045)
        obj['ef_style_matched']=True;obj.update_tag()
    bpy.context.view_layer.update()
