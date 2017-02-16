#!/usr/bin/python3
#
# Script to take the master document and ancillary files and create the
# finished manual/website.
#
# by James Hammons
# (C) 2017 Underground Software
#

# Remnants (could go into the master document as the first header)

#bootstrap_path: /bootstrap-2.2.2
#page_title: The Ardour Manual

import os
import re
import shutil
import argparse


#
# Create an all lowercase filename without special characters and with spaces
# replaced with dashes.
#
def MakeFilename(s):
	# Cleans up the file name, removing all non ASCII or .-_ chars
	fn = re.sub(r'[^.\-_a-zA-Z0-9 ]', '', s)
	fn = fn.lower()
	fn = fn.replace(' ', '-')
	return fn


#
# Parse headers into a dictionary
#
def ParseHeader(fileObj):
	header = {}

	while (True):
		hdrLine = fileObj.readline().rstrip('\r\n')

		# Break out of the loop if we hit the end of header marker
		if hdrLine.startswith('---'):
			break

		# Check to see that we have a well-formed header construct
		match = re.findall(': ', hdrLine)

		if match:
			# Parse out foo: bar pairs & put into header dictionary
			a = re.split(': ', hdrLine, 1)
			header[a[0]] = a[1]

	return header


#
# Turn a "part" name into an int
#
def PartToLevel(s):
	level = -1

	if s == 'part':
		level = 0
	elif s == 'chapter':
		level = 1
	elif s == 'subchapter':
		level = 2
	elif s == 'section':
		level = 3
	elif s == 'subsection':
		level = 4

	return level

#
# Converts a integer to a roman number
#
def num2roman(num):
	num_map = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'), (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
	roman = ''

	while num > 0:
		for i, r in num_map:
			while num >= i:
				roman += r
				num -= i

	return roman

#
# Capture the master document's structure (and content, if any) in a list
#
def GetFileStructure():
	fs = []
	fnames = [None]*6
	content = ''
	grab = False
	mf = open('master-doc.txt')

	for ln in mf:
		if ln.startswith('---'):
			# First, stuff any content that we may have read into the current
			# header's dictionary
			if grab:
				fs[-1]['content'] = content
				grab = False
				content = ''

			# Then, get the new header and do things to it
			hdr = ParseHeader(mf)
			level = PartToLevel(hdr['part'])
			hdr['level'] = level
			fnames[level] = MakeFilename(hdr['title'])

			# Ickyness--user specified URIs
			if 'uri' in hdr:
				hdr['filename'] = hdr['uri']
			else:
				fullName = ''

				for i in range(level + 1):
					fullName = fullName + fnames[i] + '/'

				hdr['filename'] = fullName.rstrip('/')

			fs.append(hdr)

			if ('include' not in hdr) and (level > 0):
				grab = True
		else:
			if grab:
				content = content + ln

	# Catch the last file, since it would be missed above
	if grab:
		fs[-1]['content'] = content

	mf.close()
	return fs


#
# Determine if a particular node has child nodes
#
def HaveChildren(fs, pos):
	# If we're at the end of the list, there can be no children
	if pos == len(fs) - 1:
		return False

	# If the next node is at a lower level than the current node, we have
	# children.
	if fs[pos]['level'] < fs[pos + 1]['level']:
		return True

	# Otherwise, no children at this node.
	return False


#
# Get the children at this level, and return them in a list
#
def GetChildren(fs, pos):
	children = []
	pos = pos + 1
	childLevel =  fs[pos]['level']

	while fs[pos]['level'] >= childLevel:
		if fs[pos]['level'] == childLevel:
			children.append(pos)

		pos = pos + 1

		# Sanity check
		if pos == len(fs):
			break

	return children


#
# Make an array of children attached to each node in the file structure
# (It's a quasi-tree structure, and can be traversed as such.)
#
def FindChildren(fs):
	childArray = []

	for i in range(len(fs)):
		if HaveChildren(fs, i):
			childArray.append(GetChildren(fs, i))
		else:
			childArray.append([])

	return childArray


#
# Make an array of the top level nodes in the file structure
#
def FindTopLevelNodes(fs):
	level0 = []

	for i in range(len(fs)):
		if fs[i]['level'] == 0:
			level0.append(i)

	return level0


#
# Find all header links and create a dictionary out of them
#
def FindInternalLinks(fs):
	linkDict = {}

	for hdr in fs:
		if 'link' in hdr:
			linkDict['@@' + hdr['link']] = '/' + hdr['filename'] + '/'

	return linkDict


