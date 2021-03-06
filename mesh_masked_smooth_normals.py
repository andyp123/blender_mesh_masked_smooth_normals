#  ***** GPL LICENSE BLOCK *****
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#  All rights reserved.
#  ***** GPL LICENSE BLOCK *****

import bpy
import bmesh
import mathutils


# addon information
bl_info = {
    "name": "Masked Soften/Harden Normals",
    "author": "Andrew Palmer",
    "version": (0, 0, 4),
    "blender": (2, 75, 0),
    "location": "",
    "description": "Soften/Harden the vertex normals of a mesh using the current selection as a mask that defines which normals are affected.",
    "category": "Mesh"
}


def get_linked_faces(vertex, smooth_mode, ignore_selection=False):
    """Get faces linked to a particular vertex with mode and selection options"""

    if smooth_mode == "face":
        # smooth based only on selected faces
        ls_faces = [f for f in vertex.link_faces if f.select or ignore_selection] 
    elif smooth_mode == "edge":
        # smooth based on faces linked to selected edges
        ls_edges = [e for e in vertex.link_edges if e.select or ignore_selection]
        ls_faces = []
        for e in ls_edges:
            ls_faces.extend(e.link_faces)
    else:
        # smooth based on all neighboring faces
        ls_faces = [f for f in vertex.link_faces]

    return ls_faces

# OPERATES IN OBJECT MODE ONLY
def set_smooth_normals(mesh_data, vertex_indices, vertex_normals):
    """Write smooth vertex normals to the user normal data (mesh loops)."""

    me = mesh_data
    me.calc_normals_split()
    
    # create a structure that matches the required input of the normals_split_custom_set function
    clnors = [mathutils.Vector()] * len(me.loops)

    for loop in me.loops:
        vertex_normal = loop.normal
        vertex_index = loop.vertex_index

        if vertex_index in vertex_indices:
            idx = vertex_indices.index(vertex_index)
            vertex_normal = vertex_normals[idx]
        clnors[loop.index] = vertex_normal

    me.normals_split_custom_set(clnors)


# OPERATES IN OBJECT MODE ONLY
def flip_normals(mesh_data):
    me = mesh_data

    me.calc_normals_split()
    clnors = [mathutils.Vector(loop.normal) for loop in me.loops]

    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode='OBJECT')

    for p in me.polygons:
        if p.select:
            # flip the normals of the selected polygon
            ls = p.loop_start
            le = ls + p.loop_total
            clnors[ls:le] = [-n for n in clnors[ls:le]]
            # revert winding order :(
            ls = p.loop_start + 1
            le = ls + p.loop_total - 1
            clnors[ls:le] = reversed(clnors[ls:le])

    me.normals_split_custom_set(clnors)


# TODO: This should work on edge and vertex selections
# OPERATES IN OBJECT MODE ONLY
def harden_normals(mesh_data):
    """Harden normals based on selected faces"""

    me = mesh_data

    me.calc_normals_split()
    clnors = [loop.normal for loop in me.loops]

    for p in me.polygons:
        if p.select:
            ls = p.loop_start
            le = ls + p.loop_total
            clnors[ls:le] = list([p.normal] * p.loop_total)

    me.normals_split_custom_set(clnors)


# OPERATES IN OBJECT MODE ONLY
def set_specific_normal_vector(mesh_data, normal):
    """Set the selected normals to a specific direction vector"""

    me = mesh_data

    me.calc_normals_split()
    clnors = [loop.normal for loop in me.loops]

    n = normal.normalized()

    for p in me.polygons:
        if p.select:
            ls = p.loop_start
            le = ls + p.loop_total
            clnors[ls:le] = list([normal] * p.loop_total)

    me.normals_split_custom_set(clnors)


# OPERATES IN EDIT MODE ONLY
def get_smoothed_vertex_normals(mesh_data, smooth_mode="face"):
    """Smooth normals based on selection"""

    bm = bmesh.from_edit_mesh(mesh_data)

    vertex_indices = []
    vertex_normals = []

    selected_verts = [v for v in bm.verts if v.select]

    for v in selected_verts:
        ls_faces = get_linked_faces(v, smooth_mode)

        # set vertex normal to average of face normals
        if len(ls_faces) > 0:
            vertex_normal = mathutils.Vector()
            for f in ls_faces:
                vertex_normal += f.normal
            vertex_indices.append(v.index)
            vertex_normal.normalize()
            vertex_normals.append(vertex_normal)

    return {'vertex_indices': vertex_indices, 'vertex_normals': vertex_normals}


