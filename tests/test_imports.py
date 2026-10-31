from dataclasses import replace
import hashlib
import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

from treediagram.design import Design_CreateExample, Design_Validate
from treediagram.importers import Motor_Import, Motor_DeriveRoundoff, Ork_Import
from treediagram.io import Json_Decode
from treediagram.vendor_motor.contract import MotorPackage_Load, MotorPackage_Digest

FIXTURES=Path(__file__).parent/"fixtures"


def test_vendored_motor_contract_and_golden_files_match_pinned_owner():
    root=Path(__file__).resolve().parents[1]
    provenance=json.loads((root/"contracts/motor-test-package/v1/PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["schema_id"]=="underline.motor-test-package/1"
    assert provenance["owner_repository"]=="https://github.com/aleistercrowleybeast666/Underline_RETLDC.git"
    assert provenance["owner_commit"]=="e4001bf730692f58071a1df4d1efad756bd84379"
    expected={"contracts/motor-test-package/v1/schema.json","src/treediagram/vendor_motor/contract.py"}
    expected.update(path.relative_to(root).as_posix() for path in (FIXTURES/"motor").glob("*.json"))
    assert set(provenance["files"])==expected
    for relative,record in provenance["files"].items():
        path=(root/relative).resolve()
        assert path.is_relative_to(root)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==record["sha256"],relative


def test_motor_roundtrip_preserves_origin_units_integral_and_installation():
    design=Design_CreateExample()
    candidate,changes=Motor_Import(FIXTURES/"motor/valid_positive.tdmotor.json",design)
    assert "thrust_n" in changes and candidate.motor.position_m==design.motor.position_m
    assert candidate.motor.gimbal_capable==design.motor.gimbal_capable
    assert candidate.motor.propellant_mass_kg==.15
    assert candidate.motor.dry_mass_kg==pytest.approx(.25)
    assert candidate.motor.length_m==.2 and candidate.motor.radius_m==.025
    assert np.trapezoid(candidate.motor.thrust_n,candidate.motor.time_s)==pytest.approx(200.)
    assert not candidate.motor.source["source_verified_independently"]
    again,changes=Motor_Import(FIXTURES/"motor/valid_positive.tdmotor.json",candidate)
    assert again==candidate and changes==()
    Design_Validate(candidate)


def test_negative_samples_require_explicit_derived_policy():
    candidate,_=Motor_Import(FIXTURES/"motor/valid_synthetic.tdmotor.json",Design_CreateExample())
    assert min(candidate.motor.thrust_n)<0
    with pytest.raises(ValueError,match="负推力"):Design_Validate(candidate)
    derived=Motor_DeriveRoundoff(candidate,1e-10)
    assert min(derived.motor.thrust_n)==0 and min(candidate.motor.thrust_n)<0
    assert derived.motor.source["package"]==candidate.motor.source["package"]
    assert derived.motor.source["derived_curve_policy"]["affected_indices"]
    with pytest.raises(ValueError):Motor_DeriveRoundoff(candidate,True)


def test_motor_hash_belongs_to_the_exact_parsed_snapshot(tmp_path, monkeypatch):
    from treediagram import importers

    path=tmp_path/"changing.tdmotor.json"
    original=(FIXTURES/"motor/valid_positive.tdmotor.json").read_bytes()
    path.write_bytes(original)
    decode=importers.Json_Decode
    def change_after_read(raw):
        result=decode(raw)
        path.write_bytes(b'{"replacement":"unrelated file"}')
        return result
    monkeypatch.setattr(importers,"Json_Decode",change_after_read)
    candidate,_=Motor_Import(path,Design_CreateExample())
    assert candidate.motor.source["file_sha256"]==hashlib.sha256(original).hexdigest()
    assert candidate.motor.source["file_sha256"]!=hashlib.sha256(path.read_bytes()).hexdigest()
    assert np.trapezoid(candidate.motor.thrust_n,candidate.motor.time_s)==pytest.approx(200.)


@pytest.mark.parametrize("missing",[("length_m",),("diameter_m",),("length_m","diameter_m")])
def test_missing_motor_geometry_requires_explicit_existing_installation(tmp_path, missing):
    package=MotorPackage_Load(FIXTURES/"motor/valid_positive.tdmotor.json")
    for key in missing:
        package["motor"][key]=None
    package["content_sha256"]=MotorPackage_Digest(package)
    path=tmp_path/"unknown-dimensions.tdmotor.json"
    path.write_text(json.dumps(package),encoding="utf-8")
    blank=replace(Design_CreateExample(),motor=None)
    with pytest.raises(ValueError,match="motor.*缺少尺寸"):
        Motor_Import(path,blank)
    assert blank.motor is None
    known=Design_CreateExample()
    known=replace(known,motor=replace(known.motor,length_m=.32,radius_m=.035))
    candidate,_=Motor_Import(path,known)
    for key in missing:
        field="radius_m" if key=="diameter_m" else key
        assert getattr(candidate.motor,field)==getattr(known.motor,field)
        assert candidate.motor.source["geometry_origin"][field]=="retained_project_installation"
    Design_Validate(candidate)


def test_motor_reimport_preserves_project_ignition_and_installation_policy():
    original=Design_CreateExample()
    original=replace(original,motor=replace(
        original.motor,ignition_s=1.25,position_m=(.01,.02,-.61),
        rotation_bm_wxyz=(0.,0.,0.,1.),gimbal_capable=False,
    ))
    candidate,_=Motor_Import(FIXTURES/"motor/valid_positive.tdmotor.json",original)
    for field in ("ignition_s","mass_model","position_m","rotation_bm_wxyz","gimbal_capable"):
        assert getattr(candidate.motor,field)==getattr(original.motor,field)
    Design_Validate(candidate)


def test_invalid_motor_golden_vectors_are_rejected():
    invalid=sorted((FIXTURES/"motor").glob("invalid*.tdmotor.json"))
    assert len(invalid)>=6
    for path in invalid:
        with pytest.raises(ValueError):MotorPackage_Load(path)


@pytest.mark.parametrize("raw",[b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}',b'['*33+b'0'+b']'*33])
def test_json_rejects_ambiguous_nonfinite_deep_inputs(raw):
    with pytest.raises(ValueError):Json_Decode(raw)


def test_ork_geometry_hierarchy_units_and_unknown_physics_blocked():
    design=Ork_Import(FIXTURES/"single-stage.ork")
    assert {p.kind for p in design.parts}>={"nose","tube","transition","fins","mass"}
    parts={p.id:p for p in design.parts}
    assert parts["electronics"].parent_id=="body"
    assert parts["body"].mass_kg==pytest.approx(600*np.pi*(.04**2-.037**2))
    assert parts["body"].position_m[2]==pytest.approx(-.7)
    assert Design_Validate(design,False)
    unknown=Ork_Import(FIXTURES/"unknown-component.ork")
    assert any("unknownSeparationMechanism" in issue for issue in unknown.import_issues)
    with pytest.raises(ValueError):Design_Validate(unknown)


def test_ork_rejects_entities_path_traversal_and_bombs(tmp_path):
    path=tmp_path/"bad.ork"
    path.write_bytes(b'<!DOCTYPE x [<!ENTITY x SYSTEM "file:///secret">]><openrocket version="1.10">&x;</openrocket>')
    with pytest.raises(Exception):Ork_Import(path)
    with zipfile.ZipFile(path,"w") as archive:
        archive.writestr("../rocket.ork",b"bad")
    with pytest.raises(ValueError,match="unsafe"):Ork_Import(path)
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("rocket.ork",b" "*100000)
    with pytest.raises(ValueError,match="decompression"):Ork_Import(path)


@pytest.mark.parametrize("field",[
    '<motormount><motor configid="m"><designation>A8</designation></motor></motormount>',
    '<clusterconfiguration>four</clusterconfiguration>',
    '<futureMassMultiplier>4</futureMassMultiplier>',
])
def test_ork_unhandled_physical_fields_cannot_silently_become_ready(tmp_path,field):
    path=tmp_path/"physical-field.ork"
    path.write_text(
        '<openrocket version="1.10"><rocket><subcomponents><stage><subcomponents>'
        '<bodytube><id>body</id><length>1</length><radius>0.05</radius><mass>1</mass>'
        +field+'</bodytube></subcomponents></stage></subcomponents></rocket></openrocket>',
        encoding="utf-8",
    )
    candidate=Ork_Import(path)
    key=field.split('>')[0].split()[0][1:]
    assert any(f"body.{key}" in issue for issue in candidate.import_issues)
    # Even after resolving the separate aero and propulsion requirements,
    # the unhandled original field remains a run blocker.
    candidate=replace(candidate,motor=Design_CreateExample().motor,
                      import_issues=tuple(i for i in candidate.import_issues if i.startswith("body.")))
    with pytest.raises(ValueError,match=key):Design_Validate(candidate)


def test_ork_invalid_wall_thickness_is_not_clamped_to_a_solid_tube(tmp_path):
    path=tmp_path/"thickness.ork"
    path.write_text(
        '<openrocket version="1.10"><rocket><subcomponents><stage><subcomponents>'
        '<bodytube><id>b</id><length>1</length><radius>0.01</radius><mass>1</mass>'
        '<thickness>0.02</thickness></bodytube></subcomponents></stage></subcomponents>'
        '</rocket></openrocket>',encoding="utf-8",
    )
    with pytest.raises(ValueError,match="thickness"):Ork_Import(path)


def test_ork_surface_density_and_missing_dimensions_remain_physical_blockers(tmp_path):
    path=tmp_path/"surface.ork"
    path.write_text(
        '<openrocket version="1.10"><rocket><subcomponents><stage><subcomponents>'
        '<bodytube><id>b</id><radius>0.05</radius><thickness>0.002</thickness>'
        '<material type="surface" density="100">surface material</material>'
        '</bodytube></subcomponents></stage></subcomponents></rocket></openrocket>',
        encoding="utf-8",
    )
    design=Ork_Import(path)
    assert design.parts[0].mass_kg is None
    assert any("b.material.type" in issue for issue in design.import_issues)
    assert any("b.length" in issue for issue in design.import_issues)
    with pytest.raises(ValueError):Design_Validate(design)


def test_ork_duplicate_physical_field_is_rejected(tmp_path):
    path=tmp_path/"duplicate-mass.ork"
    path.write_text(
        '<openrocket version="1.10"><rocket><subcomponents><stage><subcomponents>'
        '<bodytube><id>b</id><length>1</length><radius>0.05</radius>'
        '<mass>1</mass><mass>5</mass></bodytube>'
        '</subcomponents></stage></subcomponents></rocket></openrocket>',encoding="utf-8",
    )
    with pytest.raises(ValueError,match="duplicate physical field"):Ork_Import(path)
