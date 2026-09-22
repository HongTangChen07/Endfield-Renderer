import bpy,json,pathlib,traceback
from bpy.props import StringProperty,PointerProperty,EnumProperty,IntProperty,BoolProperty,FloatProperty,CollectionProperty
from bpy_extras.io_utils import ImportHelper,ExportHelper
from . import core,maps,modifiers,workflow,custom,resources,modifier_import,runtime
from .i18n import AXIS_LABELS,CONTROL_LABELS,status_text

class EF_MappingRow(bpy.types.PropertyGroup):
    material:PointerProperty(type=bpy.types.Material)
    role:EnumProperty(name='材质用途',items=custom.ROLES,default='UNASSIGNED')
    opacity:FloatProperty(name='不透明度',default=1.,min=0.,max=1.)
    base_image:PointerProperty(name='基础颜色',type=bpy.types.Image)
    normal_image:PointerProperty(name='法线（OpenGL）',type=bpy.types.Image)
    packed_image:PointerProperty(name='终末地 P 贴图',type=bpy.types.Image,description='身体：R 金属度，G 辅助通道，B 环境遮蔽，A 光滑度。头发采用独立的 P 通道规则。')
    hair_normal_image:PointerProperty(name='头发 HN 贴图',type=bpy.types.Image,description='RG 和 BA 分别存储两组法线的 XY 分量')
    emission_image:PointerProperty(name='自发光贴图',type=bpy.types.Image)
    roughness_image:PointerProperty(name='粗糙度贴图',type=bpy.types.Image)
    metallic_image:PointerProperty(name='金属度贴图',type=bpy.types.Image)
    ao_image:PointerProperty(name='环境遮蔽贴图',type=bpy.types.Image)
    rmo_image:PointerProperty(name='RMO 贴图',type=bpy.types.Image)
    auto_role:StringProperty(options={'HIDDEN'})
    auto_opacity:FloatProperty(default=-1.,options={'HIDDEN'})
    auto_images:StringProperty(default='{}',options={'HIDDEN'})
    confidence:FloatProperty(default=0.,min=0.,max=1.)
    detection_note:StringProperty()
    map_status:StringProperty()

class EF_CustomMapping(bpy.types.PropertyGroup):
    materials:CollectionProperty(type=EF_MappingRow)
    active_index:IntProperty(default=0,min=0)
    confirmed:BoolProperty(name='启用此映射',default=False,description='自动识别后自动启用；关闭自动识别时可手动设置映射')
    head_bone:StringProperty(name='头部骨骼')
    detection_summary:StringProperty()
    auto_skin_tone:BoolProperty(name='脸部肤色匹配身体',default=True,description='依据当前角色面部与身体的 UV 肤色采样自动校准，保留原贴图；不套用其他角色的肤色')
    forward_axis:EnumProperty(name='前方轴',items=[(k,AXIS_LABELS[k],'物体局部坐标方向') for k in custom.AXES],default='NEG_Y')
    up_axis:EnumProperty(name='上方轴',items=[(k,AXIS_LABELS[k],'物体局部坐标方向') for k in custom.AXES],default='POS_Z')

class EF_Preferences(bpy.types.AddonPreferences):
    bl_idname=__package__
    resource_dir:StringProperty(name='参考资源目录（可选）',subtype='DIR_PATH',description='留空时使用插件内置的着色器资源')
    def draw(self,context):
        self.layout.label(text='仅支持 GOO 引擎（Goo Engine 4.4.x）')
        self.layout.prop(self,'resource_dir')