#
# Internal links are of the form '@@link-name', which are references to the
# 'link:' field in the part header. We have to find all occurances and replace
# them with the appropriate link.
#
def FixInternalLinks(links, content, title):

	# Make key1|key2|key3|... out of our links keys
	pattern = re.compile('|'.join(links.keys()))

	# Use a lambda callback to substitute each occurance found
	result = pattern.sub(lambda x: links[x.group()], content)

	# Check for missing link targets, and report them to the user
	match = re.findall('"@@.*"', result)

	if len(match) > 0:
		print('\nMissing link target' + ('s' if len(match) > 1 else '') + ' in "' + title + '":')

		for s in match:
			print('  ' + s[3:-1])

		print()

	return result


#
# Recursively build a list of links based on the location of the page we're
# looking at currently
#
def BuildList(lst, fs, pagePos, cList):
	content = '\n\n<dl>\n'

	for i in range(len(lst)):
		curPos = lst[i]
		nextPos = lst[i + 1] if i + 1 < len(lst)  else len(fs)

		active = ' class=active' if curPos == pagePos else ''
		content = content + '<dt' + active + '><a href="/' + fs[curPos]['filename'] + '/">' + fs[curPos]['title'] + '</a></dt><dd' + active + '>'

		# If the current page is our page, and it has children, enumerate them
		if curPos == pagePos:
			if len(cList[curPos]) > 0:
				content = content + BuildList(cList[curPos], fs, -1, cList)

		# Otherwise, if our page lies between the current one and the next,
		# build a list of links from those nodes one level down.
		elif (pagePos > curPos) and (pagePos < nextPos):
			content = content + BuildList(cList[curPos], fs, pagePos, cList)

		content = content + '</dd>\n'

	content = content + '</dl>\n'

	return content

#
# Create link sidebar given a position in the list.
#
def CreateLinkSidebar(fs, pos, childList):

	# Build the list recursively from the top level nodes
	content = BuildList(FindTopLevelNodes(fs), fs, pos, childList)
	# Shove the TOC link in the top...
	content = content[:7] + '<dt><a href="/toc/">Table of Contents</a></dt><dd></dd>\n' + content[7:]

	return content


# Preliminaries

# We have command line arguments now, so deal with them
parser = argparse.ArgumentParser(description='A build script for the Ardour Manual')
parser.add_argument('-v', '--verbose', action='store_true', help='Display the high-level structure of the manual')
parser.add_argument('-q', '--quiet', action='store_true', help='Suppress all output (overrides -v)')
args = parser.parse_args()
verbose = args.verbose
quiet = args.quiet

if quiet:
	verbose = False

#verbose = False
level = 0
fileCount = 0
levelNums = [0]*6
lastFile = ''
page = ''
toc = ''
pageNumber = 0

siteDir = './website/'

if os.access(siteDir, os.F_OK):
	if not quiet:
		print('Removing stale HTML data...')

	shutil.rmtree(siteDir)

shutil.copytree('./source', siteDir)


# Read the template, and fix the stuff that's fixed for all pages
temp = open('page-template.txt')
template = temp.read()
temp.close()

template = template.replace('{{page.bootstrap_path}}', '/bootstrap-2.2.2')
template = template.replace('{{page.page_title}}', 'The Ardour Manual')


# Parse out the master docuemnt's structure into a dictionary list
fileStruct = GetFileStructure()

# Build a quasi-tree structure listing children at level + 1 for each node
nodeChildren = FindChildren(fileStruct)

# Create a dictionary for translation of internal links to real links
links = FindInternalLinks(fileStruct)

if not quiet:
	print('Found ' + str(len(links)) + ' internal link target', end='')
	print('.') if len(links) == 1 else print('s.')

if not quiet:
	master = open('master-doc.txt')
	firstLine = master.readline().rstrip('\r\n')
	master.close()

	if firstLine == '<!-- exploded -->':
		print('Parsing exploded file...')
	elif firstLine == '<!-- imploded -->':
		print('Parsing imploded file...')
	else:
		print('Parsing unknown type...')

# Here we go!

