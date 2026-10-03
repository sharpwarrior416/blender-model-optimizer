bl_info = {
    "name": "Character Merger",
    "description": "Merge character parts into one optimized mesh, combine armatures, remove unused bones, and bake a single atlas texture",
    "author": "Copilot",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > Character Merger",
    "category": "Object",
}

import bpy
import re
from collections import defaultdict


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def clear_select():
    bpy.ops.object.select_all(action="DESELECT")


def set_active(obj):
    bpy.context.view_layer.objects.active = obj


def get_selected_meshes():
    return [obj for obj in bpy.context.selected_objects if obj.type == "MESH"]


def get_selected_armatures():
    return [obj for obj in bpy.context.selected_objects if obj.type == "ARMATURE"]


# -----------------------------------------------------------------------------
# Segment grouping
# -----------------------------------------------------------------------------

def segment_name(obj_name):
    name = obj_name.lower()
    # Try to infer a body-part label from names like body, head, arm, leg, hair
    for token in [
        "head",
        "hair",
        "body",
        "torso",
        "chest",
        "arm",
        "leftarm",
        "rightarm",
        "forearm",
        "leg",
        "leftleg",
        "rightleg",
        "foot",
        "hand",
        "weapon",
        "cape",
        "cloak",
        "belt",
    ]:
        if token in name:
            return token.capitalize()

    # If no known keyword, use a generic label
    return "Part"


def group_meshes_by_segment(meshes):
    groups = defaultdict(list)
    for mesh in meshes:
        groups[segment_name(mesh.name)].append(mesh)
    return groups


# -----------------------------------------------------------------------------
# Model joining
# -----------------------------------------------------------------------------

def join_mesh_objects(meshes, new_name="CharacterMesh"):
    if not meshes:
        return None

    if len(meshes) == 1:
        mesh = meshes[0]
        mesh.name = new_name
        return mesh

    clear_select()
    for obj in meshes:
        obj.select_set(True)

    set_active(meshes[0])
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = new_name
    return joined


# -----------------------------------------------------------------------------
# Armature merging
# -----------------------------------------------------------------------------

def build_merged_armature(source_armatures, new_name="CharacterArmature"):
    if not source_armatures:
        return None

    if len(source_armatures) == 1:
        arm = source_armatures[0]
        arm.name = new_name
        return arm

    arm_data = bpy.data.armatures.new(new_name)
    arm_obj = bpy.data.objects.new(new_name, arm_data)
    bpy.context.collection.objects.link(arm_obj)

    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode="EDIT")

    # Track existing bone names to avoid duplicates
    bone_name_map = {}

    for src_arm in source_armatures:
        if src_arm.type != "ARMATURE":
            continue

        for bone in src_arm.data.edit_bones:
            # If the bone name exists, use a unique name
            safe_name = bone.name
            idx = 1
            while safe_name in bone_name_map:
                safe_name = f"{bone.name}_{idx}"
                idx += 1

            new_bone = arm_data.edit_bones.new(safe_name)
            new_bone.head = bone.head.copy()
            new_bone.tail = bone.tail.copy()
            new_bone.roll = bone.roll

            bone_name_map[bone.name] = safe_name

            if bone.parent:
                parent_name = bone.parent.name
                if parent_name in bone_name_map:
                    new_bone.parent = arm_data.edit_bones.get(bone_name_map[parent_name])

    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


# -----------------------------------------------------------------------------
# Bone cleanup
# -----------------------------------------------------------------------------

def get_used_bone_names(mesh_obj):
    bones = set()
    if mesh_obj.type != "MESH":
        return bones

    for vg in mesh_obj.vertex_groups:
        bones.add(vg.name)
    return bones


def remove_unused_bones(mesh_obj, armature_obj):
    if not armature_obj or armature_obj.type != "ARMATURE":
        return

    used = get_used_bone_names(mesh_obj)
    if not used:
        return

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")

    edit_bones = armature_obj.data.edit_bones
    for bone in list(edit_bones):
        if bone.name not in used:
            edit_bones.remove(bone)

    bpy.ops.object.mode_set(mode="OBJECT")


# -----------------------------------------------------------------------------
# UV setup
# -----------------------------------------------------------------------------

def ensure_uv_layer(obj, name="UVMap"):
    if obj.type != "MESH":
        return

    if name not in obj.data.uv_layers:
        obj.data.uv_layers.new(name=name)
    obj.data.uv_layers.active = obj.data.uv_layers[name]


# -----------------------------------------------------------------------------
# Bake atlas
# -----------------------------------------------------------------------------

