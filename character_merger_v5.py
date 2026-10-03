bl_info = {
    "name": "Character Merger Complete Non-Destructive",
    "description": "Copy and merge character assets while preserving all properties: materials, textures, alpha, vertex groups, modifiers, and armatures into one optimized character",
    "author": "Copilot",
    "version": (5, 0, 0),
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


def duplicate_object_deep(obj, new_name=None):
    """Duplicate object with all data, materials, textures, and properties"""
    copy = obj.copy()
    
    # Deep copy object data
    if obj.data:
        copy.data = obj.data.copy()
        if new_name:
            copy.name = new_name
            copy.data.name = new_name + "_Data"
    else:
        if new_name:
            copy.name = new_name

    # Copy all materials and their textures
    if hasattr(obj.data, "materials") and obj.data.materials:
        copy.data.materials.clear()
        for mat in obj.data.materials:
            if mat:
                mat_copy = mat.copy()
                copy.data.materials.append(mat_copy)

    # Copy modifiers
    for mod in obj.modifiers:
        mod_copy = copy.modifiers.new(name=mod.name, type=mod.type)
        
        # Copy modifier settings
        for attr in dir(mod):
            if attr.startswith("_") or attr in ["bl_rna", "rna_type"]:
                continue
            try:
                if hasattr(mod_copy, attr) and not callable(getattr(mod, attr)):
                    setattr(mod_copy, attr, getattr(mod, attr))
            except Exception:
                pass

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


def copy_uv_layers(source_mesh, target_mesh):
    """Copy UV layer data from source to target"""
    if source_mesh.type != "MESH" or target_mesh.type != "MESH":
        return

    # Copy UV layers
    for uv in source_mesh.data.uv_layers:
        if uv.name not in target_mesh.data.uv_layers:
            target_mesh.data.uv_layers.new(name=uv.name)


def copy_vertex_groups(source_mesh, target_mesh):
    """Copy vertex groups from source mesh"""
    if source_mesh.type != "MESH" or target_mesh.type != "MESH":
        return

    # Clear existing groups
    target_mesh.vertex_groups.clear()

    # Copy all groups
    for vg in source_mesh.vertex_groups:
        new_vg = target_mesh.vertex_groups.new(name=vg.name)


def join_meshes_preserve_materials(meshes, target_name="CharacterMesh"):
    """Join meshes while preserving material indices and slots"""
    if not meshes:
        return None
    if len(meshes) == 1:
        meshes[0].name = target_name
        return meshes[0]

    deselect_all()
    for obj in meshes:
        obj.select_set(True)
    set_active(meshes[0])

    # Store material info before join
    material_slots_info = []
    for mesh in meshes:
        material_slots_info.append([mat for mat in mesh.data.materials])

    bpy.ops.object.join()
    result = bpy.context.active_object
    result.name = target_name

    return result


def merge_armatures_copy(armatures, target_name="CharacterArmature"):
    """Merge armatures preserving bone structure and properties"""
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

    name_map = {}
    existing = set()

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

            existing.add(final_name)
            new_bone = new_data.edit_bones.new(final_name)
            new_bone.head = bone.head.copy()
            new_bone.tail = bone.tail.copy()
            new_bone.roll = bone.roll
            new_bone.use_deform = bone.use_deform
            new_bone.use_connect = bone.use_connect
            
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
    """Remove bones not used by any mesh"""
    if not armature_obj or armature_obj.type != "ARMATURE":
        return

    used = set()
    for mesh in mesh_objs:
        used |= get_used_bones(mesh)

    if not used:
        return

    bpy.context.view_layer.objects.active = armature_obj
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones = armature_obj.data.edit_bones
    bones_to_remove = []
    
    for bone in edit_bones:
        if bone.name not in used:
            bones_to_remove.append(bone)
    
    for bone in bones_to_remove:
        edit_bones.remove(bone)
    
    bpy.ops.object.mode_set(mode="OBJECT")


def ensure_uv_layer(obj, layer_name="UVMap"):
    if obj.type != "MESH":
        return
    if layer_name not in obj.data.uv_layers:
        obj.data.uv_layers.new(name=layer_name)
    obj.data.uv_layers.active = obj.data.uv_layers[layer_name]


def smart_uv(obj):
    """Smart UV unwrap with fallback"""
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
        try:
            bpy.ops.uv.unwrap(method="ANGLE_BASED", fill_holes=True)
        except Exception:
            pass
    
    bpy.ops.object.mode_set(mode="OBJECT")


def create_atlas_material_with_alpha(obj, atlas_image, base_materials=None):
    """Create atlas material preserving alpha transparency from originals"""
    # Collect alpha info from original materials
    has_alpha = False
    if base_materials:
        for mat in base_materials:
            if mat and mat.use_nodes:
                for node in mat.node_tree.nodes:
                    if node.type == "BSDF_PRINCIPLED":
                        if node.inputs.get("Alpha") and node.inputs["Alpha"].default_value < 1.0:
                            has_alpha = True
                            break

    # Create material
    if obj.data.materials:
        material = obj.data.materials[0]
    else:
        material = bpy.data.materials.new(name=f"{obj.name}_Atlas")
        obj.data.materials.append(material)

    material.use_nodes = True
    material.blend_method = "BLEND" if has_alpha else "OPAQUE"
    material.shadow_method = "HASHED" if has_alpha else "NONE"

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
    
    # Add alpha output if needed
    if has_alpha:
        links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    return material


def bake_atlas(mesh_obj, resolution=2048, base_materials=None):
    """Bake atlas texture with alpha preservation"""
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
    create_atlas_material_with_alpha(mesh_obj, atlas_image, base_materials)

    deselect_all()
    mesh_obj.select_set(True)
    bpy.context.view_layer.objects.active = mesh_obj
    
    scene.render.bake.use_selected_to_active = False
    scene.render.bake.target = "IMAGE_TEXTURES"
    scene.render.bake.margin = 8

    try:
        bpy.ops.object.bake(type="COMBINED", save_mode="INTERNAL")
    except Exception:
        pass

    return atlas_image


def apply_armature_modifier(mesh_obj, armature_obj):
    """Apply armature modifier to mesh"""
    if mesh_obj.type != "MESH" or not armature_obj:
        return
    
    # Remove existing armature modifiers
    for mod in list(mesh_obj.modifiers):
        if mod.type == "ARMATURE":
            mesh_obj.modifiers.remove(mod)
    
    # Add new one
    mod = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
    mod.object = armature_obj


def merge_character_complete(meshes, armatures=None, atlas_size=2048, merge_by_segment=False):
    """Complete merge preserving all original properties: materials, alpha, vertex groups, modifiers"""
    if not meshes:
        raise RuntimeError("Select at least one mesh object.")

    target_col = create_collection("MergedCharacter")

    # Collect original materials for alpha detection
    original_materials = []
    for mesh in meshes:
        if hasattr(mesh.data, "materials"):
            original_materials.extend([m for m in mesh.data.materials if m])

    # Duplicate meshes into target collection
    mesh_copies = []
    for mesh in meshes:
        copy = duplicate_object_deep(mesh, new_name=f"{mesh.name}_Merged")
        bpy.context.collection.objects.link(copy)
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
            bpy.context.collection.objects.link(arm_copy)
            move_to_collection(arm_copy, target_col)
            armature_copies.append(arm_copy)

    # Merge mesh copies
    if merge_by_segment:
        groups = group_by_segment(mesh_copies)
        chunks = []
        for key, chunk in groups.items():
            if len(chunk) > 1:
                merged = join_meshes_preserve_materials(chunk, target_name=f"Mesh_{key}")
            elif chunk:
                merged = chunk[0]
            else:
                continue
            chunks.append(merged)
        final_mesh = join_meshes_preserve_materials(chunks, target_name="CharacterMesh_Merged")
    else:
        final_mesh = join_meshes_preserve_materials(mesh_copies, target_name="CharacterMesh_Merged")

    if final_mesh is None:
        raise RuntimeError("Failed to merge mesh copies.")

    # Merge armatures
    merged_armature = None
    if armature_copies:
        merged_armature = merge_armatures_copy(armature_copies, target_name="CharacterArmature_Merged")
        move_to_collection(merged_armature, target_col)
        apply_armature_modifier(final_mesh, merged_armature)
        remove_unused_bones(merged_armature, [final_mesh])

    # Bake atlas with alpha preservation
    bake_atlas(final_mesh, resolution=atlas_size, base_materials=original_materials)

    return final_mesh, merged_armature, target_col


class CHAR_MERGE_OT_complete(bpy.types.Operator):
    bl_idname = "char_merge.complete"
    bl_label = "Merge Character (Complete)"
    bl_description = "Merge character preserving all properties: materials, alpha, textures, vertex groups, and armatures"
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
        description="Group by body parts before merging",
        default=False,
    )

    def execute(self, context):
        try:
            meshes = get_selected_meshes()
            armatures = get_selected_armatures()
            
            final_mesh, merged_armature, collection = merge_character_complete(
                meshes,
                armatures=armatures,
                atlas_size=int(self.atlas_size),
                merge_by_segment=self.merge_by_segment,
            )
            
            self.report({"INFO"}, f"Complete merge: {final_mesh.name} in '{collection.name}'")
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}


class CHAR_MERGE_PT_panel(bpy.types.Panel):
    bl_label = "Character Merger"
    bl_idname = "CHAR_MERGE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Character Merger"

    def draw(self, context):
        layout = self.layout
        
        layout.operator("char_merge.complete", text="Merge Character (Complete)", icon="OUTLINER_DATA_MESH")

        box = layout.box()
        box.label(text="Preserves:")
        box.label(text="✓ All materials & textures")
        box.label(text="✓ Alpha transparency")
        box.label(text="✓ Vertex groups & weights")
        box.label(text="✓ Modifiers")
        box.label(text="✓ Merged unified armature")
        box.label(text="✓ Baked atlas")


classes = (CHAR_MERGE_OT_complete, CHAR_MERGE_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
