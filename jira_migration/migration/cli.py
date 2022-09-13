#!/usr/bin/env python
# Coding = UTF-8

"""
	This module provides all command line interaction with the user.
"""

# Imports - Built-in
from datetime import datetime
import logging
import os
import re
from types import SimpleNamespace

# Imports - 3rd party
import colorama

# Imports - Local
from migration import core, io_module

# Logging
log = logging.getLogger(__name__)


# NOTE: If colorama is initialized multiple times if can cause recursion depth errors.
# To avoid that, it is initialized a single time here.
colorama.init(autoreset=True)


# Functions
def select_server(namespace: SimpleNamespace):
	"""
	Get user to select a Jira server.

	Args:
		namespace(Simplenamespace): Namespace containing configuration data.

	Returns:
		(SimpleNamespace):
			args.offline: Process offline only.
			args.url: Base URL for server.
	"""

	# Add items to namespace
	namespace.offline = False
	namespace.url = ''

	# Build list of server
	title = 'Jira Server Selection'
	columns = ['#', 'Name', 'URL']
	dataset = []
	server_list = [namespace.__getattribute__(key) for key in
		namespace.__dict__ if "ServerMenuOption" in key]
	for server in server_list:
		dataset.append([server.get('index'), server.get('name'), server.get('url')])
	print_table(title, columns, dataset)

	# Get server url
	namespace.url = ''
	selection = ''
	while selection not in range(len(dataset)):
		selection = int(input('Select a Jira server. (Enter #): '))
	if server_list[selection].get('name') == "Quit":
		quit()
	elif server_list[selection].get('name') == 'Other':
		namespace.url = input('Enter URL: ')
	elif server_list[selection].get('name') == 'Offline':
		namespace.offline = True
	else:
		namespace.url = server_list[selection].get('url')


def print_table(title: str, columns: list, dataset: list):
	"""
	Print a table of information.

	-----------
	   title
	-----------
	col col col
	--- --- ---
	val val val
	-----------

	Args:
		title(str): Table heading.
		columns (list): list of column headers.
		dataset (list): list of lists containing rows of data.
	"""

	# Find column widths
	table_width = len(title)  # Initial table width will be title width
	column_widths = []
	for col in columns:  # Establish array
		column_widths.append(len(col))
	for row in dataset:  # Populate array
		col_count = 0
		for col in row:
			if len(str(col)) > column_widths[col_count]:
				column_widths[col_count] = len(str(col))
			col_count += 1
	calculated_width = 0
	for width in column_widths:
		calculated_width += width
	calculated_width += len(columns) - 1  # Add one space gap between columns
	if calculated_width > table_width:
		table_width = calculated_width

	# Build table header
	table = ''
	table += '{}\n'.format('-' * table_width)
	table += '{:^{}}\n'.format(title, table_width)
	table += '{}\n'.format('-' * table_width)
	col_count = 0
	heading_separater = ''
	for column in columns:
		table += '{:^{}}'.format(column, column_widths[col_count])
		heading_separater += '{}'.format('-' * column_widths[col_count])
		if len(columns) > col_count + 1:
			table += ' '
			heading_separater += ' '
		else:
			table += '\n'
			heading_separater += '\n'
		col_count += 1
	table += heading_separater

	# Build table rows
	for row in dataset:
		col_count = 0
		for col in row:
			table += '{:{}}'.format(str(col), column_widths[col_count])
			if len(row) > col_count + 1:
				table += ' '
			else:
				table += '\n'
			col_count += 1
	print(table)


def ask_yes_no(question: str, flag: bool = False) -> bool:
	"""
	Ask a yes/no question and return the boolean equivalent.

	Args:
		question(str): Question to pose to user.
		flag(bool): If True don't ask the question. Used for unattended export.

	Returns:
		(bool) True if yes, otherwise False.
	"""

	# Flag
	if flag:
		return True

	answer = False
	ask = ''
	while ('y' not in ask) and ('n' not in ask):
		ask = input(question).lower()
	if 'y' in ask:
		answer = True
	return answer


def get_filename_cli(window_title: str, search_filter: list) -> str:
	"""
	Ask the user to enter their desired file.

	Args:
		window_title(str): Title for the file dialog window.
		filters(list): list of lists - names and extensions to filter for.
			Single filter: [['CSV files','*.csv']]
			Multiple selectable filters: [['CSV files','*.csv'],['Excel files','*.xls *.xlsx']]

	Returns:
		(str): Path and filename.
	"""

	prompt = f'{window_title}: Enter absolute path and filename: '
	filename = input(prompt)
	# Transform powershell drag and drop
	filename = re.sub(r'&\s\'(.+)\'', r'\1', filename)
	# Transform MINGW64 drag and drop
	filename = re.sub(r'^\'\/(\S)(\/.+)\'$', r'\1:\2', filename)
	# Transform bash drag and drop
	filename = re.sub(r'^\'(.+.\w+)\'', r'\1', filename.strip())

	return filename


def get_directory_cli(window_title: str, prompt: str) -> str:
	"""
	Ask the user to enter their desired directory.

	Args:
		window_title(str): Title for the file dialog window.

	Returns:
		(str): Absolute path to directory.
	"""

	prompt = f'{window_title}: {prompt}: '
	directory = input(prompt)
	# Transform powershell drag and drop
	directory = re.sub(r'&\s\'(.+)\'', r'\1', directory)
	# Transform MINGW64 drag and drop
	directory = re.sub(r'^\'\/(\S)(\/.+)\'$', r'\1:\2', directory)
	# Transform bash drag and drop
	directory = re.sub(r'^\'(.+)\'', r'\1', directory.strip())

	return directory


def output_message(severity: str, message: str):
	"""
	Write message to log and console. Messages color coded to indicate severity on console.

	Args:
		severity(str): log level [info, warn, error]
		message(str): string to output.
		line_feed(bool): Add line feed if True.
	"""

	# Output message
	console_message = f"\n{severity.upper()}: {message}"
	if severity == 'info':
		log.info(message.replace('\n', ''))
		print(colorama.Fore.WHITE + console_message + colorama.Fore.RESET)
	elif severity == 'warning':
		log.warning(message.replace('\n', ''))
		print(colorama.Fore.YELLOW + console_message + colorama.Fore.RESET)
	elif severity == 'error':
		if type(message) == UnicodeDecodeError:
			log.error(message.reason)
		else:
			log.error(message.replace('\n', ''))
		print(colorama.Fore.RED + console_message + colorama.Fore.RESET)


def finish_message(input_time: float, filename: str, project_key: str):
	"""
	Display finish message and elapsed run time

	Args:
		input_time(float): Time script started
		filename(str): 
		project_key(str): Jira project key
	"""

	# Build final logfile name
	target_path = os.path.dirname(filename)
	timestamp = datetime.now().strftime('%Y%m%d-%H%M')
	target_filename = os.path.join(target_path, project_key + '_' + timestamp + '.log')
	target_filename = os.path.normpath(target_filename)

	# Build message
	finish_message = (f'{os.path.basename(__file__)} finished, elapsed time (h:m:s): ' +
		f'{core.elapsed_time(input_time)}. \nLog file copied to {target_filename}')
	output_message('info', finish_message)

	# Copy log file
	io_module.copy_log(log.manager.root.handlers[0].baseFilename, target_filename)


def get_project_key() -> str:
	"""
	Unable to get project key from file, ask the user.
	"""

	return input('Please enter the project key for this project: ').upper()