class EF_UL_material_mapping(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row();row.label(text=item.material.name if item.material else '材质丢失',icon='MATERIAL');row.prop(item,'role',text='')

class EF_Settings(bpy.types.PropertyGroup):
    output_root:StringProperty(name='输出目录',subtype='DIR_PATH',default='//Endfield_Output')
    target_scope:EnumProperty(name='处理范围',items=[('AUTO','优先选中或当前角色','优先选中角色，其次当前活动角色，最后才扫描场景'),('SELECTED','仅选中的角色','仅处理选中的角色网格'),('ALL','全部已识别角色','处理所有可渲染的受支持角色及已启用映射的角色')],default='AUTO')
    render_preview:BoolProperty(name='使用现有相机渲染预览',default=True,description='没有场景相机时跳过预览，仅配置角色；不会自动创建相机')
    save_project:BoolProperty(name='完成后另存工程副本',default=False,description='仅勾选时保存结果工程；默认只修改当前场景')
    pack_images:BoolProperty(name='打包贴图到工程',default=True)
    keep_tweaks:BoolProperty(name='保留已调整的材质参数',default=True)
    setup_studio:BoolProperty(default=False,options={'HIDDEN'})
    reset_studio:BoolProperty(default=False,options={'HIDDEN'})
    map_resolution:EnumProperty(name='生成贴图尺寸',items=[('512','512 像素','快速预览'),('1024','1024 像素','均衡质量'),('2048','2048 像素','高精度细节')],default='2048')
    preview_percent:IntProperty(name='预览分辨率（%）',default=75,min=10,max=100)
    samples:IntProperty(name='预览采样数',default=64,min=8,max=256)
    status:StringProperty(default='就绪')
    busy:BoolProperty(default=False,options={'SKIP_SAVE'})
    progress:FloatProperty(default=0.,min=0.,max=1.,options={'SKIP_SAVE'})
    last_backup:StringProperty(subtype='FILE_PATH',options={'HIDDEN'})
    last_error:StringProperty(options={'HIDDEN'})
    last_result:StringProperty(subtype='FILE_PATH')
    last_preview:StringProperty(subtype='FILE_PATH')
    last_report:StringProperty(subtype='FILE_PATH')
    show_advanced:BoolProperty(name='高级设置',default=False)
    show_mapping:BoolProperty(name='自定义角色材质映射',default=False)
    show_pbr_maps:BoolProperty(name='独立 PBR 通道贴图',default=False)
    auto_detect:BoolProperty(name='自动识别材质与贴图',default=True,description='自动识别角色用途并关联同名贴图，缺失的辅助贴图从基础颜色生成；保留手动修改的用途与贴图')
    reference_library:StringProperty(name='参考工程（.blend）',subtype='FILE_PATH',description='选择本地参考工程或导出的着色器库')
    modifier_library:StringProperty(name='修改器资源库',subtype='FILE_PATH',default='//reference/reference_modifier_library.blend')
    output_dir:StringProperty(name='生成贴图目录',subtype='DIR_PATH',default='//endfield_textures')
    key_light:PointerProperty(name='主光源',type=bpy.types.Object,poll=lambda self,o:o.type=='LIGHT' and o.data.type=='SUN')
    map_role:EnumProperty(name='贴图材质类型',items=[next(item for item in custom.ROLES if item[0]==key) for key in ['cloth','metal','skin','hair','fur','glass']],default='cloth')
    seed:IntProperty(name='随机种子',default=9877,min=0)

def options(context):
    s=context.scene.ef_settings;addon=context.preferences.addons.get(__package__)
    return {'resource_dir':addon.preferences.resource_dir if addon else '', 'scope':s.target_scope,'output':s.output_root,'light':s.key_light,'keep_tweaks':s.keep_tweaks,'resolution':int(s.map_resolution),'seed':s.seed,'render_preview':s.render_preview,'save_project':s.save_project,'pack_images':s.pack_images,'preview_percent':s.preview_percent,'samples':s.samples,'auto_detect':s.auto_detect}

class EF_OT_one_click(bpy.types.Operator):
    bl_idname='endfield.one_click';bl_label='一键终末地渲染';bl_description='在当前场景配置角色材质、缺失贴图及可编辑修改器；使用现有相机渲染，不创建备份'
    @classmethod
    def poll(cls,context):return not runtime.running() and not context.scene.ef_settings.busy
    def execute(self,context):
        self.scene=context.scene;self.wm=context.window_manager;self.timer=None;self.job=None;self.finished=False
        s=self.scene.ef_settings;s.progress=0.;s.last_error=''
        try:self.plan=workflow.preflight(context,options(context))
        except Exception as exc:
            runtime.log_error(self.scene,traceback.format_exc());s.busy=False;s.status='配置失败：'+str(exc);self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.job=workflow.run(self.plan);runtime.active_jobs.append(self);s.busy=True;s.status='正在加载角色着色资源'
        if bpy.app.background:
            try:
                for update in self.job:s.status=update['label'];s.progress=update['progress']
                return {'FINISHED'}
            except Exception as exc:
                runtime.log_error(self.scene,traceback.format_exc(),self.plan['output']);s.status='配置失败：'+str(exc);self.report({'ERROR'},str(exc));return {'CANCELLED'}
            finally:self.finish()
        try:
            self.timer=self.wm.event_timer_add(.12,window=context.window);self.wm.modal_handler_add(self);self.wm.progress_begin(0,100)
        except Exception:
            self.finish();raise
        return {'RUNNING_MODAL'}
    def finish(self,context=None):
        if self.finished:return
        self.finished=True
        try:
            if self.job:self.job.close()
        except (RuntimeError,ReferenceError):pass
        try:
            if self.timer:self.wm.event_timer_remove(self.timer)
            self.wm.progress_end()
        except (RuntimeError,ReferenceError,ValueError):pass
        try:self.scene.ef_settings.busy=False
        except ReferenceError:pass
        if self in runtime.active_jobs:runtime.active_jobs.remove(self)
    def cancel(self,context):self.finish()
    def modal(self,context,event):
        if self.finished:return {'CANCELLED'}
        if event.type=='ESC':
            self.scene.ef_settings.status='已取消 · 已完成的配置保留在当前场景';self.finish();self.report({'INFO'},'已取消，保留当前场景。');return {'CANCELLED'}
        # Goo 4.4 Event RNA does not expose a timer attribute.
        if event.type!='TIMER':return {'RUNNING_MODAL'}
        try:
            update=next(self.job);s=self.scene.ef_settings;s.status=update['label'];s.progress=update['progress'];self.wm.progress_update(s.progress*100)
            for area in context.screen.areas:area.tag_redraw()
        except StopIteration:
            self.finish();note=self.plan.get('report',{}).get('preview_note');self.report({'INFO'},note or '终末地角色配置完成。');return {'FINISHED'}
        except Exception as exc:
            details=traceback.format_exc();message=str(exc);self.finish();self.scene.ef_settings.status='配置失败：'+message
            path=runtime.log_error(self.scene,details,self.plan['output']);self.report({'ERROR'},message+('；错误详情：'+path if path else ''));return {'CANCELLED'}
        return {'RUNNING_MODAL'}

class EF_OT_open_output(bpy.types.Operator):
    bl_idname='endfield.open_output';bl_label='打开输出目录'
    def execute(self,context):
        path=pathlib.Path(bpy.path.abspath(context.scene.ef_settings.output_root));path.mkdir(parents=True,exist_ok=True);bpy.ops.wm.path_open(filepath=str(path));return {'FINISHED'}

class EF_OT_populate_mapping(bpy.types.Operator):
    bl_idname='endfield.populate_mapping';bl_label='自动识别材质与贴图';bl_description='读取原材质、关联同名贴图并识别头骨，保留手动调整；缺图将在一键渲染时生成';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.object and context.object.type=='MESH'
    def execute(self,context):custom.populate(context.object);return {'FINISHED'}

class EF_OT_save_mapping(bpy.types.Operator,ExportHelper):
    bl_idname='endfield.save_mapping';bl_label='保存材质映射';filename_ext='.json'
    filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:pathlib.Path(self.filepath).write_text(json.dumps(custom.export_mapping(context.object),ensure_ascii=False,indent=2),encoding='utf-8');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_OT_load_mapping(bpy.types.Operator,ImportHelper):
    bl_idname='endfield.load_mapping';bl_label='加载材质映射';filename_ext='.json'
    filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:custom.import_mapping(context.object,json.loads(pathlib.Path(self.filepath).read_text(encoding='utf-8')));return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_OT_save_look(bpy.types.Operator,ExportHelper):
    bl_idname='endfield.save_look';bl_label='保存外观预设';filename_ext='.json'
    filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:
            chosen=workflow.targets(context,context.scene.ef_settings.target_scope);pathlib.Path(self.filepath).write_text(json.dumps({'schema':1,'controls':workflow.shader_controls(chosen),'modifiers':workflow.modifier_controls(chosen)},ensure_ascii=False,indent=2),encoding='utf-8');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_OT_load_look(bpy.types.Operator,ImportHelper):
    bl_idname='endfield.load_look';bl_label='加载外观预设';filename_ext='.json'
    filter_glob:StringProperty(default='*.json',options={'HIDDEN'})
    def execute(self,context):
        try:
            data=json.loads(pathlib.Path(self.filepath).read_text(encoding='utf-8'))
            if data.get('schema')!=1:raise ValueError('不支持此外观预设格式')
            chosen=workflow.targets(context,context.scene.ef_settings.target_scope);workflow.apply_controls(chosen,data['controls']);workflow.restore_modifier_controls(chosen,data.get('modifiers',{}));return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_OT_apply(bpy.types.Operator):
    bl_idname='endfield.apply_three_characters';bl_label='应用三个角色的专用配置';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        s=context.scene.ef_settings
        try:
            if not s.key_light:raise ValueError('请选择主光源')
            if not hasattr(bpy.types,'ShaderNodeShaderInfo'):raise ValueError('仅支持 GOO 引擎（Goo Engine 4.4.x），普通 Blender 不受支持')
            cfg={'reference_library':bpy.path.abspath(s.reference_library),'textures_dir':bpy.path.abspath(s.output_dir),'light':s.key_light.name}
            result=core.apply_all(cfg)
            path=pathlib.Path(cfg['textures_dir'])/'material_manifest.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            self.report({'INFO'},'已应用终末地材质配置，并保留原始材质')
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_OT_restore(bpy.types.Operator):
    bl_idname='endfield.restore_materials';bl_label='恢复选中角色的原始材质';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return any('ef_source_materials' in o for o in context.selected_objects)
    def execute(self,context):
        try:
            for o in context.selected_objects:
                if 'ef_source_materials' in o:core.restore_materials(o)
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_OT_modifiers(bpy.types.Operator):
    bl_idname='endfield.live_modifiers';bl_label='一键导入修改器';bl_description='自动识别角色并从内置参考资源导入可编辑修改器；保留原材质、骨架和形态键';bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return not context.scene.ef_settings.busy
    def execute(self,context):
        s=context.scene.ef_settings
        try:
            s.busy=True;report=modifier_import.run(context,options(context))
            self.report({'INFO'},f"已导入 {len(report['characters'])} 个角色的可编辑修改器，原材质、骨架和形态键已保留")
            return {'FINISHED'}
        except Exception as exc:
            runtime.log_error(context.scene,traceback.format_exc());s.status='配置失败：'+str(exc);self.report({'ERROR'},str(exc))
            return {'CANCELLED'}
        finally:s.busy=False

class EF_OT_generate(bpy.types.Operator):
    bl_idname='endfield.generate_maps';bl_label='根据当前材质重新生成贴图';bl_options={'REGISTER'}
    @classmethod
    def poll(cls,context):return context.object is not None and context.object.active_material is not None
    def execute(self,context):
        try:
            mat=context.object.active_material;s=context.scene.ef_settings
            source=bpy.data.materials.get(mat.get('ef_source_name','')) or mat
            if not source.node_tree:raise ValueError('此材质没有图像节点')
            n=source.node_tree.nodes.get('mmd_base_tex')
            if n is None:n=next((n for n in source.node_tree.nodes if n.type=='TEX_IMAGE' and n.image and n.image.colorspace_settings.name=='sRGB'),None)
            if n is None or n.image is None:raise ValueError('未找到基础颜色贴图')
            output=pathlib.Path(bpy.path.abspath(s.output_dir))/mat.get('ef_character','Custom')
            maps.generate(bpy.path.abspath(n.image.filepath),output,s.map_role,s.seed,force=True)
            for im in bpy.data.images:
                if im.source=='FILE' and pathlib.Path(bpy.path.abspath(im.filepath)).parent==output:
                    packed=bool(im.packed_file)
                    if packed:im.unpack(method='USE_ORIGINAL')
                    im.reload()
                    if packed:im.pack()
            self.report({'INFO'},'已生成 P、法线、粗糙度、金属度及微细凹陷环境遮蔽贴图')
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}

