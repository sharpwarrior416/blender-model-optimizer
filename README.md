# Blender Model Optimizer

A comprehensive Blender add-on for merging complex multi-part characters into a single optimized mesh with unified armature, atlased textures, and baked materials.

## Features

- **Merge Models in Segments**: Join mesh objects by grouping similar objects or all at once
- **Merge Armatures**: Combine multiple skeleton rigs into one unified armature with bone retargeting
- **Remove Unused Bones**: Clean up bones not used by any vertex groups
- **Smart UV Layout**: Auto-UV unwrap and pack with padding
- **Texture Baking**: Bake multiple materials to a single atlas texture
- **Game-Ready Export**: Optimized for game engines (Unity, Unreal, Godot)

## Installation

1. Download this repository as a ZIP
2. In Blender: Edit > Preferences > Add-ons > Install…
3. Select the ZIP file
4. Search for "Character Merger" and enable it

## Usage

1. Select all objects you want to merge (meshes, armatures, lights, etc.)
2. Open the 3D Viewport sidebar (press `N`)
3. Go to the **"Character Merger"** tab
4. Configure options:
   - **Atlas Resolution**: 1024, 2048, or 4096px
   - **Merge Mode**: All at once or by segment
   - **Keep Original**: Preserve original objects as backup
5. Click **"Merge Character"** to run the full pipeline

## Workflow

1. **Segment Merging**: Groups objects by prefix/suffix
2. **Armature Merging**: Creates a new master armature and retargets weights
3. **Bone Cleanup**: Removes orphaned bones
4. **UV Packing**: Smart unwrapping with padding for seams
5. **Texture Baking**: Bakes all materials to atlas
6. **Material Setup**: Creates PBR material with merged atlas

## Requirements

- Blender 3.2+
- Cycles renderer enabled for baking