# TODO: Store face areas to avoid repeat calculation
#       add together area of neighboring face with the same normal
# OPERATES IN EDIT MODE ONLY
def get_face_weighted_normals(mesh_data, smooth_mode="face"):
    """Smooth normals weighted by face area"""

    bm = bmesh.from_edit_mesh(mesh_data)
    smooth_all = (smooth_mode == "all")

    vertex_indices = []
    vertex_normals = []

    if smooth_all:
        selected_verts = [v for v in bm.verts]
    else:
        selected_verts = [v for v in bm.verts if v.select]

    for v in selected_verts:
        if smooth_all:
            ls_faces = [f for f in v.link_faces]
        else:
            ls_faces = get_linked_faces(v, smooth_mode)

        if len(ls_faces) > 0:
            vertex_normal = mathutils.Vector()
            for f in ls_faces:
                vertex_normal += f.normal * f.calc_area()
            vertex_indices.append(v.index)
            vertex_normal.normalize()
            vertex_normals.append(vertex_normal)

    return {'vertex_indices': vertex_indices, 'vertex_normals': vertex_normals}


class FaceWeightedNormals(bpy.types.Operator):
    """Smooth custom normals weighted by face area"""
    bl_idname = "mesh.face_weighted_normals"
    bl_label = "Face Weighted Normals"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_data = context.object.data
        mesh_data.use_auto_smooth = True

        initial_mode = context.object.mode

        # get selection mode (VERT, EDGE, FACE)
        if initial_mode == "OBJECT":
            smooth_mode = "all"
        else:
            select_mode = context.tool_settings.mesh_select_mode
            if select_mode[2]:
                smooth_mode = "face"
            elif select_mode[1]:
                smooth_mode = "edge"
            else:
                smooth_mode = "vertex"

        bpy.ops.object.mode_set(mode="EDIT")
        vn = get_face_weighted_normals(mesh_data, smooth_mode)

        bpy.ops.object.mode_set(mode="OBJECT")
        set_smooth_normals(mesh_data, vn['vertex_indices'], vn['vertex_normals'])
        bpy.ops.object.mode_set(mode=initial_mode)

        return {'FINISHED'}

    @classmethod  
    def poll(cls, context):  
        obj = context.object  
        return obj is not None and obj.type == "MESH"


class MaskedSoftenNormals(bpy.types.Operator):
    """Smooth custom normals based on selection"""
    bl_idname = "mesh.masked_soften_normals"
    bl_label = "Masked Soften Normals"
    bl_options = {'REGISTER', 'UNDO'}

    always_use_face_mask = bpy.props.BoolProperty(
        name = "only use faces",
        default = False,
        subtype = 'NONE',
        description = "Only mask using selected faces regardless of the current selection mode"
        )

    def execute(self, context):
        mesh_data = context.object.data
        mesh_data.use_auto_smooth = True

        # get selection mode (VERT, EDGE, FACE)
        select_mode = context.tool_settings.mesh_select_mode
        if select_mode[2] or self.always_use_face_mask:
            vn = get_smoothed_vertex_normals(mesh_data, "face")
        elif select_mode[1]:
            vn = get_smoothed_vertex_normals(mesh_data, "edge")
        else:
            vn = get_smoothed_vertex_normals(mesh_data, "vertex")

        bpy.ops.object.mode_set(mode="OBJECT")
        set_smooth_normals(mesh_data, vn['vertex_indices'], vn['vertex_normals'])
        bpy.ops.object.mode_set(mode="EDIT")

        return {'FINISHED'}

    @classmethod  
    def poll(cls, context):  
        obj = context.object  
        return obj is not None and obj.type == "MESH" and obj.mode == 'EDIT' 


