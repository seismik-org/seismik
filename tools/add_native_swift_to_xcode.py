import os
import hashlib
from pathlib import Path

def main():
    root = Path(__file__).resolve().parent.parent
    pbx_path = root / "mobile_app" / "ios" / "Runner.xcodeproj" / "project.pbxproj"
    native_dir = root / "mobile_app" / "ios" / "Runner" / "Native"
    runner_dir = root / "mobile_app" / "ios" / "Runner"

    with open(pbx_path, "r", encoding="utf-8") as f:
        content = f.read()

    files = []
    for p in native_dir.rglob("*.swift"):
        rel = p.relative_to(runner_dir).as_posix()
        files.append((p.name, rel))

    files.sort()
    print(f"Found {len(files)} Swift files in Native/")

    build_files = []
    file_refs = []
    group_children = []
    sources_files = []

    for fn, rel in files:
        h = hashlib.sha1(rel.encode("utf-8")).hexdigest().upper()
        file_ref = "78" + h[:22]
        build_ref = "79" + h[:22]

        if file_ref not in content:
            build_files.append(f"\t\t{build_ref} /* {fn} in Sources */ = {{isa = PBXBuildFile; fileRef = {file_ref} /* {fn} */; }};")
            file_refs.append(f'\t\t{file_ref} /* {fn} */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "{rel}"; sourceTree = "<group>"; }};')
            group_children.append(f"\t\t\t\t{file_ref} /* {fn} */,")
            sources_files.append(f"\t\t\t\t{build_ref} /* {fn} in Sources */,")

    print(f"New files to add: {len(build_files)}")
    if not build_files:
        print("All files already present in project.pbxproj.")
        return

    # 1. PBXBuildFile
    marker1 = "/* Begin PBXBuildFile section */\n"
    if marker1 in content:
        content = content.replace(marker1, marker1 + "\n".join(build_files) + "\n")

    # 2. PBXFileReference
    marker2 = "/* Begin PBXFileReference section */\n"
    if marker2 in content:
        content = content.replace(marker2, marker2 + "\n".join(file_refs) + "\n")

    # 3. Runner PBXGroup
    marker3 = "97C146F01CF9000F007C117D /* Runner */ = {\n\t\t\tisa = PBXGroup;\n\t\t\tchildren = (\n"
    if marker3 in content:
        content = content.replace(marker3, marker3 + "\n".join(group_children) + "\n")

    # 4. Sources Build Phase
    marker4 = "97C146EA1CF9000F007C117D /* Sources */ = {\n\t\t\tisa = PBXSourcesBuildPhase;\n\t\t\tbuildActionMask = 2147483647;\n\t\t\tfiles = (\n"
    if marker4 in content:
        content = content.replace(marker4, marker4 + "\n".join(sources_files) + "\n")

    with open(pbx_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("Successfully updated project.pbxproj!")

if __name__ == "__main__":
    main()
