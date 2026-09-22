"""Per-character face color calibration; original images and Nico stay intact."""
import bpy,json,numpy as np
from . import core,faces

GROUP='EF Generic Skin Response v3'
FACE_NODE='Environment-matched face'

def linear(c):return np.where(c<=.04045,c/12.92,((c+.055)/1.055)**2.4)

def median(values,weights):
    result=[]
    for i in range(3):
        order=np.argsort(values[:,i]);cum=np.cumsum(weights[order]);result.append(values[order[np.searchsorted(cum,cum[-1]*.5)],i])
    return np.array(result)

def sample_material(obj,mat):
    """Area-weight UV samples instead of counting densely triangulated eyes/lips."""
    from . import autodetect
    texture=next((mat.node_tree.nodes.get(n) for n in ['Original face color','D | Original base color','Base Color | original sRGB'] if mat.node_tree and mat.node_tree.nodes.get(n)),None)
    im=texture.image if texture and texture.type=='TEX_IMAGE' else autodetect.base_image(mat)
    if im is None:return None
    # Image.pixels are scene-linear for sRGB images. Read a copy to avoid changing
    # the source image's color space or packed data during calibration.
    import pathlib
    from . import maps
    path=pathlib.Path(bpy.path.abspath(im.filepath))
    if path.is_file():pixels=linear(maps.read_pixels(path,1024)[:,:,:3])
    else:
        if not im.has_data:return None
        a=np.empty(len(im.pixels),dtype=np.float32);im.pixels.foreach_get(a);pixels=a.reshape(im.size[1],im.size[0],4)[:,:,:3]
    h,w=pixels.shape[:2];slots={i for i,m in enumerate(obj.data.materials) if m==mat};uvs=obj.data.uv_layers.active.data;samples=[];weights=[]
    for p in obj.data.polygons:
        if p.material_index not in slots or p.area<=0:continue
        uv=np.mean([uvs[li].uv[:] for li in p.loop_indices],axis=0)
        color=pixels[int(uv[1]*h)%h,int(uv[0]*w)%w]
        if not np.isfinite(color).all() or color.max()<.02:continue
        samples.append(color);weights.append(p.area)
    if len(samples)<8:return None
    samples=np.array(samples);weights=np.array(weights);luma=samples@np.array([.2126,.7152,.0722])
    order=np.argsort(luma);cum=np.cumsum(weights[order]);lo=luma[order[np.searchsorted(cum,cum[-1]*.2)]];hi=luma[order[np.searchsorted(cum,cum[-1]*.85)]]
    valid=(luma>=lo)&(luma<=hi)
    return {'color':median(samples[valid],weights[valid]),'area':float(weights.sum()),'image':im.name,'samples':int(valid.sum())}

def calibration(obj,face):
    f=sample_material(obj,face);candidates=[]
    for mat in obj.data.materials:
        if mat.get('ef_custom_role',mat.get('ef_role'))!='skin':continue
        sample=sample_material(obj,mat)
        if not sample:continue
        sh=next((n for n in mat.node_tree.nodes if n.type=='GROUP' and n.node_tree and n.node_tree.name==core.BASE),None)
        tint=np.array(sh.inputs['BaseColor'].default_value[:3]) if sh else np.ones(3)
        candidates.append((sample,mat.name,tint))
    if not f or not candidates:return {'gain':[1.,1.,1.],'method':'neutral: no usable body skin reference'}
    body,name,tint=max(candidates,key=lambda x:x[0]['area'])
    # Limit atlas compensation to avoid flattening intentionally distinct colors.
    ratio=np.clip(body['color']/np.maximum(f['color'],.01),.8,1.35)
    return {'gain':ratio.tolist(),'method':'UV atlas ratio with shared Endfield skin lighting','face_color':f['color'].tolist(),'body_color':body['color'].tolist(),'body_material':name,'body_tint':tint.tolist(),'face_image':f['image'],'body_image':body['image']}

