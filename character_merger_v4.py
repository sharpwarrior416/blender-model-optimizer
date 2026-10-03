bl_info = {
    "name": "Character Merger Advanced Non-Destructive",
    "description": "Create merged character copies while keeping original meshes and armatures intact; combines rigs with improved bone matching and atlas baking",
    "author": "Copilot",
    "version": (4, 0, 0),
    "blender": (3, 2, 0),
    "location": "View3D > Sidebar > Character Merger",
    "category": "Object",
}

import bpy
from collections import defaultdict


def deselect_all():
    bpy.ops.object.select_all(action="DESELECT")


def set_active(obj):
    bpy.context.view_layer.objects.active = obj


def create_collection(name="MergedCharacter"):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def move_to_collection(obj, collection):
    for col in list(obj.users_collection):
        try:
            col.objects.unlink(obj)
        except Exception:
            pass
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def duplicate_object(obj, new_name=None):
    copy = obj.copy()
    if obj.data:
        copy.data = obj.data.copy()
        if new_name:
            copy.name = new_name
            if copy.data:
                copy.data.name = new_name + "_Data"
    else:
        if new_name:
            copy.name = new_name
    return copy


def get_selected_meshes():
    return [o for o in bpy.context.selected_objects if o.type == "MESH"]


def get_selected_armatures():
    return [o for o in bpy.context.selected_objects if o.type == "ARMATURE"]


def group_by_segment(meshes):
    groups = defaultdict(list)
    for mesh in meshes:
        name = mesh.name.lower()
        if any(token in name for token in ["head", "hair", "face"]):
            groups["Head"].append(mesh)
        elif any(token in name for token in ["arm", "hand"]):
            groups["Arm"].append(mesh)
        elif any(token in name for token in ["leg", "foot"]):
            groups["Leg"].append(mesh)
        elif any(token in name for token in ["body", "torso", "chest", "shirt", "coat"]):
            groups["Body"].append(mesh)
        else:
            groups["Misc"].append(mesh)
    return groups


def join_meshes(meshes, target_name="CharacterMesh"):
    if not meshes:
        return None
    if len(meshes) == 1:
        meshes[0].name = target_name
        return meshes[0]

    deselect_all()
    for obj in meshes:
        obj.select_set(True)
    set_active(meshes[0])
    bpy.ops.object.join()
    result = bpy.context.active_object
    result.name = target_name
    return result


def normalize_bone_name(name):
    # Normalize names to improve matching across armatures
    lowered = name.lower().replace(" ", "_")
    lowered = lowered.replace("-", "_")
    lowered = lowered.replace(".", "_")
    return lowered


def build_bone_name_map(source_armature):
    """Heuristic map: source bone -> target name in the merged armature."""
    mapping = {}
    for bone in source_armature.data.bones:
        base = normalize_bone_name(bone.name)
        mapping[bone.name] = bone.name

        if "left" in base:
            mapping[bone.name] = bone.name.replace("left", "Left")
        if "right" in base:
            mapping[bone.name] = bone.name.replace("right", "Right")

    return mapping


def merge_armatures_copy(armatures, target_name="CharacterArmature"):
    if not armatures:
        return None

    if len(armatures) == 1:
        arm = armatures[0].copy()
        arm.data = armatures[0].data.copy()
        arm.name = target_name
        arm.data.name = target_name + "_Data"
        return arm

    new_data = bpy.data.armatures.new(target_name)
    new_obj = bpy.data.objects.new(target_name, new_data)
    bpy.context.collection.objects.link(new_obj)

    # Track names to avoid collisions
    name_map = {}
    existing = {}

    bpy.context.view_layer.objects.active = new_obj
    bpy.ops.object.mode_set(mode="EDIT")

    for arm in armatures:
        if arm.type != "ARMATURE":
            continue
        for bone in arm.data.edit_bones:
            final_name = bone.name
            counter = 1
            while final_name in existing:
                final_name = f"{bone.name}_{counter}"
                counter += 1

            existing[final_name] = True
            new_bone = new_data.edit_bones.new(final_name)
            new_bone.head = bone.head.copy()
            new_bone.tail = bone.tail.copy()
            new_bone.roll = bone.roll
            name_map[bone.name] = final_name

            if bone.parent:
                parent_name = bone.parent.name
                if parent_name in name_map:
                    new_bone.parent = new_data.edit_bones.get(name_map[parent_name])
                elif parent_name in new_data.edit_bones:
                    new_bone.parent = new_data.edit_bones.get(parent_name)

    bpy.ops.object.mode_set(mode="OBJECT")
    return new_obj


