"""One-click orchestration shared by the UI and headless integration checks."""
import bpy,pathlib,json,datetime,hashlib,array,traceback
from . import core,style,modifiers,resources,studio,custom,autodetect

VERSION='1.1.4'

def detect(obj):
    if obj.type!='MESH' or not obj.data.materials:return None
    if hasattr(obj,'ef_custom') and obj.ef_custom.confirmed:return custom.key(obj)
    names={resources.original_material(m).name for m in obj.data.materials if m}
    for key,profile in core.PROFILES.items():
        expected={m for group in profile['roles'].values() for m in group}
        if names==expected:return key
    return None

def targets(context,scope='AUTO',automatic=False):
    meshes=[o for o in context.selected_objects if o.type=='MESH']
    chosen=[(detect(o) or custom.key(o),o) for o in meshes if detect(o) or automatic and (scope=='SELECTED' or autodetect.candidate(o))]
    active=context.view_layer.objects.active
    if scope=='AUTO' and not chosen and active and active.type=='MESH' and (detect(active) or automatic and autodetect.candidate(active)):
        chosen=[(detect(active) or custom.key(active),active)]
    if scope=='ALL' or (scope=='AUTO' and not chosen):chosen=[(detect(o) or custom.key(o),o) for o in context.scene.objects if not o.hide_render and (detect(o) or automatic and autodetect.candidate(o))]
    if not automatic and scope=='SELECTED' and any(detect(o) is None for o in meshes):raise ValueError('选中的网格需要设置材质映射，请使用下方的“自定义角色材质映射”。')
    if not chosen:raise ValueError('请选择受支持的角色，或先设置并启用其自定义材质映射。')
    return chosen

def scalar(value):
    if isinstance(value,bpy.types.ID):return None
    if isinstance(value,(bool,int,float,str)):return value
    try:return list(value)
    except TypeError:return None

def shader_controls(chosen):
    from . import skin_match
    result={}
    for key,obj in chosen:
        mats={}
        for m in obj.data.materials:
            if not m or not m.node_tree or not m.get('ef_style_preset'):continue
            groups={}
            for n in m.node_tree.nodes:
                if n.type=='GROUP':groups[n.name]={i.name:scalar(i.default_value) for i in n.inputs if hasattr(i,'default_value') and not i.is_linked and scalar(i.default_value) is not None}
            skin_match.filter_legacy_controls(m,groups)
            for face_name in ['Calibrated generic face',skin_match.FACE_NODE]:
                if face_name not in groups or not m.get('ef_skin_calibration'):continue
                previous=json.loads(m['ef_skin_calibration']);values=groups[face_name];tint=values.get('Skin Tint',[1,1,1])
                if previous.get('enabled',True)!=getattr(obj.ef_custom,'auto_skin_tone',True) or all(abs(a-b)<1e-5 for a,b in zip(tint,previous['gain'])):
                    values.pop('Skin Tint',None)
                elif face_name=='Calibrated generic face':
                    # v2 included body tint in the gain; v3 applies it in shared lighting.
                    body_tint=previous.get('body_tint',[1.,1.,1.])
                    values['Skin Tint']=[tint[i]/max(body_tint[i],.01) for i in range(3)]+[1.]
                if face_name=='Calibrated generic face':
                    groups[skin_match.FACE_NODE]={k:v for k,v in values.items() if k in ['Skin Tint','Brightness']}
                    del groups[face_name]
            mats[m.get('ef_source_name',m.name)]=groups
        result[key]=mats
    return result

def apply_controls(chosen,controls):
    for key,obj in chosen:
        for mat in obj.data.materials:
            if not mat.node_tree:continue
            for name,values in controls.get(key,{}).get(mat.get('ef_source_name',mat.name),{}).items():
                node=mat.node_tree.nodes.get(name)
                if not node:continue
                for socket,value in values.items():
                    if socket in node.inputs and not node.inputs[socket].is_linked:
                        try:node.inputs[socket].default_value=value
                        except (TypeError,ValueError):pass

def modifier_controls(chosen):
    result={}
    for key,obj in chosen:
        mods={}
        for mod in obj.modifiers:
            if mod.type!='NODES' or not mod.name.startswith('EF '):continue
            values={k:scalar(v) for k,v in mod.items() if scalar(v) is not None and not isinstance(v,str)}
            groups={n.name:{i.name:scalar(i.default_value) for i in n.inputs if hasattr(i,'default_value') and not i.is_linked and scalar(i.default_value) is not None} for n in mod.node_group.nodes if n.type=='GROUP'}
            mods[mod.name]={'values':values,'groups':groups}
        result[key]=mods
    return result

def restore_modifier_controls(chosen,saved):
    for key,obj in chosen:
        for name,entry in saved.get(key,{}).items():
            mod=obj.modifiers.get(name)
            if not mod:continue
            for k,v in entry['values'].items():
                if k in mod:mod[k]=v
            for n,values in entry['groups'].items():
                node=mod.node_group.nodes.get(n)
                if not node:continue
                for socket,value in values.items():
                    if socket in node.inputs and not node.inputs[socket].is_linked:
                        try:node.inputs[socket].default_value=value
                        except (TypeError,ValueError):pass
        obj.update_tag()