def group():
    existing=bpy.data.node_groups.get(GROUP)
    if existing:return existing
    # Isolate the adapter from the body and the three character-specific shaders.
    g=bpy.data.node_groups[core.BASE].copy();g.name=GROUP
    normal=g.nodes.get('混合.024')
    if not normal:raise ValueError('皮肤参考资源缺少法线分支，无法创建面部适配')
    socket=g.interface.new_socket(name='Face normal softness',in_out='INPUT',socket_type='NodeSocketFloat');socket.default_value=.75;socket.min_value=0.;socket.max_value=1.
    gi=next(n for n in g.nodes if n.type=='GROUP_INPUT')
    geo=core.node(g,'ShaderNodeNewGeometry','Face original normal',-1500,-1000)
    hf=core.node(g,'ShaderNodeAttribute','Face head forward',-1500,-1200);hf.attribute_name='headForward'
    dot=core.node(g,'ShaderNodeVectorMath','Front-facing region',-1250,-1050);dot.operation='DOT_PRODUCT';g.links.new(geo.outputs['Normal'],dot.inputs[0]);g.links.new(hf.outputs['Vector'],dot.inputs[1])
    ramp=core.node(g,'ShaderNodeMapRange','Keep jaw underside normals',-1050,-1050);ramp.interpolation_type='SMOOTHSTEP';ramp.clamp=True;ramp.inputs['From Min'].default_value=.05;ramp.inputs['From Max'].default_value=.55;g.links.new(dot.outputs['Value'],ramp.inputs['Value'])
    amount=core.node(g,'ShaderNodeMath','Facial normal softening',-800,-1050);amount.operation='MULTIPLY';g.links.new(ramp.outputs[0],amount.inputs[0]);g.links.new(gi.outputs['Face normal softness'],amount.inputs[1])
    mix=core.node(g,'ShaderNodeMixRGB','Soft facial lighting normal',-550,-1050);g.links.new(amount.outputs[0],mix.inputs[0]);g.links.new(geo.outputs['Normal'],mix.inputs[1]);g.links.new(hf.outputs['Vector'],mix.inputs[2])
    unit=core.node(g,'ShaderNodeVectorMath','Unit facial lighting normal',-300,-1050);unit.operation='NORMALIZE';g.links.new(mix.outputs[0],unit.inputs[0])
    for output in normal.outputs:
        for link in list(output.links):g.links.new(unit.outputs[0],link.to_socket)
    g['ef_note']='Body skin ambient, cast-shadow and direct lighting with soft face normals.'
    return g

def body_shader(obj,preferred=None):
    mats=sorted((m for m in obj.data.materials if m.get('ef_custom_role',m.get('ef_role'))=='skin'),key=lambda m:m.name!=preferred)
    return next((n for m in mats if m.node_tree for n in m.node_tree.nodes if n.type=='GROUP' and n.node_tree and n.node_tree.name==core.BASE),None)

def sync_skin(obj,wrapper,result):
    skin=wrapper.nodes['Body skin lighting'];source=body_shader(obj,result.get('body_material'))
    if source:
        for s in source.inputs:
            if hasattr(s,'default_value') and not s.is_linked:core.set_input(skin,s.name,s.default_value)
    else:
        from . import resources
        data=resources.style_data(resources.directory());values=next(e['values'] for e in data['materials']['M_actor_laevat_body_01'] if e['group']==core.BASE)
        for name,value in values.items():core.set_input(skin,name,value)
    for name,value in {'Is Skin?':True,'Use NormalTex?':False,'Use anisotropy?':False,'Use RS_Eff?':False,'Use Simple transmission？':False,'_D(sRGB).A':1.,'_P(非色彩Non_Color)R.G.B':(0.,.5,1.,1.),'_P(非色彩Non_Color)A':.45,'MetallicMax':0.,'SmoothnessMax':.45,'Rim_ColorStrength':.3,'Rim_width_X':.006,'Rim_width_Y':.004,'_E（非色彩）':(0,0,0,1),'Emission Color':(0,0,0,1)}.items():
        # Reference RGB sockets use three values; colors use four.
        try:core.set_input(skin,name,value)
        except ValueError:core.set_input(skin,name,value[:3])
    # Keep highlights restrained on the face while sharing the diffuse response.
    spec=source.inputs['SpecularColor'].default_value[:] if source else (1,1,1,1)
    core.set_input(skin,'SpecularColor',tuple(float(c)*.12 for c in spec[:3])+(1.,))

