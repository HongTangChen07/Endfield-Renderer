"""Chinese presentation labels; saved property/socket identifiers stay stable."""
import re

AXIS_LABELS={'NEG_Y':'−Y 轴','POS_Y':'+Y 轴','POS_Z':'+Z 轴','NEG_Z':'−Z 轴','POS_X':'+X 轴','NEG_X':'−X 轴'}
CONTROL_LABELS={
    'SmoothnessMax':'最大光滑度','MetallicMax':'最大金属度','NormalStrength':'法线强度',
    'Rim_ColorStrength':'轮廓光强度','GlobalShadowBrightnessAdjustment':'整体阴影亮度',
    'Skin Tint':'肤色调节','Shadow Tint':'阴影颜色','Shadow Softness':'阴影柔和度',
    'Nose Shadow':'鼻部阴影','Nose Highlight':'鼻部高光','Brightness':'面部亮度','Face normal softness':'面部法线柔化',
}
LEGACY_STATUS={
    'Ready':'就绪','Preparing backup':'就绪',
    'Backup saved; loading reference resources':'正在加载角色着色资源',
    'Reference lighting and studio ready':'参考灯光与舞台已就绪',
    'Geometry, UVs, shape keys and live modifiers verified':'网格、UV、形态键及可编辑修改器校验通过',
    'Rendering preview':'正在渲染预览图',
}

def status_text(value):
    if value in LEGACY_STATUS:return LEGACY_STATUS[value]
    match=re.fullmatch(r'Ready · (\d+) character\(s\)',value)
    if match:return '就绪 · 已完成 '+match.group(1)+' 个角色'
    return value.replace(' · live modifiers and head controls',' · 可编辑修改器与头部控制点').replace(' · face and skin adapters',' · 面部与皮肤适配')
