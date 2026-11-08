#!/usr/bin/env python3
bl_info = {
    'name': 'XXMI Buffer Export',
    'blender': (3, 6, 0),
    'author': 'failsafe65#9445',
    'location': 'XXMI Tools panel',
    'description': 'Exports a 3DMigoto buffer that is compatible with the originally imported model.',
    'category': 'Export',
	'version': (1, 0, 0)
}

import os
import re
import bpy
import json
import struct
from pathlib import Path
from XXMITools.migoto.ui import XXMISidebarOptionsPanelBase
from XXMITools.migoto.datastructures import Fatal, GameEnum

class XXMI_PT_SidePanelBufferExport(XXMISidebarOptionsPanelBase, bpy.types.Panel):
	bl_label = ''
	bl_options = {'HIDE_HEADER'}
	bl_order = 100

	def draw(self, context):
		XXMISidebarOptionsPanelBase.draw(self, context)
		layout = self.layout
		col = layout.column()
		col.label(text="Export Buffer:")
		row = col.row(align=True)
		row.operator('xxmi.exportbuffer', text='Position').buffer=0
		row.operator('xxmi.exportbuffer', text='Blend').buffer=1
		row.operator('xxmi.exportbuffer', text='Texcoord').buffer=2
		row.operator('xxmi.exportbuffer', text='IB').buffer=3

class ExportBufferOperator(bpy.types.Operator):
	'''Export buffer operator'''
	bl_idname = 'xxmi.exportbuffer'
	bl_label = 'Export Buffer'
	bl_description = 'Export Buffer'
	bl_options = {'REGISTER'}
	
	buffer: bpy.props.IntProperty(
        name="Buffer",
        description="Which buffer to export",
        default = 0,
		min = 0,
		max = 3
    )

	def execute(self, context):
		xxmi = bpy.context.scene.xxmi

		if self.buffer == 0: # Position
			semantics = ('POSITION', 'NORMAL', 'TANGENT')
			suffix = 'Position.buf'
		elif self.buffer == 1: # Blend
			semantics = ('BLENDWEIGHT', 'BLENDINDICES')
			suffix = 'Blend.buf'
		elif self.buffer == 2:  # Texcoord
			if GameEnum[xxmi.game] == GameEnum.HonkaiImpactPart2:
				semantics = ('TEXCOORD',)
			else:
				semantics = ('COLOR', 'TEXCOORD')
			suffix = 'Texcoord.buf'
		else: # IB
			semantics = None
			suffix = '.ib'
		try:
			self.report({'INFO'}, f"Exported {export_3dmigoto_buffer(xxmi,context.object, semantics, suffix)}")
		except Fatal as e:
			self.report({'ERROR'}, str(e))
		return {'FINISHED'}
	