def wrapper_group(obj,mat,result):
    name=core.datablock_name('EF Face v3 / '+mat.name);g=bpy.data.node_groups.get(name)
    if g:g.nodes.clear()
    else:
        g=bpy.data.node_groups.new(name,'ShaderNodeTree')
        for n,t,default in [('Color','NodeSocketColor',(1,1,1,1)),('Skin Tint','NodeSocketColor',(1,1,1,1)),('Brightness','NodeSocketFloat',1.),('Face normal softness','NodeSocketFloat',.75)]:
            s=g.interface.new_socket(name=n,in_out='INPUT',socket_type=t);s.default_value=default
            if t=='NodeSocketFloat':s.min_value=0.;s.max_value=1. if n=='Face normal softness' else 4.
        g.interface.new_socket(name='Shader',in_out='OUTPUT',socket_type='NodeSocketShader')
    gi=core.node(g,'NodeGroupInput','Face controls',-700,100);go=core.node(g,'NodeGroupOutput','Face result',700,100)
    tint=core.node(g,'ShaderNodeMixRGB','Atlas skin calibration',-450,150);tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1.;g.links.new(gi.outputs['Color'],tint.inputs[1]);g.links.new(gi.outputs['Skin Tint'],tint.inputs[2])
    skin=core.node(g,'ShaderNodeGroup','Body skin lighting',-180,150);skin.node_tree=group();g.links.new(tint.outputs[0],skin.inputs['_D(sRGB)R.G.B']);g.links.new(gi.outputs['Face normal softness'],skin.inputs['Face normal softness'])
    rgb=core.node(g,'ShaderNodeShaderToRGB','Shared skin radiance',200,150);g.links.new(skin.outputs[0],rgb.inputs[0])
    # Face atlases also contain eyelid, brow and lip ink. Give these dark details
    # the same light color/shadow, but cap amplification so HDRI cannot wash them out.
    safe=core.node(g,'ShaderNodeVectorMath','Safe atlas denominator',0,-250);safe.operation='MAXIMUM';safe.inputs[1].default_value=(.001,.001,.001);g.links.new(tint.outputs[0],safe.inputs[0])
    ratio=core.node(g,'ShaderNodeVectorMath','Face incident light',220,-220);ratio.operation='DIVIDE';g.links.new(rgb.outputs[0],ratio.inputs[0]);g.links.new(safe.outputs[0],ratio.inputs[1])
    cap=core.node(g,'ShaderNodeVectorMath','Protect dark feature contrast',420,-220);cap.operation='MINIMUM';cap.inputs[1].default_value=(1.,1.,1.);g.links.new(ratio.outputs[0],cap.inputs[0])
    detail=core.node(g,'ShaderNodeMixRGB','Lit original facial details',620,-220);detail.blend_type='MULTIPLY';detail.inputs[0].default_value=1.;g.links.new(gi.outputs['Color'],detail.inputs[1]);g.links.new(cap.outputs[0],detail.inputs[2])
    lum=core.node(g,'ShaderNodeRGBToBW','Atlas luminance',200,-450);g.links.new(gi.outputs['Color'],lum.inputs[0])
    weight=core.node(g,'ShaderNodeMapRange','Skin versus dark facial details',440,-450);weight.interpolation_type='SMOOTHSTEP';weight.clamp=True
    f=result.get('face_color',[.6,.42,.36]);level=sum(a*b for a,b in zip(f,[.2126,.7152,.0722]));weight.inputs['From Min'].default_value=level*.25;weight.inputs['From Max'].default_value=level*.75;g.links.new(lum.outputs[0],weight.inputs[0])
    combine=core.node(g,'ShaderNodeMixRGB','Skin lighting with original detail contrast',860,80);g.links.new(weight.outputs[0],combine.inputs[0]);g.links.new(detail.outputs[0],combine.inputs[1]);g.links.new(rgb.outputs[0],combine.inputs[2])
    em=core.node(g,'ShaderNodeEmission','Face brightness',1100,150);g.links.new(combine.outputs[0],em.inputs['Color']);g.links.new(gi.outputs['Brightness'],em.inputs['Strength']);g.links.new(em.outputs[0],go.inputs[0]);go.location=(1320,150)
    g['ef_generic_face']=3;sync_skin(obj,g,result);return g

