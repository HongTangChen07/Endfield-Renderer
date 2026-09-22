"""Deterministic missing-map synthesis. Blender + bundled NumPy, no pip dependencies.

Generated maps are art-directed estimates, not recovered game textures. Base color
is preserved. Micro-cavity is deliberately mild and is not claimed as baked AO.
PNG encoding preserves packed alpha as data and bypasses display transforms.
"""
import bpy, numpy as np, pathlib, hashlib, json, struct, zlib

VERSION='1.1.0'

def read_pixels(path, max_size=2048, target_size=None):
    im=bpy.data.images.load(str(path),check_existing=False)
    try:
        im.colorspace_settings.name='Non-Color'
        w,h=im.size
        if target_size:im.scale(*target_size);w,h=im.size
        if max(w,h)>max_size:
            ratio=max_size/max(w,h);im.scale(max(1,round(w*ratio)),max(1,round(h*ratio)))
        w,h=im.size
        a=np.empty(w*h*4,np.float32);im.pixels.foreach_get(a)
        return a.reshape(h,w,4)
    finally:bpy.data.images.remove(im)

def png_write(path,a):
    a=np.asarray(np.clip(a,0,1)*255+.5,dtype=np.uint8)
    if a.ndim==2:a=np.repeat(a[:,:,None],3,axis=2)
    if a.shape[2]==3:a=np.concatenate([a,np.full((*a.shape[:2],1),255,dtype=np.uint8)],axis=2)
    h,w,c=a.shape
    def chunk(t,b):return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
    # Blender pixel arrays are bottom-up; PNG scanlines are top-down.
    data=b''.join(b'\0'+row.tobytes() for row in a[::-1])
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(data,6))+chunk(b'IEND',b'')
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()

def smooth(a,steps=3):
    for _ in range(steps):
        p=np.pad(a,((1,1),(1,1)),mode='edge')
        a=(p[1:-1,1:-1]*4+p[:-2,1:-1]+p[2:,1:-1]+p[1:-1,:-2]+p[1:-1,2:])/8
    return a

def synthesize(rgba,role,seed=9877):
    rgb=rgba[...,:3];h,w=rgb.shape[:2]
    luma=rgb@np.array([.2126,.7152,.0722],dtype=np.float32)
    r,g,b=np.moveaxis(rgb,-1,0)
    rough=np.full((h,w),{'skin':.48,'face':.57,'hair':.53,'metal':.31,'glass':.19,'fur':.87}.get(role,.65),np.float32)
    metallic=np.full_like(rough,.80 if role=='metal' else 0)
    # Copper/gold trim is inferred only for clothing atlases, never skin/hair.
    gold=np.clip((r-b-.13)*7,0,1)*np.clip((g-b-.045)*10,0,1)
    if role=='cloth':
        blue=np.clip((b-r+.03)*4,0,1)
        rough-=.13*blue
        rough=rough*(1-gold)+.30*gold;metallic=.83*gold
    y,x=np.mgrid[0:h,0:w].astype(np.float32)
    phase=(seed%997)/997*6.2831853
    if role=='hair':
        height=.004*np.sin(x*.9+phase)+.002*np.sin(x*.31+phase)
        rough+=.035*np.sin(x*.25)
    elif role in ['cloth','fur']:
        height=.0016*np.sin(x*1.5)*np.sin(y*1.5)
        rough+=.018*np.sin(x*1.2)*np.sin(y*1.2)
    else:height=np.zeros_like(luma)
    if role in ['cloth','metal']:
        height+=.008*(smooth(luma,3)-smooth(luma,10))
    dy,dx=np.gradient(height)
    normal=np.stack([-dx*3,-dy*3,np.ones_like(dx)],-1)
    normal/=np.linalg.norm(normal,axis=-1,keepdims=True)
    normal=normal*.5+.5
    ao=np.clip(1-np.maximum(smooth(luma,5)-luma,0)*(.18 if role in ['cloth','metal'] else .03),.92,1)
    p=np.stack([metallic,np.full_like(rough,.5),ao,1-np.clip(rough,.15,.95)],-1)
    result={'P':p,'N':normal,'Roughness':np.clip(rough,0,1),'Metallic':metallic,'AO':ao}
    if role=='hair':
        # Hair uses a distinct P contract: R blends the directional normal,
        # G and A attenuate the anisotropic highlight. Smoothness is a scalar.
        p[:,:,0]=.65;p[:,:,1]=.65;p[:,:,3]=.55
        hn=np.empty_like(p);hn[:,:,:2]=normal[:,:,:2]
        hn[:,:,2]=.5+.035*np.sin(x*.22+phase)
        hn[:,:,3]=.5+.12*np.sin(y/h*np.pi*2)
        result['HN']=hn
    return result

