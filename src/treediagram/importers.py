"""Declarative imports. No plugin installation, scripts or executable payloads."""
from __future__ import annotations

import hashlib
import io
import math
import zipfile
from dataclasses import asdict, replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError

from .design import Design, Design_Validate, Motor, Part, Scenario
from .io import Json_Read, Json_Decode


def Motor_DeriveRoundoff(design: Design, tolerance_n: float) -> Design:
    if type(tolerance_n) not in (int,float) or not math.isfinite(tolerance_n) or not 0 < tolerance_n <= 1e-6:
        raise ValueError("roundoff tolerance must be explicit, positive and <=1e-6 N")
    motor=design.motor
    if motor is None:
        raise ValueError("no motor")
    affected=[i for i,f in enumerate(motor.thrust_n) if f < 0]
    if any(motor.thrust_n[i] < -tolerance_n for i in affected):
        raise ValueError("negative thrust exceeds roundoff tolerance; no changes committed")
    source={**motor.source,"derived_curve_policy":{"id":"negative_roundoff_to_zero/1","tolerance_n":tolerance_n,
            "affected_indices":affected,"original_values_n":[motor.thrust_n[i] for i in affected]}}
    return replace(design,motor=replace(motor,thrust_n=tuple(0. if i in affected else f for i,f in enumerate(motor.thrust_n)),source=source))


def Motor_Import(path: Path, design: Design) -> tuple[Design, tuple[str, ...]]:
    from .vendor_motor.contract import MAX_BYTES, MotorPackage_Validate
    # Hash and parse exactly the same bounded byte snapshot. A later file change
    # must never attach a different file identity to an already parsed curve.
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    package = MotorPackage_Validate(Json_Decode(raw))
    motor = package["motor"]
    curve = package["simulation_curve"] or package["evidence_curve"]
    propellant, total = motor["propellant_mass_kg"], motor["total_mass_kg"]
    previous = design.motor
    geometry, geometry_origin = {}, {}
    for field, supplied in (("length_m", motor["length_m"]),
                            ("radius_m", None if motor["diameter_m"] is None
                             else motor["diameter_m"] / 2)):
        if supplied is not None:
            geometry[field], geometry_origin[field] = supplied, "underline_package"
            continue
        retained = getattr(previous, field, None)
        if type(retained) not in (float, int) or not math.isfinite(retained) or retained <= 0:
            raise ValueError(
                f"motor.{field}: 包内缺少尺寸；请先在工程中明确发动机安装尺寸，再导入曲线"
            )
        geometry[field], geometry_origin[field] = retained, "retained_project_installation"
    # Assembly position/capability remains TreeDiagram-owned on re-import.
    candidate = Motor(tuple(curve["time_s"]), tuple(curve["thrust_n"]), propellant,
                      None if total is None or propellant is None else total-propellant,
                      position_m=previous.position_m if previous else (0., 0., 0.),
                      length_m=geometry["length_m"], radius_m=geometry["radius_m"],
                      ignition_s=previous.ignition_s if previous else 0.,
                      mass_model=previous.mass_model if previous else "impulse_fraction_uniform_cylinder",
                      gimbal_capable=previous.gimbal_capable if previous else False,
                      rotation_bm_wxyz=previous.rotation_bm_wxyz if previous else (1.,0.,0.,0.),
                      source={"package": package, "file_sha256": hashlib.sha256(raw).hexdigest(),
                              "source_verified_independently": False,
                              "geometry_origin": geometry_origin})
    warnings = []
    if package["simulation_curve"] is None:
        warnings.append("motor: 缺少符合边界/缺口策略的仿真曲线；仅导入证据预览")
    changes = tuple(key for key, value in asdict(candidate).items()
                    if previous is None or asdict(previous).get(key) != value)
    result = replace(design, motor=candidate,
                     import_issues=tuple(issue for issue in design.import_issues if not issue.startswith("motor:"))+tuple(warnings))
    Design_Validate(result, runnable=False)
    return result, changes