def create_atlas_material(obj, image_name, atlas_size):
    if obj.type != "MESH":
        return None

    material = bpy.data.materials.new(name="CharacterAtlasMaterial")
    material.use_nodes = True

    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    output = nodes.new(type="ShaderNodeOutputMaterial")
    output.location = (400, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (180, 0)

    tex = nodes.new(type="ShaderNodeTexImage")
    tex.location = (-220, 0)

    atlas_image = bpy.data.images.get(image_name)
    if atlas_image is None:
        atlas_image = bpy.data.images.new(image_name, atlas_size, atlas_size, alpha=True)
    tex.image = atlas_image

    uv = nodes.new(type="ShaderNodeUVMap")
    uv.location = (-480, 0)
    uv.uv_map = "UVMap"

    links.new(uv.outputs["UV"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    if obj.data.materials:
        obj.data.materials[0] = material
    else:
        obj.data.materials.append(material)

    return material


def bake_atlas(mesh_obj, atlas_size=2048, bake_type="COMBINED"):
    if mesh_obj is None or mesh_obj.type != "MESH":
        return None

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64

    # Make sure we have a UV layer and simple unwrap to support baking.
    ensure_uv_layer(mesh_obj)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Smart unwrap for atlas packing.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
    except Exception:
        bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True)
    bpy.ops.object.mode_set(mode="OBJECT")

    image_name = "CharacterAtlas"
    atlas_image = bpy.data.images.get(image_name)
    if atlas_image is None:
        atlas_image = bpy.data.images.new(image_name, atlas_size, atlas_size, alpha=True)
    else:
        atlas_image.generated_color = (0.0, 0.0, 0.0, 0.0)
        atlas_image.scale(atlas_size, atlas_size)

    create_atlas_material(mesh_obj, image_name, atlas_size)

    # Required for baking to an image texture
    bpy.context.view_layer.objects.active = mesh_obj
    obj = mesh_obj
    obj.select_set(True)

    # Set scene bake options
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.target = "IMAGE_TEXTURES"
    scene.render.bake.margin = 4

    # Bake
    bpy.ops.object.bake(type=bake_type, save_mode="INTERNAL")
    return atlas_image


# -----------------------------------------------------------------------------
# Final merge workflow
# -----------------------------------------------------------------------------

def merge_character(selected_objects, atlas_size=2048, merge_by_segment=False):
    meshes = [obj for obj in selected_objects if obj.type == "MESH"]
    armatures = [obj for obj in selected_objects if obj.type == "ARMATURE"]

    if not meshes:
        raise RuntimeError("Select at least one mesh object.")

    if merge_by_segment:
        grouped = group_meshes_by_segment(meshes)
        merged_parts = []
        for _, part_meshes in grouped.items():
            merged_part = join_mesh_objects(part_meshes, new_name=f"{segment_name(part_meshes[0].name)}_Merged")
            if merged_part:
                merged_parts.append(merged_part)
        final_mesh = join_mesh_objects(merged_parts, new_name="CharacterMesh")
    else:
        final_mesh = join_mesh_objects(meshes, new_name="CharacterMesh")

    if final_mesh is None:
        raise RuntimeError("Could not create final merged mesh.")

    if armatures:
        merged_armature = build_merged_armature(armatures, new_name="CharacterArmature")
        if merged_armature:
            # Assign armature modifier to the merged mesh
            mod = final_mesh.modifiers.new(name="Armature", type="ARMATURE")
            mod.object = merged_armature
            remove_unused_bones(final_mesh, merged_armature)

    # Ensure there is a material to place the atlas image on
    bake_atlas(final_mesh, atlas_size=atlas_size, bake_type="COMBINED")

    return final_mesh


# -----------------------------------------------------------------------------
# Operators
# -----------------------------------------------------------------------------

class CHAR_MERGE_OT_merge_character(bpy.types.Operator):
    bl_idname = "char_merge.merge_character"
    bl_label = "Merge Character"
    bl_description = "Join all selected meshes into one character, merge armatures, and bake an atlas"
    bl_options = {"REGISTER", "UNDO"}

    atlas_size: bpy.props.EnumProperty(
        name="Atlas Resolution",
        items=[
            ("1024", "1024", "1024x1024"),
            ("2048", "2048", "2048x2048"),
            ("4096", "4096", "4096x4096"),
        ],
        default="2048",
    )

    merge_by_segment: bpy.props.BoolProperty(
        name="Merge by Segment",
        description="Merge objects by body part naming groups before combining all of them",
        default=False,
    )

    def execute(self, context):
        try:
            selected = list(context.selected_objects)
            if not selected:
                self.report({"ERROR"}, "Select at least one object.")
                return {"CANCELLED"}

            final_mesh = merge_character(
                selected,
                atlas_size=int(self.atlas_size),
                merge_by_segment=self.merge_by_segment,
            )
            self.report({"INFO"}, f"Merged character into {final_mesh.name}")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class CHAR_MERGE_PT_panel(bpy.types.Panel):
    bl_label = "Character Merger"
    bl_idname = "CHAR_MERGE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Character Merger"

    def draw(self, context):
        layout = self.layout
        layout.operator("char_merge.merge_character", icon="MESH_DATA")

        box = layout.box()
        box.label(text="Recommended workflow:")
        box.label(text="1. Select all character parts")
        box.label(text="2. Click Merge Character")
        box.label(text="3. Bake atlas and optimize final mesh")


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

classes = (
    CHAR_MERGE_OT_merge_character,
    CHAR_MERGE_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