def generate(source,out_dir,role,seed=9877,resolution=2048,force=False,kinds=None):
    source=pathlib.Path(source);out=pathlib.Path(out_dir)
    source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    # Distinct images named e.g. body.png must never overwrite each other's maps.
    key=source.stem+'_'+role+'_'+source_hash[:10]
    manifest_path=out/f'{key}_manifest.json'
    if manifest_path.is_file() and not force:
        saved=json.loads(manifest_path.read_text(encoding='utf-8'))
        expected=set(kinds) if kinds is not None else {'P','N','Roughness','Metallic','AO'}|({'HN'} if role=='hair' else set())
        if saved['source_sha256']==source_hash and saved['generator_version']==VERSION and saved['seed']==seed and saved['resolution']==resolution and expected.issubset(saved['paths']) and all(pathlib.Path(v).is_file() for v in saved['paths'].values()):return saved
    arrays=synthesize(read_pixels(source,resolution),role,seed)
    paths={};stats={}
    for kind,a in arrays.items():
        if kinds is not None and kind not in kinds:continue
        path=out/f'{key}_{kind}.png';digest=png_write(path,a);paths[kind]=str(path)
        stats[kind]={'sha256':digest,'min':float(a.min()),'max':float(a.max()),'mean':float(a.mean()),'finite':bool(np.isfinite(a).all()),'size':[a.shape[1],a.shape[0]]}
    manifest={'generator_version':VERSION,'source':str(source),'source_sha256':source_hash,'role':role,'seed':seed,'resolution':resolution,'paths':paths,'statistics':stats,'P_schema':'R: direction blend, G: highlight mask, B: AO, A: highlight attenuation' if role=='hair' else 'R: metallic, G: auxiliary, B: AO, A: smoothness','provenance':'procedural estimates; micro-cavity AO, not a raytraced bake'}
    (out/f'{key}_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest


def compose_p(generated, supplied, out_dir, role, resolution=2048):
    """Fill the body P contract with valid artist maps over procedural estimates."""
    active={k:v for k,v in supplied.items() if k in ['Roughness','Metallic','AO']}
    if role=='hair' or not active:return str(generated)
    p=read_pixels(generated,resolution);h,w=p.shape[:2]
    identity=hashlib.sha256(pathlib.Path(generated).read_bytes())
    for kind,path in sorted(active.items()):
        identity.update(kind.encode());identity.update(pathlib.Path(path).read_bytes())
        a=read_pixels(path,resolution,target_size=(w,h))[:,:,0]
        p[:,:,{'Metallic':0,'AO':2,'Roughness':3}[kind]]=1-a if kind=='Roughness' else a
    dest=pathlib.Path(out_dir)/('composed_'+identity.hexdigest()[:16]+'_P.png');png_write(dest,p);return str(dest)

def convert_rmo(source,out_path,resolution=2048):
    a=read_pixels(source,resolution)
    p=np.stack([a[:,:,1],np.full(a.shape[:2],.5),a[:,:,2],1-a[:,:,0]],-1)
    digest=png_write(out_path,p)
    return {'P':str(out_path),'source':str(source),'sha256':digest,'operation':'P=(RMO.G, 0.5, RMO.B, 1-RMO.R)'}
