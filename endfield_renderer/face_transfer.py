"""Fit the supplied Endfield face-mask UV layout to another face surface.

Closest-surface transfer in normalized face space; reference UV data is loaded
from the user's local NPZ. This approximates masks, never reconstructs game SDF.
The character's original texture UVs, shape keys and mesh topology are retained.
"""
import bpy,numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import barycentric_transform

def fit_mask_uv(obj,surface_path):
    with np.load(surface_path) as src:tri=src['triangles'];uv=src['uv']
    vertices=[Vector(v) for v in tri.reshape(-1,3)]
    tree=BVHTree.FromPolygons(vertices,[(i*3,i*3+1,i*3+2) for i in range(len(tri))],all_triangles=True)
    me=obj.data;faces=[f for f in me.polygons if me.materials[f.material_index].get('ef_role')=='face']
    vids=sorted({v for f in faces for v in f.vertices})
    pos=np.array([list(obj.matrix_world@me.vertices[v].co) for v in vids],dtype=np.float32)
    low=pos.min(0);high=pos.max(0);pos=(pos-(low+high)/2)/np.maximum(high-low,1e-6)
    result={};distances=[]
    for vid,point in zip(vids,pos):
        close,normal,index,distance=tree.find_nearest(Vector(point))
        if index is None:raise ValueError('无法投射面部顶点')
        a,b,c=[Vector(v) for v in tri[index]];ua,ub,uc=[Vector((v[0],v[1],0)) for v in uv[index]]
        coord=barycentric_transform(close,a,b,c,ua,ub,uc);result[vid]=coord[:2];distances.append(distance)
    active=me.uv_layers.active_index;render=next((u.name for u in me.uv_layers if u.active_render),me.uv_layers.active.name)
    layer=me.uv_layers.get('EF_FaceUV') or me.uv_layers.new(name='EF_FaceUV')
    for face in faces:
        for loop in face.loop_indices:layer.data[loop].uv=result[me.loops[loop].vertex_index]
    me.uv_layers.active_index=active;me.uv_layers[render].active_render=True
    return {'vertices':len(vids),'mean_normalized_distance':float(np.mean(distances)),'max_normalized_distance':float(max(distances)),'uv_layer':layer.name}
