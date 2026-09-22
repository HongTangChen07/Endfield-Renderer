"""构建 GOO 引擎插件安装包。仅使用 Python 3.10+ 标准库。"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "endfield_renderer"
RESOURCE_NAMES = {
    "reference_face_surface.npz",
    "reference_modifier_library.blend",
    "reference_shader_library.blend",
    "reference_style.json",
}


def collect_payload():
    """仅收集插件源码、中文文档和经过清单校验的角色资源。"""
    payload = {}
    sources = sorted(PACKAGE.glob("*.py"))
    if not sources or not (PACKAGE / "__init__.py").is_file():
        raise ValueError("未找到 endfield_renderer 插件源码")
    version = None
    for path in sources:
        data = path.read_bytes()
        tree = ast.parse(data.decode("utf-8-sig"), filename=path.name)
        compile(tree, path.name, "exec")
        if path.name == "__init__.py":
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "bl_info"
                    for target in node.targets
                ):
                    version = ast.literal_eval(node.value)["version"]
                    break
        payload[path.relative_to(ROOT).as_posix()] = data
    if not isinstance(version, (tuple, list)) or len(version) != 3 or not all(
        type(part) is int and part >= 0 for part in version
    ):
        raise ValueError("bl_info 中的三段版本号无效")

    for name in ("README.md", "快速开始.md"):
        path = PACKAGE / name
        payload[path.relative_to(ROOT).as_posix()] = path.read_bytes()

    manifest_path = PACKAGE / "assets" / "manifest.json"
    manifest_data = manifest_path.read_bytes()
    manifest = json.loads(manifest_data.decode("utf-8-sig"))
    if set(manifest["files"]) != RESOURCE_NAMES:
        raise ValueError("资源清单与角色资源白名单不一致")
    payload[manifest_path.relative_to(ROOT).as_posix()] = manifest_data
    for name in sorted(RESOURCE_NAMES):
        path = PACKAGE / "assets" / name
        data = path.read_bytes()
        expected = manifest["files"][name]
        if len(data) != expected["bytes"] or hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"资源校验失败：{name}")
        payload[path.relative_to(ROOT).as_posix()] = data
    return tuple(version), payload


def build(output_dir):
    output_dir = output_dir.resolve()
    if output_dir == PACKAGE.resolve() or PACKAGE.resolve() in output_dir.parents:
        raise ValueError("输出目录不能位于插件源码目录内")
    version, payload = collect_payload()
    output_dir.mkdir(parents=True, exist_ok=True)
    name = "endfield_one_click_" + "_".join(map(str, version)) + ".zip"
    target = output_dir / name
    temporary = output_dir / (name + ".partial")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path, data in sorted(payload.items()):
                # 固定归档时间和权限；相同输入及压缩环境得到相同 ZIP。
                entry = zipfile.ZipInfo(path, date_time=(2020, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data, compresslevel=9)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != set(payload):
                raise ValueError("安装包完整性校验失败")
            if any(archive.read(path) != data for path, data in payload.items()):
                raise ValueError("安装包内容校验失败")
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"Build OK: {target.name} ({len(payload)} files, {target.stat().st_size} bytes)")
    print(f"SHA-256: {digest}")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist", help="安装包输出目录，默认为仓库 dist/")
    args = parser.parse_args()
    try:
        build(args.output_dir)
    except (OSError, ValueError, KeyError, TypeError, SyntaxError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Build failed: {exc}\n")


if __name__ == "__main__":
    main()
