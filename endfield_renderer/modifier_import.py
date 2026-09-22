"""Independent modifier import: keep source material slots and shader nodes."""
import bpy,pathlib,json,datetime
from . import workflow,autodetect,custom,core,modifiers,studio,resources

def run(context,options):
    plan=workflow.preflight(context,options);out=plan['output'];out.mkdir(parents=True,exist_ok=True)
    stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    chosen=plan['targets'];before={k:workflow.geometry_state(o) for k,o in chosen};slots={k:[m for m in o.data.materials] for k,o in chosen};saved=workflow.modifier_controls(chosen)
    for key,obj in chosen:
        if obj.name in plan['auto_plans']:autodetect.apply_plan(obj,plan['auto_plans'][obj.name])
    root=plan['root'];core.append_library(root/'reference_shader_library.blend');modifiers.load_library(root/'reference_modifier_library.blend')
    light=studio.ensure_light(context.scene,plan['style'],plan['light'])
    context.scene.ef_settings.key_light=light;records=[]
    for key,obj in chosen:
        if obj.data.users>1:obj.data=obj.data.copy()
        if key.startswith('Custom_'):
            mapping=custom.validate(obj);roles={m.name:mapping[resources.original_material(m).name].role for m in obj.data.materials};obj['ef_custom_profile']=True
        else:roles={m.name:core.role_for(key,resources.original_material(m).name) for m in obj.data.materials}
        obj['ef_character']=key
        records.append(modifiers.setup(obj,key,str(root/'reference_modifier_library.blend'),light,material_roles=roles))
    if options.get('keep_tweaks',True):workflow.restore_modifier_controls(chosen,saved)
    bpy.context.view_layer.update()
    checks={'geometry_preserved':all(workflow.geometry_state(o)==before[k] for k,o in chosen),'material_slots_preserved':all(list(o.data.materials)==slots[k] for k,o in chosen),'modifiers_live':all(all(m.show_viewport and m.show_render for m in o.modifiers if m.name.startswith('EF ')) for k,o in chosen)}
    if not all(checks.values()):raise RuntimeError('修改器导入校验失败，配置已停止。')
    report={'version':workflow.VERSION,'status':'complete','operation':'modifiers_only','backup':None,'characters':records,'checks':checks}
    path=out/('Endfield_modifiers_'+stamp+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    context.scene.ef_settings.last_report=str(path);context.scene.ef_settings.status=f'已导入 {len(chosen)} 个角色的修改器（可编辑）'
    return report