def digest(collection,prop,tc,width):
    a=array.array(tc,[0])*(len(collection)*width);collection.foreach_get(prop,a);return hashlib.sha256(a.tobytes()).hexdigest()

def geometry_state(obj):
    m=obj.data
    return {'coordinates':digest(m.vertices,'co','f',3),'topology':digest(m.loops,'vertex_index','i',1),'materials':digest(m.polygons,'material_index','i',1),'uvs':{u.name:digest(u.data,'uv','f',2) for u in m.uv_layers if u.name!='EF_FaceUV'},'shapes':{s.name:digest(s.data,'co','f',3) for s in m.shape_keys.key_blocks} if m.shape_keys else {},'armature':obj.find_armature().name if obj.find_armature() else None}

def preflight(context,options):
    if bpy.app.version[:2]!=(4,4) or not hasattr(bpy.types,'ShaderNodeShaderInfo'):raise ValueError('仅支持 GOO 引擎（Goo Engine 4.4.x）。普通 Blender 和 Cycles 不受支持。')
    automatic=options.get('auto_detect',True)
    root=resources.directory(options.get('resource_dir',''));chosen=targets(context,options.get('scope','AUTO'),automatic);seen=set();auto_plans={}
    for key,obj in chosen:
        if key in seen:raise ValueError('同一场景中的其他角色副本请使用自定义映射：'+key+'。每个专用适配器在同一场景中仅支持一个实例。')
        seen.add(key)
        if obj.library or obj.data.library:raise ValueError('请先将对象设为本地数据：'+obj.name+'，然后再应用材质。')
        if not obj.data.uv_layers.active:raise ValueError(obj.name+' 需要 UV 贴图。')
        if obj.mode!='OBJECT':raise ValueError('请先切换到物体模式。')
        if any(m is None for m in obj.data.materials):raise ValueError(obj.name+' 含有空材质槽，请先分配材质或移除此槽。')
        if key.startswith('Custom_'):
            if automatic:
                data=autodetect.analyze(obj);autodetect.validate_plan(obj,data);auto_plans[obj.name]=data
                if abs(custom.AXES[obj.ef_custom.forward_axis].dot(custom.AXES[obj.ef_custom.up_axis]))>.01:raise ValueError('前方轴和上方轴必须使用不同的坐标轴。')
            else:custom.validate(obj)
        else:
            arm=obj.find_armature()
            if not arm or '頭' not in arm.data.bones:raise ValueError(obj.name+' 需要原始的“頭”骨骼。其他骨架请使用自定义映射。')
            anchor=bpy.data.objects.get('EF_'+key+'_HC')
            if anchor and any(c.type=='CHILD_OF' and c.target!=arm for c in anchor.constraints):raise ValueError('已有角色实例 '+key+' 占用了这些头部控制点，请为此副本使用自定义映射。')
            for mat in obj.data.materials:
                original=resources.original_material(mat);core.role_for(key,original.name)
                im=resources.base_image(mat)
                if im and not resources.usable_image(im):raise ValueError('基础颜色贴图不可用：'+original.name+'。请恢复贴图文件，或将贴图打包到工程。')
    light=studio.resolve_light(context.scene,options.get('light'))
    out=pathlib.Path(bpy.path.abspath(options.get('output') or '//Endfield_Output'))
    if not out.is_absolute():out=pathlib.Path(bpy.app.tempdir or pathlib.Path.home())/'Endfield_Output'
    return {'targets':chosen,'root':root,'output':out,'options':options,'light':light,'style':resources.style_data(root),'auto_plans':auto_plans}

