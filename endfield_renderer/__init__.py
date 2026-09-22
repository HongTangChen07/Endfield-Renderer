bl_info={'name':'终末地一键渲染','author':'','version':(1,1,4),'blender':(4,4,0),'location':'3D 视图 > 侧栏 > 终末地','description':'一键配置终末地材质、可编辑修改器、程序贴图，仅配置角色，支持自定义角色材质映射；仅支持 GOO 引擎（Goo Engine 4.4.x）','category':'Material'}

def register():
    from . import ui
    ui.register()

def unregister():
    from . import ui
    ui.unregister()