class EF_PT_panel(bpy.types.Panel):
    bl_label='终末地一键渲染';bl_idname='EF_PT_panel';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='终末地'
    def draw(self,context):
        l=self.layout;s=context.scene.ef_settings
        l.label(text='仅支持 GOO 引擎（4.4.x）')
        l.label(text='仅配置角色 · 保留现有场景')
        row=l.row();row.scale_y=1.7;row.operator(EF_OT_one_click.bl_idname,icon='RENDER_STILL')
        if s.busy:
            l.progress(factor=s.progress,type='BAR',text=s.status);l.label(text='按 Esc 停止后续步骤，保留当前场景。');return
        l.label(text=status_text(s.status),icon='CHECKMARK' if context.scene.get('ef_style_matched') else 'INFO')
        row=l.row();row.scale_y=1.3;row.operator(EF_OT_modifiers.bl_idname,icon='MODIFIER')
        l.prop(s,'target_scope');l.prop(s,'auto_detect')
        if s.auto_detect:l.label(text='优先已有贴图，缺失辅助图自动生成',icon='TEXTURE')
        l.prop(s,'output_root');l.prop(s,'render_preview')
        if s.render_preview and context.scene.camera is None:l.label(text='无场景相机：配置角色，跳过出图',icon='INFO')
        l.operator(EF_OT_open_output.bl_idname,icon='FILE_FOLDER')
        l.separator();l.prop(s,'show_mapping',icon='TRIA_DOWN' if s.show_mapping else 'TRIA_RIGHT',emboss=False)
        obj=context.object
        if s.show_mapping:
            box=l.box()
            if not obj or obj.type!='MESH':box.label(text='请选择包含完整角色的单个网格。',icon='INFO')
            else:
                cfg=obj.ef_custom;box.label(text=obj.name,icon='OUTLINER_OB_MESH');box.operator(EF_OT_populate_mapping.bl_idname)
                if cfg.materials:
                    if cfg.detection_summary:box.label(text=cfg.detection_summary,icon='CHECKMARK')
                    box.template_list('EF_UL_material_mapping','',cfg,'materials',cfg,'active_index',rows=6)
                    if cfg.active_index<len(cfg.materials):
                        item=cfg.materials[cfg.active_index];col=box.column(align=True)
                        if item.detection_note:col.label(text=item.detection_note,icon='INFO')
                        if item.map_status:col.label(text=item.map_status)
                        for field,label in [('base_image','基础颜色'),('normal_image','法线（+Y）'),('packed_image','P 贴图（通道规则见使用说明）'),('hair_normal_image','头发法线'),('emission_image','自发光')]:
                            col.label(text=label);col.template_ID(item,field,open='image.open')
                        col.prop(s,'show_pbr_maps',icon='TRIA_DOWN' if s.show_pbr_maps else 'TRIA_RIGHT',emboss=False)
                        if s.show_pbr_maps:
                            for field,label in [('roughness_image','粗糙度'),('metallic_image','金属度'),('ao_image','环境遮蔽'),('rmo_image','RMO（R 粗糙度 / G 金属度 / B 遮蔽）')]:
                                col.label(text=label);col.template_ID(item,field,open='image.open')
                        col.prop(item,'opacity')
                    arm=obj.find_armature()
                    if arm:box.prop_search(cfg,'head_bone',arm.data,'bones')
                    else:box.label(text='静态网格：头部控制点跟随物体。')
                    row=box.row(align=True);row.prop(cfg,'forward_axis');row.prop(cfg,'up_axis')
                    if not s.auto_detect:box.prop(cfg,'confirmed')
                    box.prop(cfg,'auto_skin_tone')
                    box.label(text='可手动修正；再次识别保留手动修改。',icon='INFO')
                row=box.row(align=True);row.operator(EF_OT_save_mapping.bl_idname);row.operator(EF_OT_load_mapping.bl_idname)
        l.prop(s,'show_advanced',icon='TRIA_DOWN' if s.show_advanced else 'TRIA_RIGHT',emboss=False)
        if s.show_advanced:
            box=l.box()
            for field in ['key_light','keep_tweaks','map_resolution','seed','preview_percent','samples','pack_images','save_project']:box.prop(s,field)
            row=box.row(align=True);row.operator(EF_OT_save_look.bl_idname);row.operator(EF_OT_load_look.bl_idname)
            box.operator(EF_OT_restore.bl_idname)
            box.label(text='单独生成贴图')
            box.prop(s,'output_dir');box.prop(s,'map_role');box.operator(EF_OT_generate.bl_idname)
        mat=context.object.active_material if context.object else None
        if mat and mat.node_tree:
            shader=next((n for n in mat.node_tree.nodes if n.type=='GROUP' and n.node_tree and n.node_tree.name in [core.BASE,core.HAIR]),None)
            if shader:
                l.separator();l.label(text='当前材质参数')
                for name in ['SmoothnessMax','MetallicMax','NormalStrength','Rim_ColorStrength','GlobalShadowBrightnessAdjustment']:
                    if name in shader.inputs:l.prop(shader.inputs[name],'default_value',text=CONTROL_LABELS[name])
            face=next((n for n in mat.node_tree.nodes if n.type=='GROUP' and n.node_tree and (n.node_tree.name in ['EF Nico Toon Face v1','EF Generic Toon Face v2'] or n.node_tree.get('ef_generic_face')==3)),None)
            if face:
                l.separator();l.label(text='面部肤色与明暗')
                for name in ['Skin Tint','Shadow Tint','Shadow Softness','Nose Shadow','Nose Highlight','Brightness','Face normal softness']:
                    if face.node_tree.name=='EF Generic Toon Face v2' and name in ['Nose Shadow','Nose Highlight']:continue
                    if name not in face.inputs:continue
                    l.prop(face.inputs[name],'default_value',text=CONTROL_LABELS[name])

CLASSES=(EF_Preferences,EF_MappingRow,EF_CustomMapping,EF_Settings,EF_UL_material_mapping,EF_OT_one_click,EF_OT_open_output,EF_OT_populate_mapping,EF_OT_save_mapping,EF_OT_load_mapping,EF_OT_save_look,EF_OT_load_look,EF_OT_apply,EF_OT_modifiers,EF_OT_restore,EF_OT_generate,EF_PT_panel)
def register():
    for c in CLASSES:bpy.utils.register_class(c)
    bpy.types.Scene.ef_settings=PointerProperty(type=EF_Settings)
    bpy.types.Object.ef_custom=PointerProperty(type=EF_CustomMapping)
    runtime.register()
def unregister():
    runtime.unregister()
    if hasattr(bpy.types.Scene,'ef_settings'):del bpy.types.Scene.ef_settings
    if hasattr(bpy.types.Object,'ef_custom'):del bpy.types.Object.ef_custom
    for c in reversed(CLASSES):bpy.utils.unregister_class(c)