def _Ork_Read(path: Path) -> bytes:
    if path.stat().st_size > 16*1024*1024:
        raise ValueError("ORK: compressed/input size exceeds 16 MiB")
    raw = path.read_bytes()
    if not raw.startswith(b"PK"):
        return raw
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) > 64 or sum(m.file_size for m in members) > 32*1024*1024:
            raise ValueError("ORK: archive member/expanded size limit")
        names = set()
        for member in members:
            name = member.filename.replace("\\", "/")
            if name in names or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or ":" in name:
                raise ValueError("ORK: duplicate/unsafe archive path")
            names.add(name)
            if (member.external_attr >> 16) & 0o170000 == 0o120000 or member.flag_bits & 1:
                raise ValueError("ORK: symlink/encrypted archive not allowed")
            if member.file_size > 8*1024*1024 or member.file_size > max(4096, member.compress_size*100):
                raise ValueError("ORK: decompression limit")
        if "rocket.ork" not in names:
            raise ValueError("ORK: expected rocket.ork archive member")
        return archive.read("rocket.ork")


def Ork_Import(path: Path) -> Design:
    raw = _Ork_Read(path)
    if len(raw) > 8*1024*1024:
        raise ValueError("ORK: XML exceeds 8 MiB")
    try:
        root = ElementTree.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except (DefusedXmlException, ParseError) as exc:
        raise ValueError(f"ORK: unsafe or malformed XML: {exc}") from exc
    version = root.get("version", "")
    if root.tag != "openrocket" or version not in ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9", "1.10"):
        raise ValueError("ORK: supported design versions are 1.0..1.10")
    queue = [(root, 0)]
    for element, depth in queue:
        if depth > 24 or len(queue) > 4096:
            raise ValueError("ORK: XML depth/node limit")
        queue.extend((child, depth+1) for child in element)
    rocket = root.find("rocket")
    if rocket is None or len(root.findall("rocket")) != 1:
        raise ValueError("ORK: exactly one rocket is required")
    stages = rocket.findall("./subcomponents/stage")
    if len(stages) != 1:
        raise ValueError("ORK: only one ordinary stage is supported")
    issues = ["aero: 请核对并明确输入气动系数；ORK 几何不等于气动模型"]
    parts, counter = [], 0
    supported = {"nosecone": "nose", "bodytube": "tube", "transition": "transition",
                 "trapezoidfinset": "fins", "masscomponent": "mass", "innertube": "tube"}
    # The official format is extensible. Only fields interpreted below and
    # presentation metadata may be omitted without a blocking physics issue.
    # https://openrocket.readthedocs.io/en/latest/dev_guide/file_specification.html
    presentation = {"id", "name", "comment", "color", "linestyle", "appearance",
                    "insideappearance", "finish", "designer", "designtype", "kitname", "revision"}
    handled = {"subcomponents", "length", "packedlength", "rootchord", "radius", "aftradius",
               "outerradius", "packedradius", "position", "axialoffset", "mass", "overridemass",
               "thickness", "material", "overridesubcomponents", "overridecg", "overridecd",
               "instancecount", "cant", "radialposition", "radialdirection"}
    for owner in (rocket, stages[0]):
        if len(owner.findall("subcomponents")) != 1:
            raise ValueError(f"ORK {owner.tag}: exactly one subcomponents container is required")
        for field in owner:
            if field.tag not in presentation | {"subcomponents"}:
                issues.append(f"{owner.tag}.{field.tag}: 未支持的装配/配置字段，需人工核对")

    def number(node, key, default=None):
        text = node.findtext(key)
        if text is None:
            return default
        try:
            value = float(text)
        except ValueError as exc:
            raise ValueError(f"ORK {node.tag}.{key}: auto/unknown values require explicit geometry") from exc
        if not math.isfinite(value):
            raise ValueError(f"ORK {node.tag}.{key}: nonfinite")
        return value

    # Iterative traversal keeps arbitrary XML nesting out of Python recursion.
    pending = [(stages[0], None, 0., 0., 0.)]
    while pending:
        parent, parent_id, parent_front, parent_length, parent_cg = pending.pop(0)
        after = 0.
        for node in parent.findall("./subcomponents/*"):
            counter += 1
            identity = node.findtext("id") or f"ork-{counter}"
            if node.tag not in supported:
                issues.append(f"{identity}: 未支持关键部件 {node.tag}，需人工建模")
                continue
            for field in node:
                if field.tag in handled and len(node.findall(field.tag)) != 1:
                    raise ValueError(f"{identity}.{field.tag}: duplicate physical field")
                if field.tag not in presentation | handled:
                    issues.append(f"{identity}.{field.tag}: 未支持的物理字段，需人工核对")
            for dimension, keys in (("length", ("length", "packedlength", "rootchord")),
                                    ("radius", ("radius", "aftradius", "outerradius", "packedradius"))):
                if not any(node.find(key) is not None for key in keys):
                    issues.append(f"{identity}.{dimension}: 缺失尺寸；0.01 m 仅预览占位，禁止物理计算")
            length = number(node, "length", number(node, "packedlength", number(node, "rootchord", .01)))
            radius = number(node, "radius", number(node, "aftradius", number(node, "outerradius", number(node, "packedradius", .01))))
            placement = node.find("axialoffset")
            if placement is None:
                placement = node.find("position")
            method = placement.get("method", placement.get("type", "after")) if placement is not None else "after"
            offset = float(placement.text or "0") if placement is not None else 0.
            if method in ("top", "front"):
                local_front = offset
            elif method in ("bottom", "aft"):
                local_front = parent_length-length+offset
            elif method in ("middle", "center"):
                local_front = (parent_length-length)/2+offset
            elif method == "after":
                local_front = after+offset
            elif method == "absolute":
                local_front = offset-parent_front
            else:
                raise ValueError(f"{identity}: unsupported position method {method}")
            after = local_front+length
            front = parent_front+local_front
            center = front+length/2
            mass = number(node, "mass", number(node, "overridemass"))
            thickness = number(node, "thickness", 0.)
            if not 0 <= thickness <= radius:
                raise ValueError(f"{identity}.thickness: wall thickness must be within outer radius")
            material = node.find("material")
            density = float(material.get("density")) if material is not None and material.get("density") else None
            if density is not None and (not math.isfinite(density) or density <= 0):
                raise ValueError(f"{identity}.material.density: positive finite density required")
            if mass is None and density and node.tag in ("bodytube", "innertube") and 0 < thickness <= radius:
                if material.get("type") != "bulk":
                    issues.append(f"{identity}.material.type: 非体密度，不能以 kg/m³ 推导筒体质量")
                else:
                    mass = density*math.pi*(radius**2-(radius-thickness)**2)*length
            if node.findtext("overridesubcomponents") == "true":
                issues.append(f"{identity}: 子树质量覆盖需明确替代关系，当前不计为可运行")
            if node.find("overridecg") is not None or node.find("overridecd") is not None:
                issues.append(f"{identity}: CG/CD 覆盖尚需人工输入")
            instance_count = number(node, "instancecount", 1.)
            if instance_count != 1:
                issues.append(f"{identity}: 重复实例 {instance_count} 需逐个建模，未静默复制质量")
            for key in ("cant", "radialposition", "radialdirection"):
                if number(node, key, 0.) != 0:
                    issues.append(f"{identity}.{key}: 非轴向安装尚需显式变换")
            if node.tag in ("nosecone", "transition", "trapezoidfinset"):
                issues.append(f"{identity}: {node.tag} 的质心/惯量需要显式审核，当前仅几何预览")
            parts.append(Part(identity, node.findtext("name") or node.tag, supported[node.tag], parent_id,
                              (0., 0., -(center-parent_cg)), mass_kg=mass, length_m=length,
                              radius_m=radius, inner_radius_m=max(0., radius-thickness) if thickness else 0.,
                              provenance=f"OpenRocket {version}; x_aft mapped to -z_body; explicit/derived own mass"))
            pending.append((node, identity, front, length, center))
    if not parts:
        raise ValueError("ORK: no supported components")
    design = Design(str(uuid4()), rocket.findtext("name") or path.stem, tuple(parts), None,
                    scenario=Scenario(aero_provenance="missing: ORK geometry only"),
                    assumptions=("OpenRocket 几何子集导入；不宣称仿真等价。", f"Source SHA256 {hashlib.sha256(raw).hexdigest()}"),
                    import_issues=tuple(issues))
    Design_Validate(design, runnable=False)
    return design