def apply(obj,mat,match=True):
    old=next((n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image),None)
    if not old:raise ValueError('面部材质缺少基础颜色图像')
    im=old.image;result=calibration(obj,mat) if match else {'gain':[1.,1.,1.],'method':'neutral: auto calibration disabled'};result['enabled']=match
    t=mat.node_tree;t.nodes.clear()
    uv=core.node(t,'ShaderNodeUVMap','Original material UV',-650,150);uv.uv_map=obj.data.uv_layers.active.name
    tex=core.node(t,'ShaderNodeTexImage','Original face color',-450,150);tex.image=im;t.links.new(uv.outputs[0],tex.inputs[0])
    # A distinct node name keeps legacy Nico defaults out of tweak restoration.
    sh=core.node(t,'ShaderNodeGroup',FACE_NODE,-100,150);sh.node_tree=wrapper_group(obj,mat,result);t.links.new(tex.outputs['Color'],sh.inputs['Color'])
    sh.inputs['Skin Tint'].default_value=(*result['gain'],1.);sh.inputs['Brightness'].default_value=1.
    trans=core.node(t,'ShaderNodeBsdfTransparent','Cutouts',0,-150);mix=core.node(t,'ShaderNodeMixShader','Face alpha',250,150)
    alpha=core.node(t,'ShaderNodeMath','Mapped face opacity',0,-300);alpha.operation='MULTIPLY';alpha.inputs[1].default_value=mat.get('ef_custom_opacity',1.)
    t.links.new(tex.outputs['Alpha'],alpha.inputs[0]);t.links.new(alpha.outputs[0],mix.inputs[0]);t.links.new(trans.outputs[0],mix.inputs[1]);t.links.new(sh.outputs[0],mix.inputs[2])
    out=core.node(t,'ShaderNodeOutputMaterial','Output',500,150);t.links.new(mix.outputs[0],out.inputs[0])
    mat['ef_face_adapter']='Shared skin lighting v3';result['version']=3;mat['ef_skin_calibration']=json.dumps(result,ensure_ascii=False)
    return result

def refresh(obj):
    """Recalculate automatic gains after restoring artist-edited body controls."""
    for mat in obj.data.materials:
        if mat.get('ef_role')!='face' or 'ef_skin_calibration' not in mat:continue
        sh=mat.node_tree.nodes.get(FACE_NODE)
        if not sh:continue
        previous=json.loads(mat['ef_skin_calibration'])
        manual=not np.allclose(sh.inputs['Skin Tint'].default_value[:3],previous['gain'],atol=1e-5)
        enabled=getattr(obj.ef_custom,'auto_skin_tone',True)
        result=calibration(obj,mat) if enabled else {'gain':[1.,1.,1.],'method':'neutral: auto calibration disabled'};result['enabled']=enabled
        sync_skin(obj,sh.node_tree,result)
        if not manual:sh.inputs['Skin Tint'].default_value=(*result['gain'],1.)
        result['version']=3;mat['ef_skin_calibration']=json.dumps(result,ensure_ascii=False)

def surface_values(role):
    if role=='hair':
        values={'Use Fusion face color?':False,'BaseColor':(1.,1.,1.,1.),'SpecularColor':(1.1,1.1,1.1,1.),'HNormalStrength':.45,'HighLightColorA':(.18,.18,.18,1.),'HighLightColorB':(.26,.26,.26,1.),'Highlight length':.055,'Rim_ColorStrength':.75,'Rim_width_X':.008,'Rim_width_Y':.006}
    elif role in ['cloth','metal','glass','fur']:
        values={'Rim_ColorStrength':1.2,'Rim_width_X':.012,'Rim_width_Y':.008}
    else:values={}
    return values

def surface_defaults(shader,role,material=None):
    """Keep reference lighting, remove foreign-character palette and broad rims."""
    values=surface_values(role)
    for name,value in values.items():core.set_input(shader,name,value)
    if material is not None:material['ef_custom_surface_version']=2

def filter_legacy_controls(mat,groups):
    """Migrate only old shipped defaults; keep values the artist has changed."""
    role=mat.get('ef_custom_role')
    if not surface_values(role) or mat.get('ef_custom_surface_version',0)>=2:return
    from . import resources
    data=resources.style_data(resources.directory())
    preset='M_actor_pelica_hair_01' if role=='hair' else 'M_actor_pelica_cloth_01'
    for node in mat.node_tree.nodes:
        if node.name not in groups or node.type!='GROUP' or not node.node_tree:continue
        entries=[e for e in data['materials'][preset] if e['group']==node.node_tree.name]
        if not entries:continue
        old=dict(entries[0]['values'])
        if role=='hair':old.update({'Rim_ColorStrength':2.,'Rim_width_X':.02,'Rim_width_Y':.012,'BaseColor':[.9,.9,.9,1.]})
        for name in surface_values(role):
            if name not in old or name not in groups[node.name]:continue
            try:equal=np.allclose(groups[node.name][name],old[name],atol=1e-5)
            except (TypeError,ValueError):equal=groups[node.name][name]==old[name]
            if equal:groups[node.name].pop(name,None)