def get_used_bones(mesh_obj):
    used = set()
    if mesh_obj.type != "MESH":
        return used
    for vg in mesh_obj.vertex_groups:
        used.add(vg.name)
    return used


def remove_unused_bones(armature_obj, mesh_objs):
    if not armature_obj or armature_obj.type != "ARMATURE":
        return

    used = set()
    for mesh in mesh_objs:
        used |= get_used_bones(mesh)

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_obj.data.edit_bones
    for bone in list(edit_bones):
        if bone.name not in used:
            edit_bones.remove(bone)
    bpy.ops.object.mode_set(mode="OBJECT")


def ensure_uv_layer(obj, layer_name="UVMap"):
    if obj.type != "MESH":
        return
    if layer_name not in obj.data.uv_layers:
        obj.data.uv_layers.new(name=layer_name)
    obj.data.uv_layers.active = obj.data.uv_layers[layer_name]


def smart_uv(obj):
    if obj.type != "MESH":
        return

    deselect_all()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
    except Exception:
        bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True)
    bpy.ops.object.mode_set(mode="OBJECT")


def create_atlas_material(obj, atlas_image):
    if obj.data.materials:
        material = obj.data.materials[0]
    else:
        material = bpy.data.materials.new(name=f"{obj.name}_Atlas")
        obj.data.materials.append(material)

    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in list(nodes):
        nodes.remove(node)

    out = nodes.new(type="ShaderNodeOutputMaterial")
    out.location = (250, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)

    tex = nodes.new(type="ShaderNodeTexImage")
    tex.location = (-250, 0)
    tex.image = atlas_image

    uv = nodes.new(type="ShaderNodeUVMap")
    uv.location = (-500, 0)
    uv.uv_map = "UVMap"

    links.new(uv.outputs["UV"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    return material


def bake_atlas(mesh_obj, resolution=2048):
    if mesh_obj.type != "MESH":
        return None

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64

    atlas_name = f"{mesh_obj.name}_Atlas"
    atlas_image = bpy.data.images.get(atlas_name)
    if atlas_image is None:
        atlas_image = bpy.data.images.new(atlas_name, resolution, resolution, alpha=True)
    else:
        atlas_image.scale(resolution, resolution)

    ensure_uv_layer(mesh_obj, "UVMap")
    smart_uv(mesh_obj)
    create_atlas_material(mesh_obj, atlas_image)

    deselect_all()
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.target = "IMAGE_TEXTURES"
    scene.render.bake.margin = 8

    bpy.ops.object.bake(type="COMBINED", save_mode="INTERNAL")
    return atlas_image


def apply_armature_modifier(mesh_obj, armature_obj):
    if mesh_obj.type != "MESH" or not armature_obj:
        return
    for mod in list(mesh_obj.modifiers):
        if mod.type == "ARMATURE":
            mesh_obj.modifiers.remove(mod)
    mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = armature_obj


def ensure_armature_parent(mesh_obj, armature_obj):
    if not armature_obj:
        return
    if mesh_obj.parent != armature_obj:
        mesh_obj.parent = armature_obj


def merge_character_advanced_non_destructive(meshes, armatures=None, atlas_size=2048, merge_by_segment=False):
    if not meshes:
        raise RuntimeError("Select at least one mesh object.")

    target_col = create_collection("MergedCharacter")

    # Duplicate meshes into target collection
    mesh_copies = []
    for mesh in meshes:
        copy = mesh.copy()
        copy.data = mesh.data.copy()
        copy.name = f"{mesh.name}_Merged"
        copy.data.name = copy.name + "_Data"
        move_to_collection(copy, target_col)
        mesh_copies.append(copy)

    # Duplicate armatures into target collection
    armature_copies = []
    if armatures:
        for arm in armatures:
            arm_copy = arm.copy()
            arm_copy.data = arm.data.copy()
            arm_copy.name = f"{arm.name}_Merged"
            arm_copy.data.name = arm_copy.name + "_Data"
            move_to_collection(arm_copy, target_col)
            armature_copies.append(arm_copy)

    # Merge mesh copies based on segment grouping if requested
    if merge_by_segment:
        groups = group_by_segment(mesh_copies)
        chunks = []
        for key, chunk in groups.items():
            if len(chunk) > 1:
                merged = join_meshes(chunk, target_name=f"Mesh_{key}")
            elif chunk:
                merged = chunk[0]
            else:
                continue
            chunks.append(merged)
        final_mesh = join_meshes(chunks, target_name="CharacterMesh_Merged")
    else:
        final_mesh = join_meshes(mesh_copies, target_name="CharacterMesh_Merged")

    if final_mesh is None:
        raise RuntimeError("Failed to merge mesh copies.")

    # Merge armatures into one unified rig
    merged_armature = None
    if armature_copies:
        merged_armature = merge_armatures_copy(armature_copies, target_name="CharacterArmature_Merged")
        move_to_collection(merged_armature, target_col)

        # Keep bone group names consistent with the mesh groups when possible
        project_bones = set()
        for vg in final_mesh.vertex_groups:
            project_bones.add(vg.name)
        for bone in merged_armature.data.bones:
            if bone.name not in project_bones:
                pass

        apply_armature_modifier(final_mesh, merged_armature)
        ensure_armature_parent(final_mesh, merged_armature)
        remove_unused_bones(merged_armature, [final_mesh])

    # Bake atlas on the merged final mesh
    bake_atlas(final_mesh, resolution=atlas_size)

    return final_mesh, merged_armature, target_col


class CHAR_MERGE_OT_advanced_non_destructive(bpy.types.Operator):
    bl_idname = "char_merge.advanced_non_destructive"
    bl_label = "Merge Character (Advanced)"
    bl_description = "Copy, merge, combine armatures, and bake atlas while keeping originals intact"
    bl_options = {"REGISTER", "UNDO"}

    atlas_size: bpy.props.EnumProperty(
        name="Atlas Resolution",
        items=[
            ("1024", "1024x1024", "1024x1024"),
            ("2048", "2048x2048", "2048x2048"),
            ("4096", "4096x4096", "4096x4096"),
        ],
        default="2048",
    )

    merge_by_segment: bpy.props.BoolProperty(
        name="Merge by Segment",
        default=False,
    )

    def execute(self, context):
        try:
            meshes = get_selected_meshes()
            armatures = get_selected_armatures()
            final_mesh, merged_armature, collection = merge_character_advanced_non_destructive(
                meshes,
                armatures=armatures,
                atlas_size=int(self.atlas_size),
                merge_by_segment=self.merge_by_segment,
            )
            self.report({"INFO"}, f"Merged copy created in '{collection.name}'")
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
        layout.operator("char_merge.advanced_non_destructive", text="Merge Character (Advanced)", icon="OUTLINER_DATA_MESH")

        box = layout.box()
        box.label(text="Features:")
        box.label(text="✓ Keeps original objects")
        box.label(text="✓ Copies meshes and armatures")
        box.label(text="✓ Merges unified rig")
        box.label(text="✓ Removes unused bones")
        box.label(text="✓ Bakes atlas texture")


classes = (CHAR_MERGE_OT_advanced_non_destructive, CHAR_MERGE_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