# TODO: Make a harden normals tool that works in the same way as smooth normals
class MaskedHardenNormals(bpy.types.Operator):
    """Harden custom normals based on selection"""
    bl_idname = "mesh.masked_harden_normals"
    bl_label = "Masked Harden Normals"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        mesh_data = context.object.data
        mesh_data.use_auto_smooth = True

        bpy.ops.object.mode_set(mode="OBJECT")
        harden_normals(mesh_data)
        bpy.ops.object.mode_set(mode="EDIT")

        return {'FINISHED'}

    @classmethod  
    def poll(cls, context):  
        obj = context.object  
        return obj is not None and obj.type == "MESH" and obj.mode == 'EDIT' 


class FlipCustomNormals(bpy.types.Operator):
    """Flip active mesh's normals, including custom ones"""
    bl_idname = "mesh.masked_flip_custom_normals"
    bl_label = "Flip Custom Normals"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object  
        return obj is not None and obj.type == "MESH" and obj.mode == 'EDIT' 

    def execute(self, context):
        mesh_data = context.object.data
        mesh_data.use_auto_smooth = True

        bpy.ops.object.mode_set(mode='OBJECT')
        flip_normals(mesh_data)
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}


class SetSpecificNormalVector(bpy.types.Operator):
    """Precisely set the normals of selected vertices"""
    bl_idname = "mesh.set_specific_custom_normal"
    bl_label = "Set Specific Custom Normals"
    bl_options = {'REGISTER','UNDO'}

    custom_normal = bpy.props.FloatVectorProperty(
        name = "vertex normal direction",
        default = (0.0,0.0,1.0),
        subtype = 'DIRECTION',
        description = "Value to set selected vertex normals to"
        )
    allow_split_normals = bpy.props.BoolProperty(
        name = "allow split normals",
        default = False,
        subtype = 'NONE',
        description = "Allow split normals at edge of face selection"
        )

    @classmethod
    def poll(cls, context):
        obj = context.object  
        return obj is not None and obj.type == "MESH" and obj.mode == 'EDIT' 

    def execute(self, context):
        mesh_data = context.object.data
        mesh_data.use_auto_smooth = True

        if context.tool_settings.mesh_select_mode[2] and self.allow_split_normals:
            bpy.ops.object.mode_set(mode='OBJECT')
            set_specific_normal_vector(mesh_data, self.custom_normal)
        else:
            bm = bmesh.from_edit_mesh(mesh_data)
            vertex_indices = [v.index for v in bm.verts if v.select]
            vertex_normals = [self.custom_normal] * len(vertex_indices)
            bpy.ops.object.mode_set(mode='OBJECT')
            set_smooth_normals(mesh_data, vertex_indices, vertex_normals)
        
        bpy.ops.object.mode_set(mode='EDIT')

        return {'FINISHED'}


class SoftenHardenNormalsPanel(bpy.types.Panel):
    """COMMENT"""
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_context = "mesh_edit"
    bl_category = "Shading / UVs"
    bl_label = "Custom Normals"

    def draw(self, context):
        layout = self.layout

        obj = context.object
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("mesh.face_weighted_normals", text="Set Weighted Normals")
        row = col.row(align=True)
        row.operator("mesh.masked_soften_normals", text="Soften")
        row.operator("mesh.masked_harden_normals", text="Harden")
        col = layout.column(align=True)
        row = col.row(align=True)
        row.operator("mesh.masked_flip_custom_normals", text="Flip Direction")
        row = col.row(align=True)
        row.operator("mesh.set_specific_custom_normal", text="Set Direction")


# operator registration
def register():  
    bpy.utils.register_class(MaskedSoftenNormals)
    bpy.utils.register_class(MaskedHardenNormals)
    bpy.utils.register_class(FaceWeightedNormals)
    bpy.utils.register_class(FlipCustomNormals)
    bpy.utils.register_class(SetSpecificNormalVector)
    bpy.utils.register_class(SoftenHardenNormalsPanel)

def unregister():
    bpy.utils.unregister_class(MaskedSoftenNormals)
    bpy.utils.unregister_class(MaskedHardenNormals)
    bpy.utils.unregister_class(FaceWeightedNormals)
    bpy.utils.unregister_class(FlipCustomNormals)
    bpy.utils.unregister_class(SetSpecificNormalVector)
    bpy.utils.unregister_class(SoftenHardenNormalsPanel)
  
if __name__ == "__main__":  
    register()  