def export_3dmigoto_buffer(xxmi, selected, semantics, suffix):
	if not xxmi.destination_path:
		raise Fatal('Destination path not set')
	if not xxmi.dump_path:
		raise Fatal('Dump path not set')
	dumpPath = Path(xxmi.dump_path)
	if os.path.exists(dumpPath / 'hash.json'):
		with open(dumpPath / 'hash.json') as f:
			components = json.load(f)
	else:
		raise Fatal('Dump folder missing hash.json')
	
	# Find selected component
	selectedComponent = {}
	for component in components:
		componentName = dumpPath.stem + component['component_name']
		for part in component['object_classifications']:
			if selected.name.startswith(f'{componentName}{part}'):
				selectedComponent = component
				break
		else:
			continue
		break
	if not selectedComponent:
		raise Fatal(f'Selected component ({componentName}{part}) not found in hash.json')

	packCode = {'UNORM': {8: 'B'},
				'SNORM': {8: 'b'},
				'FLOAT': {32: 'f', 16: 'e'},
				'UINT': {32: 'I', 16: 'H'},
				'SINT': {32: 'i', 16: 'h'}}

	# Get all related objects
	objectNames = tuple(f'{componentName}{part}' for part in selectedComponent['object_classifications'])
	objects = sorted([obj for obj in bpy.context.view_layer.objects if obj.name.startswith(objectNames) and obj.visible_get()], key=lambda o: o.get('3DMigoto:FirstIndex'))

	if semantics:
		# Create helper dict for packing
		semanticPackInfo = {}
		for prop in selected.get('3DMigoto:VBLayout'):
			semanticName = prop.get('SemanticName')
			semanticIndex = prop.get('SemanticIndex')
			if semanticName.startswith(semantics):
				format = prop.get('Format')
				datatype = format.split('_')[1]
				bitwidth = re.split('G|B|A', format.split('_')[0][1:])
				dim = len(bitwidth)
				if (len(set(bitwidth)) != 1):
					raise Fatal('Variable width channels is not supported')
				bits = int(bitwidth[0])
				semanticPackInfo[f"{semanticName}{semanticIndex}"] = packCode[datatype][bits]*dim

		if 'TANGENT' in semantics:
			# Check for tangent attributes
			if 'TANGENT.x' in selected.data.attributes:
				tangentData = {v.index+sum([len(o.data.vertices) for o in objects[:i]]): (obj.data.attributes['TANGENT.x'].data[v.index].value,
																						  obj.data.attributes['TANGENT.y'].data[v.index].value,
																						  obj.data.attributes['TANGENT.z'].data[v.index].value,
																						  obj.data.attributes['TANGENT.w'].data[v.index].value)
																						  for i,obj in enumerate(objects)
																						  for v in obj.data.vertices}
			elif 'TANGENT.xy' in selected.data.attributes:
				tangentData = {v.index+sum([len(o.data.vertices) for o in objects[:i]]): (*obj.data.attributes['TANGENT.xy'].data[v.index].vector,
																						  *obj.data.attributes['TANGENT.zw'].data[v.index].vector)
																						  for i,obj in enumerate(objects)
																						  for v in obj.data.vertices}
			elif 'TANGENT.xyzw' in selected.data.attributes:
				tangentData = {v.index+sum([len(o.data.vertices) for o in objects[:i]]): tuple(obj.data.attributes['TANGENT.xyzw'].data[v.index].value)
																						  for i,obj in enumerate(objects)
																						  for v in obj.data.vertices}
			else:
				# Find tangent data in dump folder
				with open(dumpPath / f"{componentName}{selectedComponent['object_classifications'][0]}-vb0={selectedComponent['position_vb']}.txt") as f:
					tangentData = {int(line.split('[')[1].split(']')[0]): tuple(float(t) for t in line.replace(',','').split()[2:]) for line in f if 'TANGENT:' in line}

		# Build buffer
		bufbytes = bytearray()
		for i, obj in enumerate(objects):
			start = sum([len(o.data.vertices) for o in objects[:i]])
			if 'TEXCOORD' in semantics:
				loopdict = {}
				for l in obj.data.loops:
					loopdict[l.vertex_index] = l.index
			for v in obj.data.vertices:
				for s in semanticPackInfo:
					semanticData = []
					if s.startswith('POSITION'):
						semanticData = v.co
					elif s.startswith('NORMAL'):
						semanticData = v.normal
					elif s.startswith('TANGENT'):
						semanticData = tangentData[v.index+start]
					elif s.startswith('BLENDWEIGHT'):
						semanticData = [g.weight for g in v.groups]
						semanticData.extend([0]*4)
						del semanticData[4:]
					elif s.startswith('BLENDINDICES'):
						semanticData = [g.group for g in v.groups]
						semanticData.extend([0]*4)
						del semanticData[4:]
					elif s.startswith('COLOR'):
						semanticData = tuple(int(channel*255) for channel in obj.data.attributes['COLOR'].data[loopdict[v.index]].color_srgb)
					elif s.startswith('TEXCOORD'):
						uvindex = int(s.removeprefix('TEXCOORD'))
						semanticData = list(obj.data.uv_layers[uvindex].uv[loopdict[v.index]].vector)
						if obj.get(f"3DMigoto:TEXCOORD{uvindex if uvindex else ''}.xy")['flip_v']:
							semanticData[1] = 1 - semanticData[1]
					bufbytes.extend(struct.pack(semanticPackInfo[s], *semanticData))
	else: # Handle IB
		start = 0
		for obj in objects:
			if obj == selected:
				componentName += part
				bufbytes = bytearray()
				for p in selected.data.polygons:
					ibformat = selected.get('3DMigoto:IBFormat')
					bits = int(ibformat.split('_')[-2].replace('R',''))
					datatype = ibformat.split('_')[-1]
					for v in p.vertices:
						bufbytes.extend(struct.pack(packCode[datatype][bits], start + v))
			else:
				start += len(obj.data.vertices)

	# Write buffer
	with open(Path(xxmi.destination_path) / f'{componentName}{suffix}', 'wb') as f:
		f.write(bufbytes)
	return f'{componentName}{suffix}'

def register():
	bpy.utils.register_class(XXMI_PT_SidePanelBufferExport)
	bpy.utils.register_class(ExportBufferOperator)
	print('XXMI Buffer Export Registered')

def unregister():
	bpy.utils.unregister_class(XXMI_PT_SidePanelBufferExport)
	bpy.utils.unregister_class(ExportBufferOperator)
	print('XXMI Buffer Export Unregistered')