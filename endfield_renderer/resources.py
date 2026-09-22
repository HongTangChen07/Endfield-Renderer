"""Portable reference resources and packed-image recovery."""
import bpy,json,pathlib,re

REQUIRED=('reference_shader_library.blend','reference_modifier_library.blend','reference_style.json','reference_face_surface.npz')

def directory(override=''):
    candidates=[]
    if override:candidates.append(pathlib.Path(bpy.path.abspath(override)))
    candidates.append(pathlib.Path(__file__).parent/'assets')
    candidates.append(pathlib.Path(__file__).parent.parent/'reference')
    for path in candidates:
        if all((path/f).is_file() for f in REQUIRED):return path
    raise ValueError('参考资源丢失。请重新安装完整的“终末地一键渲染”插件 ZIP，或在插件偏好设置中指定资源目录。')

def style_data(root):
    return json.loads((pathlib.Path(root)/'reference_style.json').read_text(encoding='utf-8'))

def original_material(mat):
    return bpy.data.materials.get(mat.get('ef_source_name','')) or mat

def base_image(mat):
    original=original_material(mat)
    node=original.node_tree.nodes.get('mmd_base_tex') if original.node_tree else None
    return node.image if node and node.image else None

def usable_image(im):
    return im is not None and (pathlib.Path(bpy.path.abspath(im.filepath)).is_file() or bool(im.packed_file))

def recover_source(mat,key,output):
    """Export a packed original only when its external file is unavailable."""
    original=original_material(mat);im=base_image(original)
    if not im:return None
    path=pathlib.Path(bpy.path.abspath(im.filepath))
    if path.is_file():
        if 'ef_resolved_source_path' in original:del original['ef_resolved_source_path']
        return path
    if not im.packed_file:raise ValueError('基础颜色贴图丢失：'+original.name)
    name=path.name or re.sub(r'[^\w.-]','_',im.name)+'.png'
    path=pathlib.Path(output)/'recovered_sources'/key/'tex'/name;path.parent.mkdir(parents=True,exist_ok=True)
    payload=bytes(im.packed_file.data)
    if not path.is_file() or path.read_bytes()!=payload:path.write_bytes(payload)
    original['ef_resolved_source_path']=str(path)
    # Recover corresponding native maps from packed data without changing the
    # original Image datablocks or writing into the artist's source directory.
    for packed in bpy.data.images:
        if not packed.packed_file:continue
        old=pathlib.Path(bpy.path.abspath(packed.filepath));dest=None
        if key=='Tevelos' and old.name.startswith('T_actor_'):
            dest=path.parent.parent/'other tex'/old.name
        elif key=='Suomi' and old.parent.name=='normalmap':dest=path.parent/'normalmap'/old.name
        if dest:
            dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.is_file():dest.write_bytes(bytes(packed.packed_file.data))
    return path
