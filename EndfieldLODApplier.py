import re
import sys
import json
import time
import math
import numpy
import shutil
from pathlib import Path

def usage():
	print(f'Usage: {Path(sys.executable).name} {sys.argv[0]} <character dump folder> <folder of mod to fix>')
	quit()

def generateProgressBar(progress, length):
	solid = math.floor(length * progress)
	mid = (progress - (solid / length))*length
	subChar = ''
	
	if 0 < mid < 0.125:
		subChar = ' '
	elif 0.125 <= mid < 0.25:
		subChar = '▏'
	elif 0.25 <= mid < 0.375:
		subChar = '▎'
	elif 0.375 <= mid < 0.5:
		subChar = '▍'
	elif 0.5 <= mid < 0.625:
		subChar = '▌'
	elif 0.625 <= mid < 0.75:
		subChar = '▋'
	elif 0.75 <= mid < 0.875:
		subChar = '▊'
	elif 0.875 <= mid < 1:
		subChar = '▉'

	bar = f'{'█' * solid}{subChar}{' ' * (length - solid - len(subChar))}'
	return bar	

def parseini(inipath: Path):
	inilist = []
	with open(inipath) as f:
		rawdata = f.read()
	inilist = [line for line in rawdata.split('\n') if not line.strip().startswith(';')]
	inilist = '\n'.join(inilist).split('[')
	inidict = {i.split(']')[0]: {'rawdata': i.split(']')[1]} for i in inilist if ']' in i}
	for i in inidict:
		splitdata = [line for line in inidict[i]['rawdata'].split('\n') if line.strip() and not '$' in line and '=' in line]
		for line in splitdata:
			key = line.split('=')[0].strip()
			value = line.split('=',1)[1].strip()
			if key in inidict[i]:
				if type(inidict[i][key]) == list:
					inidict[i][key].append(value)
				else:
					inidict[i][key] = [inidict[i][key], value]
			else:		
				inidict[i][key] = value
	return {'path': inipath, 'rawdata': rawdata, 'dict': inidict}