def run(plan):
    """Configure in the current scene; never save or reopen a rollback file."""
    scene=bpy.context.scene;chosen=plan['targets'];options=plan['options'];out=plan['output'];root=plan['root']
    out.mkdir(parents=True,exist_ok=True);stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    controls=shader_controls(chosen) if options.get('keep_tweaks',True) else {};mod_controls=modifier_controls(chosen) if options.get('keep_tweaks',True) else {}
    baseline={o.name:geometry_state(o) for k,o in chosen};records={};total=sum(len(o.data.materials) for k,o in chosen)+len(chosen)*2+6;step=0
    def status(label):
        nonlocal step
        step+=1;return {'progress':min(step/total,.97),'label':label}
    yield status('正在加载角色着色资源')
    for key,obj in chosen:
        if obj.name in plan.get('auto_plans',{}):autodetect.apply_plan(obj,plan['auto_plans'][obj.name])
    core.append_library(root/'reference_shader_library.blend');modifiers.load_library(root/'reference_modifier_library.blend')
    scene['ef_reference_style_json']=json.dumps(plan['style'],ensure_ascii=False);scene['ef_reference_directory']=str(root)
    light=studio.ensure(scene,chosen,root,plan['style'],plan['light']);scene.ef_settings.key_light=light
    coll=studio.collection(scene,'EF_Controls');textures=out/'textures';textures.mkdir(exist_ok=True)
    config={'reference_library':str(root/'reference_shader_library.blend'),'textures_dir':str(textures),'light':light.name,'resolution':int(options.get('resolution',2048)),'seed':int(options.get('seed',9877))}
    yield status('角色主光与着色资源已就绪')
    for key,obj in chosen:
        if obj.data.users>1:obj.data=obj.data.copy()
        (textures/key).mkdir(exist_ok=True)
        mapped=key.startswith('Custom_');mapping=custom.validate(obj) if mapped else None
        if mapped:obj['ef_custom_profile']=True;obj['ef_head_bone']=obj.ef_custom.head_bone;obj['ef_custom_owner']=obj
        originals=[resources.original_material(m).name for m in obj.data.materials];cache={};items=[]
        for i,mat in enumerate(list(obj.data.materials)):
            original=resources.original_material(mat)
            if mapped:new,record=custom.apply_material(obj,mapping[original.name],key,config,cache)
            else:
                resources.recover_source(mat,key,out);role=core.role_for(key,original.name);new,record=core.apply_material(original,role,key,config,cache)
            obj.data.materials[i]=new;items.append(record)
            yield status(obj.name+' · '+original.name)
        obj['ef_character']=key;obj['ef_source_materials']=json.dumps(originals,ensure_ascii=False);obj['ef_style_matched']=True
        mods=modifiers.setup(obj,key,str(root/'reference_modifier_library.blend'),light)
        yield status(obj.name+' · 可编辑修改器与头部控制点')
        if mapped:custom.finish(obj,key,plan['style'])
        else:style.apply_characters(scene,[(key,obj)])
        records[obj.name]={'profile':key,'materials':items,'modifiers':mods}
        yield status(obj.name+' · 面部与皮肤适配')
    scene['ef_style_matched']=True;scene['ef_addon_version']=VERSION
    apply_controls(chosen,controls);restore_modifier_controls(chosen,mod_controls);bpy.context.view_layer.update()
    from . import skin_match
    for key,obj in chosen:
        if key.startswith('Custom_'):skin_match.refresh(obj)
    checks={o.name:geometry_state(o)==baseline[o.name] for k,o in chosen}
    if not all(checks.values()):raise RuntimeError('网格保留校验失败，配置已停止。')
    for key,obj in chosen:
        if any(not m.show_render or not m.show_viewport for m in obj.modifiers if m.name.startswith('EF ')):raise RuntimeError('生成的修改器被禁用：'+obj.name)
    yield status('网格、UV、形态键及可编辑修改器校验通过')
    if options.get('pack_images',True):
        for im in bpy.data.images:
            if im.source=='FILE' and not im.packed_file and pathlib.Path(bpy.path.abspath(im.filepath)).is_file():im.pack()
    preview=None;preview_note=None
    if options.get('render_preview',True) and scene.camera is None:
        preview_note='当前场景没有相机，已完成角色配置并跳过预览；插件不自动创建相机。'
        yield status(preview_note)
    if options.get('render_preview',True) and scene.camera is not None:
        yield status('正在渲染预览图')
        preview=out/('Endfield_preview_'+stamp+'.png');r=scene.render;old=(r.filepath,r.image_settings.file_format,r.resolution_percentage,scene.eevee.taa_render_samples)
        try:
            r.filepath=str(preview);r.image_settings.file_format='PNG';r.resolution_percentage=int(options.get('preview_percent',75));scene.eevee.taa_render_samples=int(options.get('samples',64));bpy.ops.render.render(write_still=True)
        finally:r.filepath,r.image_settings.file_format,r.resolution_percentage,scene.eevee.taa_render_samples=old
    report={'version':VERSION,'status':'complete','backup':None,'preview':str(preview) if preview else None,'preview_note':preview_note,'configuration_scope':'character_only','characters':records,'geometry_preserved':checks,'notes':['生成的贴图是程序估算结果，并非还原的游戏原始贴图。','自定义角色的面部采用通用卡通着色，请检查光照与面部结构。']}
    report_path=out/('Endfield_report_'+stamp+'.json');report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    scene.ef_settings.last_report=str(report_path);scene.ef_settings.last_preview=str(preview or '')
    result=out/('Endfield_scene_'+stamp+'.blend');scene.ef_settings.last_result=str(result);scene.ef_settings.status='就绪 · 已完成 '+str(len(chosen))+' 个角色'
    # Include every Python module so the procedural generator is retained.
    for file in pathlib.Path(__file__).parent.glob('*.py'):
        text=bpy.data.texts.get('EF Source / '+file.name) or bpy.data.texts.new('EF Source / '+file.name);text.clear();text.write(file.read_text(encoding='utf-8'))
    if options.get('save_project',False):bpy.ops.wm.save_as_mainfile(filepath=str(result),copy=True,compress=True)
    else:scene.ef_settings.last_result=''
    plan['report']=report;plan['result']=scene.ef_settings.last_result
    yield {'progress':1.,'label':scene.ef_settings.status}

def run_sync(context,options):
    plan=preflight(context,options)
    for update in run(plan):scene=bpy.context.scene;scene.ef_settings.status=update['label']
    return plan
