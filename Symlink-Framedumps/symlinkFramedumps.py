from pathlib import Path
import math
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

script_dir = Path(__file__).parent

framedumps = [item for item in script_dir.iterdir() if item.is_dir() and item.name.startswith('FrameAnalysis') and (item / 'log.txt').exists() and (item / 'deduped').exists() and len([i for i in item.iterdir() if not i.is_file()]) == 1]


fdcount = len(framedumps)
if not fdcount:
	print('No unlinked framedumps found. Exiting...')
	quit()
print(f'Linking framedumps...\n|{generateProgressBar(0,60)}| {' ' * (len(str(fdcount))-1)}0/{fdcount}\n')
for fi,framedump in enumerate(framedumps):
	for nonlink in [i for i in framedump.iterdir() if i.is_file() and i.name != 'log.txt']:
		nonlink.unlink()
	print(f'\x1b[3F\x1b[KLinking {framedumps[fi].name}...\n\n')
	with open(framedump / 'log.txt') as f:
		loglines = [line for line in f]
	links = [(framedump / line.split(' -> ')[0].split(f'{framedump.name}')[1][1:], framedump / 'deduped' / line.split('deduped')[1][1:-1]) for line in loglines if 'deduped' in line and '->' in line and 'failed' not in line]
	for li, line in enumerate(loglines):
		if 'deduped' in line and '->' in line:
			splitline = line.split('\\')
			splitline[0] = splitline[0][:-2]
			loglines[li] = '/'.join(splitline)
	linkcount = len(links)
	print(f'\x1b[1F\x1b[K|{generateProgressBar(0,60)}| {' ' * (len(str(linkcount))-1)}0/{linkcount}')
	for li,link in enumerate(links):
		link[0].symlink_to(link[1])
		print(f'\x1b[1F\x1b[K|{generateProgressBar((li+1)/linkcount,60)}| {' ' * (len(str(linkcount))-len(str(li+1)))}{li+1}/{linkcount}')
	if fi+1 > fdcount:
		print(f'\x1b[3F\x1b[KLinking {framedumps[fi+1].name}...')
	else:
		print(f'\x1b[3F')
	print(f'|{generateProgressBar((fi+1)/fdcount,60)}| {' ' * (len(str(fdcount))-len(str(fi+1)))}{fi+1}/{fdcount}\n')
	(framedump / 'log.txt').rename(framedump / 'log.txt.bak')
	with open(framedump / 'log.txt', 'w') as f:
		for i in loglines:
			f.write(i)
print(f'Finished.')