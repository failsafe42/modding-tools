import re
import sys
import struct
from time import time
from functools import partial
from pathlib import PureWindowsPath,Path

hashupdate = {
	'eed13e28': {'hash': '86b9312f', 'stride': '12'},
	'9e0ad5bd': {'hash': 'e9681c99', 'stride': '16'}
}

def updatetexcoord(path: Path, backup_path: Path, stride):
	filebytes = bytearray()
	if stride == '20':
		oldformat = 'I4f'
		newformat = 'I4e'
	elif stride == '28':
		oldformat = 'I6f'
		newformat = 'I6e'
	with open(backup_path,'rb') as f:
		for chunk in iter(partial(f.read,int(stride)),b''):
			filebytes.extend(struct.pack(newformat,*struct.unpack(oldformat,chunk)))
	with open(path,'wb') as f:
		f.write(filebytes)

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

# Get directory to work from by first argument or use script directory if no argument is found
single_ini_name = ''
if len(sys.argv) == 1:
	base_path = Path(__file__).resolve().parent
else:
	if sys.argv[1].endswith('.ini'):
		single_ini_name = Path(sys.argv[1]).name
		base_path = Path(sys.argv[1]).resolve().parent
	else:
		base_path = Path(sys.argv[1]).resolve()

# Find and parse all ini files recursively in base directory
parsedinis = []
if single_ini_name:
	parsedinis.append(parseini(base_path / single_ini_name))
else:
	for ini in base_path.rglob('*.ini'):
		parsedinis.append(parseini(ini))

if not parsedinis:
	print('No inis found. Nothing to do.')
	quit()

# Check for outdated hashes in ini
updateinis = []
for ini in parsedinis:
	for section in ini['dict']:
		if 'hash' in ini['dict'][section] and ini['dict'][section]['hash'] in hashupdate:
			if ini not in updateinis:
				updateinis.append(ini)

if not updateinis:
	print('No outdated inis found. Nothing to do.')
	quit()

# Update outdated files
for ini in updateinis:
	ini['path'].rename(ini['path'].parent / (ini['path'].name + f'-{int(time())}.bak'))
	hair_texcoord_override = ''
	face_texcoord_override = ''
	for section in ini['dict']:
		if 'hash' in ini['dict'][section] and ini['dict'][section]['hash'] in hashupdate:
			ini['rawdata'] = ini['rawdata'].replace(ini['dict'][section]['rawdata'],
										   			re.sub(r'hash\s*=\s*'+ini['dict'][section]['hash'],
														   f"hash = {hashupdate[ini['dict'][section]['hash']]['hash']}",
														   ini['dict'][section]['rawdata']))
			if 'vb1' in ini['dict'][section]:
				resource = ini['dict'][section]['vb1']
			elif 'this' in ini['dict'][section]:
				resource = ini['dict'][section]['this']
			ini['rawdata'] = ini['rawdata'].replace(ini['dict'][resource]['rawdata'],
													re.sub(r'stride\s*=\s*'+ini['dict'][resource]['stride'], 
														   f"stride = {hashupdate[ini['dict'][section]['hash']]['stride']}",
														   ini['dict'][resource]['rawdata']))
			texcoord = Path(PureWindowsPath(ini['dict'][resource]['filename']))
			if not texcoord.exists():
				texcoord = next(base_path.rglob(str(texcoord), case_sensitive=False), None)
				if texcoord is None:
					print(f"Error: Can't find texcoord buf ({ini['dict'][resource]['filename']})")

			texcoord_backup = texcoord.parent / (texcoord.name + f'-{int(time())}.bak')
			texcoord.rename(texcoord_backup)
			updatetexcoord(texcoord, texcoord_backup, ini['dict'][resource]['stride'])
	with open(ini['path'],'w') as f:
		f.write(ini['rawdata'])
	print(f'Updated {ini['path']}')