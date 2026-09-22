"""Minimal character lighting; never import a stage, world, camera or model."""
import bpy


def collection(scene,name):
    c=next((c for c in scene.collection.children_recursive if c.name==name or c.get('ef_collection_role')==name),None)
    if c is None:
        c=bpy.data.collections.new(name);scene.collection.children.link(c);c['ef_collection_role']=name
    return c


def resolve_light(scene,light=None):
    """A removed scene light may still survive as a saved property pointer."""
    try:
        if light and scene.objects.get(light.name)==light:
            if light.type!='LIGHT' or light.data.type!='SUN':raise ValueError('终末地主光源请选择日光类型的灯光。')
            return light
    except ReferenceError:pass
    return next((o for o in scene.objects if o.name.startswith('EF_Key') and o.type=='LIGHT' and o.data.type=='SUN'),None) or next((o for o in scene.objects if o.type=='LIGHT' and o.data.type=='SUN'),None)


def ensure_light(scene,data,light=None):
    light=resolve_light(scene,light)
    if light:return light
    light=bpy.data.objects.new('EF_Key',bpy.data.lights.new('EF_Key','SUN'))
    collection(scene,'EF_Controls').objects.link(light);light['ef_owned']=True
    light.rotation_euler=data['light']['rotation']
    for name,value in data['light'].items():
        if name!='rotation' and hasattr(light.data,name):
            try:setattr(light.data,name,value)
            except (TypeError,AttributeError):pass
    return light


def ensure(scene,targets,root,data,light=None,reset=False,stage=False):
    # Keep obsolete arguments for saved scripts, but never execute stage setup.
    # Color management, world, framing, cameras and existing lamps belong to the artist.
    scene.render.engine='BLENDER_EEVEE'
    light=ensure_light(scene,data,light)
    bpy.context.view_layer.update()
    return light