for header in fileStruct:
	fileCount = fileCount + 1
	content = ''
	more = ''

	lastLevel = level
	level = header['level']

	# Handle Part/Chapter/subchapter/section/subsection numbering
	if level == 0:
		levelNums[2] = 0
	elif level == 1:
		levelNums[2] = 0
	elif level == 2:
		levelNums[3] = 0
	elif level == 3:
		levelNums[4] = 0

	levelNums[level] = levelNums[level] + 1;

	# This is totally unnecessary, but nice; besides which, you can capture
	# the output to a file to look at later if you like :-)
	if verbose:
		for i in range(level):
			print('\t', end='')

		if (level == 0):
			print('\nPart ' + num2roman(levelNums[0]) + ': ', end='')
		elif (level == 1):
			print('\n\tChapter ' + str(levelNums[1]) + ': ', end='')

		print(header['title'])

	# Handle TOC scriblings...
	if level == 0:
		toc = toc + '<h2>Part ' + num2roman(levelNums[level]) + ': ' + header['title'] + '</h2>\n';
	elif level == 1:
		toc = toc + '  <p id=chapter>Ch. ' + str(levelNums[level]) + ':&nbsp;&nbsp;<a href="/' + header['filename'] + '/">' + header['title'] + '</a></p>\n'
	elif level == 2:
		toc = toc + '    <a id=subchapter href="/' + header['filename'] + '/">' + header['title'] + '</a><br>\n'
	elif level == 3:
		toc = toc + '      <a id=subchapter href="/' + header['filename'] + '/">' + header['title'] + '</a><br>\n'
	elif level == 4:
		toc = toc + '      <a id=subchapter href="/' + header['filename'] + '/">' + header['title'] + '</a><br>\n'

	# Make the 'this thing contains...' stuff
	if HaveChildren(fileStruct, pageNumber):
		pages = GetChildren(fileStruct, pageNumber)

		for pg in pages:
			more = more + '<li>' + '<a href="/' + fileStruct[pg]['filename'] + '/">' + fileStruct[pg]['title'] + '</a>' + '</li>\n'

		more = '<div id=subtopics>\n' + '<h2>This section contains the following topics:</h2>\n' + '<ul>\n' + more + '</ul>\n' + '</div>\n'

	# Make the 'Previous' & 'Next' content
	nLink = ''
	pLink = ''

	if pageNumber > 0:
		pLink = '<li><a title="' + fileStruct[pageNumber - 1]['title'] + '" href="/' + fileStruct[pageNumber - 1]['filename'] + '/" class="previous"> &lt; Previous </a></li>'

	if pageNumber < len(fileStruct) - 1:
		nLink = '<li><a title="' + fileStruct[pageNumber + 1]['title'] + '" href="/' + fileStruct[pageNumber + 1]['filename'] + '/" class="next"> Next &gt; </a></li>'

	prevnext = '<ul class=pager>' + pLink + nLink + '</ul>'

	# Create the link sidebar
	sidebar = CreateLinkSidebar(fileStruct, pageNumber, nodeChildren)

	# Parts DO NOT have any content, they are ONLY an organizing construct!
	# Chapters, subchapters, sections & subsections can all have content,
	# but the basic fundamental organizing unit WRT content is still the
	# chapter.
	if level > 0:
		if 'include' in header:
			srcFile = open('include/' + header['include'])
			content = srcFile.read()
			srcFile.close()

			# Get rid of any extant header in the include file
			# (once this is accepted, we can nuke this bit, as content files
			# will not have any headers or footers in them)
			content = re.sub('---.*\n(.*\n)*---.*\n', '', content)
			content = content.replace('{% children %}', '')

		else:
			if 'content' in header:
				content = header['content']
			else:
				content = '[something went wrong]'

	# Fix up any internal links
	content = FixInternalLinks(links, content, header['title'])

	# Set up the actual page from the template
	if 'style' not in header:
		page = re.sub("{% if page.style %}.*\n.*\n{% endif %}.*\n", "", template)
	else:
		page = template.replace('{{page.style}}', header['style'])
		page = page.replace('{% if page.style %}', '')
		page = page.replace('{% endif %}', '')

	page = page.replace('{{ page.title }}', header['title'])
	page = page.replace('{% tree %}', sidebar)
	page = page.replace('{% prevnext %}', prevnext)
	page = page.replace('{{ content }}', content + more)

	# Create the directory for the index.html file to go into (we use makedirs,
	# because we have to in order to accomodate the 'uri' keyword)
	os.makedirs(siteDir + header['filename'], 0o775, exist_ok=True)

	# Finally, write the file!
	destFile = open(siteDir + header['filename'] + '/index.html', 'w')
	destFile.write(page)
	destFile.close()

	# Save filename for next header...
	lastFile = header['filename']
	pageNumber = pageNumber + 1

# Finally, create the TOC
sidebar = CreateLinkSidebar(fileStruct, -1, nodeChildren)

page = re.sub("{% if page.style %}.*\n.*\n{% endif %}.*\n", "", template)
page = page.replace('{{ page.title }}', 'Ardour Table of Contents')
page = page.replace('{% tree %}', sidebar)
page = page.replace('{{ content }}', toc)
page = page.replace('{% prevnext %}', '')

os.mkdir(siteDir + 'toc', 0o775)
tocFile = open(siteDir + 'toc/index.html', 'w')
tocFile.write(page)
tocFile.close()

if not quiet:
	print('Processed ' + str(fileCount) + ' files.')