def applyLODS(modini: dict[str], lods):
	# Get current hashes
	hashes = {modini['dict'][i]['hash']: i for i in modini['dict'] if 'hash' in modini['dict'][i]}

	# Generate ini sections
	writecount = 0
	bufferstoconvert = {}
	convertedbuffers = {}
	overridesections = []
	commandlistsections = []
	resourcesections = []
	for i in modini['dict']:
		if i.startswith('TextureOverride') and modini['dict'][i]['hash'] in lods:
			commandlistfound = False
			vb2found = True
			if 'vb2' in modini['dict'][i]:
				vb2name = modini['dict'][i]['vb2'].replace('ref ','')
			else:
				if 'run' not in modini['dict'][i]:
					vb2found = False
				else:
					commandlistname = modini['dict'][i]['run']
					commandlist = modini['dict'][commandlistname]
					if 'vb2' in commandlist:
						vb2name = commandlist['vb2'].replace('ref ','')
						commandlistfound = True
					else:
						vb2found = False
			if vb2found:		
				vb2 = modini['dict'][vb2name]
				filepath = modini['path'].parent / vb2['filename']

				vb2stride = int(vb2['stride'])
				if vb2stride not in [4,12]:
					print(f'ERROR: Unknown VB2 stride for {filepath} ({vb2stride})')
					quit()
			for lodi,lod in enumerate(lods[modini['dict'][i]['hash']]):
				if lod['vb0_hash'] in hashes:
					overridesections.append(f'\n[{hashes[lod['vb0_hash']]}]\n{modini['dict'][hashes[lod['vb0_hash']]]['rawdata'].strip()}\n')
					if vb2found:
						resourcesections.append(f'\n[{vb2name}]\n{vb2['rawdata'].strip()}\n')
					if commandlistfound:
						commandlistsections.append(f'\n[{commandlistname}]\n{commandlist['rawdata'].strip()}\n')
					continue
				if vb2found:
					lodfilepath = f'{filepath.parent / filepath.stem}_LOD{lodi}.buf'

					bufferstoconvert[lodfilepath] = (filepath, lod, vb2stride)
				
				rawdata = modini['dict'][i]['rawdata'].split('\n')
				for li,line in enumerate(rawdata):
					if 'hash' in line:
						rawdata[li] = line.replace(modini['dict'][i]['hash'], lod['vb0_hash'])
					if vb2found:
						if vb2name in line:
							rawdata[li] = line.replace(vb2name, f'{vb2name}_LOD{lodi}')
				overridesections.append(f'\n[{i}_LOD{lodi}]\n{'\n'.join(rawdata).strip()}\n')
				if vb2found:
					resourcesections.append(f'\n[{vb2name}_LOD{lodi}]\n{vb2['rawdata'].replace(filepath.stem, f'{filepath.stem}_LOD{lodi}').strip()}\n')
				if commandlistfound:
					overridesections[-1] = overridesections[-1].replace(commandlistname, f'{commandlistname}_LOD{lodi}')
					commandlistsections.append(f'\n[{commandlistname}_LOD{lodi}]\n{commandlist['rawdata'].replace(vb2name, f'{vb2name}_LOD{lodi}').strip()}\n')

	# Generate new vb2s
	convertcount = len(bufferstoconvert)
	if convertcount:
		print(f'Converting...\n|{generateProgressBar(0/convertcount, 60)}| {' ' * (len(str(convertcount))-1)}0/{convertcount}')		
	for buf in bufferstoconvert:
		lodfilepath = buf
		filepath = bufferstoconvert[buf][0]
		lod = bufferstoconvert[buf][1]
		vb2stride = bufferstoconvert[buf][2]
		vb2file = numpy.fromfile(filepath, dtype=numpy.uint8).reshape(-1,vb2stride)
		
		# Remap groups
		groups = vb2file[:, -4:]
		for group in numpy.nditer(groups, op_flags=['readwrite']):
			group[...] = lod['vg_map'][str(group)]

		if vb2stride == 12: # Consolidate duplicate groups
			weights = vb2file[:,:-4].view(dtype=numpy.uint16)
			for vi,vweights in enumerate(weights):
				binned = numpy.bincount(groups[vi], vweights)
				index = numpy.flatnonzero(binned)
				weights[vi,:] = numpy.concatenate([binned[index],[0]*(4-len(index))])
				groups[vi,:] = numpy.concatenate([index,[0]*(4-len(index))])
			convertedbuffers[lodfilepath] = numpy.concatenate((weights.view(dtype=numpy.uint8), groups),axis=1)
		elif vb2stride == 4: # No weights, only groups
			convertedbuffers[lodfilepath] = groups
		writecount += 1
		print(f'\x1b[2F\x1b[KConverted {filepath}...\n|{generateProgressBar(writecount/convertcount, 60)}| {' ' * (len(str(convertcount))-len(str(writecount)))}{writecount}/{convertcount}')

	# Write to files
	lodapplierheader = '\n\n\n; LOD APPLIER START ----------------------\n'
	overrideheader = '; Overrides ------------------------------'
	resourceheader = '; Resources ------------------------------'
	commandlistheader = '; Command Lists --------------------------'
	lodapplierfooter = '; LOD APPLIER END ------------------------'
	if not writecount:
		print('No override sections with LODs to apply. Skipping writing to files.')
	else:
		for buffer in convertedbuffers:
			convertedbuffers[buffer].tofile(buffer)
			# print(f'Wrote {buffer}')
		writeini = [
			lodapplierheader,
			overrideheader,
			''.join(overridesections),
			commandlistheader if commandlistsections else '',
			''.join(commandlistsections),
			resourceheader,
			''.join(resourcesections),
			lodapplierfooter
		]
		shutil.copy(modini['path'], modini['path'].parent / (modini['path'].name + f'_{time.time_ns()}.bak'))
		with open(modini['path'], 'w') as f:
			f.write(f"{re.sub(r'\n{0,3}; LOD APPLIER START(?s:.)+?LOD APPLIER END -{24}', '', modini['rawdata'])}{'\n'.join(part for part in writeini if part)}")
		print(f'Wrote sections to {modini['path']}')
	return writecount

if __name__ == '__main__':		
	if len(sys.argv) != 3:
		usage()

	dumppath = Path(sys.argv[1])
	if not (dumppath / 'Metadata.json').exists():
		print('Metadata.json missing from dump folder')
		usage()

	modpath = Path(sys.argv[2])
	inifiles = sorted(modpath.rglob('*.ini'))
	if not inifiles:
		print('No ini file found in mod folder')
		usage()

	with open(dumppath / 'Metadata.json') as f:
		metadata = json.load(f)

	parsedinis = [parseini(ini) for ini in inifiles]

	# Find lods in metadata
	lods = {c['vb0_hash']: c['lods'] for c in metadata['components'] if c['lods']}|{c['ib_hash']: c['lods'] for c in metadata['components'] if c['lods']}

	# Find inis that override hashes found in metadata
	modinis = [ini for ini in parsedinis if any(ini['dict'][section]['hash'] in lods for section in ini['dict'] if 'hash' in ini['dict'][section])]

	print(f'Found {len(modinis)} potential ini file{'' if len(modinis) == 1 else 's'} to modify {[ini['path'].name for ini in modinis]}')

	modifiedinis = len(modinis) - [applyLODS(modini, lods) for modini in modinis].count(0)
	print(f'Done. Applied LODs to {modifiedinis} ini{'' if modifiedinis == 1 else 's'}.')
