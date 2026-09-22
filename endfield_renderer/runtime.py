"""Transient job state. Saved files must never keep a dead progress lock."""
import bpy,pathlib
from bpy.app.handlers import persistent

active_jobs=[]

def running():
    stale=False
    for job in list(active_jobs):
        try:
            if isinstance(job,bpy.types.Operator):job.as_pointer()
        except ReferenceError:active_jobs.remove(job);stale=True
    if stale and not active_jobs:
        for scene in bpy.data.scenes:
            scene.ef_settings.busy=False
            if scene.ef_settings.status.startswith('正在'):scene.ef_settings.status='任务已停止，可重新配置'
    return bool(active_jobs)

def log_error(scene,details,output=None):
    scene.ef_settings.last_error=details
    if output is not None:
        try:
            path=pathlib.Path(output)/'last_error.txt';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(details,encoding='utf-8');return str(path)
        except (OSError,ValueError):pass
    return ''

@persistent
def reset_state(_=None):
    for job in list(active_jobs):
        try:job.finish()
        except ReferenceError:pass
    active_jobs.clear()
    for scene in bpy.data.scenes:
        if not hasattr(scene,'ef_settings'):continue
        s=scene.ef_settings
        if s.busy or s.status in ['正在准备备份','正在恢复备份']:s.status='就绪'
        s.busy=False;s.progress=0.

def reset_after_register():
    if not running():reset_state()

def register():
    if reset_state not in bpy.app.handlers.load_post:bpy.app.handlers.load_post.append(reset_state)
    if hasattr(bpy.data,'scenes'):reset_state()
    elif not bpy.app.timers.is_registered(reset_after_register):bpy.app.timers.register(reset_after_register,first_interval=.1)

def unregister():
    if bpy.app.timers.is_registered(reset_after_register):bpy.app.timers.unregister(reset_after_register)
    reset_state()
    if reset_state in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(reset_state)
