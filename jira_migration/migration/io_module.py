#!/usr/bin/env python
# Coding = UTF-8

"""
	This module contains file I/O functions.
"""


# Imports - Built-in
from collections import Counter
from configparser import ConfigParser
import csv
from datetime import datetime
from filecmp import cmp
import glob
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from tqdm import tqdm
from types import SimpleNamespace

# Imports - Local
from migration import core, cli, export, gui


# Logging
log = logging.getLogger(__name__)


# Functions
def read_config_ini(namespace: SimpleNamespace(), filename: str):
	"""
	Import all config.ini data into namespace as dictionaries.
	i.e. namespace.[ini section] = {key:value, ...}

	Args:
		namespace(SimpleNamespace): Namespace to add configuration variables to.
		filename(str): Filename and path to configuration file.
	"""

	# Read config file
	config = ConfigParser(interpolation=None)
	if os.path.exists(filename):
		config.read(filename)
	else:
		log.error('Config file, /"{}/", not found! Unable to continue.'.format(filename))
		quit()

	for section in config.sections():
		section_name = section.replace(' ','') # Remove all spaces
		section_dict = {}
		for key in config[section]:
			try: # Convert to int if able
				section_dict[key] = (config[section][key] if not config[section][key].isdigit()
					else int(config[section][key]))
			except:
				section_dict[key] = config[section][key]
		setattr(namespace, section_name, section_dict)

	# Checklist exclusions
	namespace.ChecklistExclusions = namespace.ChecklistExclusions.get('list').split()

	# Flags to boolean values
	for flag in namespace.Flags:
		namespace.Flags[flag] = eval(namespace.Flags[flag])

	# SSL config
	namespace.SSL['enabled'] = eval(namespace.SSL['enabled'])

	# Schemas
	for schema in namespace.Schemas:
		namespace.Schemas[schema] = namespace.Schemas[schema].split(',')

	# Simple columns
	for column in namespace.SimpleColumns:
		namespace.SimpleColumns[column] = namespace.SimpleColumns[column].split(',')

	# Compound columns
	for column in namespace.CompoundColumns:
		namespace.CompoundColumns[column] = namespace.CompoundColumns[column].split(',')

	# Column exclusions
	for column in namespace.ColumnExclusions:
		namespace.ColumnExclusions[column] = namespace.ColumnExclusions[column].split(',')


def read_csv(csv_file: str) -> list:
	"""
	Read csv from file into list.

	Args:
		csv_file(str): Path to Jira exported CSV file.

	Returns:
		(list): Each entry is a row from the CSV file.
	"""

	data = []
	with open(csv_file, encoding='utf8') as csv_raw:
		# Set max field size (used for very large csv fields)
		max_int = sys.maxsize
		while True:
			try:
				csv.field_size_limit(max_int)
				break
			except OverflowError:
				max_int = int(max_int/10)
		csv.field_size_limit(max_int)

		# Read data from CSV file
		csv_reader = csv.reader(csv_raw, delimiter=',')
		try: # May throw UnicodeDecodeError if non UTF-8 chars detected.
			for row in csv_reader:
				data.append(row)
		except UnicodeDecodeError as exception_message:
			log.error(exception_message)
			quit('Unable to read file. Try converting file to UTF-8 with Notepad++ or other app.')
	return data


def write_csv(dataset: list, output_filename: str, split: bool = False):
	"""
	Write data to CSV file. Rename existing file if present.
	If name is "Epics" or "NoEpics", export just epics or exclude epics.

	Args:
		dataset(list): Data to write to CSV.
		output_filename(str): Filename (filename only or absolute path), of Jira export file.
		split(bool): Split csv into Epics and Other.
	"""

	# Rename original csv file if exists
	if os.path.exists(output_filename):
		# compare to current dataset
		match = compare_csv_data(dataset, output_filename)
		if not match:
			bak_count = len(
				glob.glob1(
					os.path.split(output_filename)[0],
					'{}*.bak'.format(os.path.split(output_filename)[1])
					)
				)
			backup_file = '{}.bak'.format(output_filename)
			if bak_count > 0:
				backup_file = '{}.({}).bak'.format(output_filename, bak_count + 1)
			os.rename(output_filename, backup_file)
		else:
			cli.output_message('info', 
				f'No changes detected, retain existing file: '
					f'{output_filename}.')
			return

	# Write new csv
	if split:
		# Get issue type column
		issue_type_column = None
		headers = dataset[0]
		issue_type_columns = core.get_columns(headers, 'Issue Type')
		if len(issue_type_columns) == 1:
			issue_type_column = issue_type_columns[0]
		else:
			message = 'More than one Issue Type column found. Check CSV file.'
			log.error(message)
			quit(message)

		# Abort script if single issue type column wasn't found
		if not issue_type_column:
			message = 'Unable to determine Issue Type column. Exiting.'
			log.error(message)
			quit(message)

		# Write two CSV files
		epic_filename = build_filename(output_filename, '_Epics')
		noepic_filename = build_filename(output_filename, '_Non-Epics')
		try:
			with open(epic_filename, 'w', newline='', encoding="UTF-8") as epic_output_file, \
				open(noepic_filename, 'w', newline='', encoding="UTF-8") as noepic_output_file:
				epic_writer = csv.writer(
					epic_output_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL
				)
				noepic_writer = csv.writer(
					noepic_output_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL
				)
				for row in tqdm(dataset, desc='Writing Epic and Non-Epic CSV data'):
					if dataset.index(row) == 0:
						epic_writer.writerow(row)
						noepic_writer.writerow(row)
					elif row[issue_type_column].lower() == 'epic':
						epic_writer.writerow(row)
					elif row[issue_type_column].lower() != 'epic':
						noepic_writer.writerow(row)
		except PermissionError:
			message = f'{os.path.normpath(output_filename)}, file may be in use.'
			log.error(message)
			quit(message)
		# Finish message
		message = (f'Finished writing: {os.path.normpath(epic_filename)} and ' +
			f'{os.path.normpath(noepic_filename)}')
		log.info(message)
		print(message)

	if not split:
		try:
			with open(output_filename, 'w', newline='', encoding="UTF-8") as output_file:
				csv_writer = csv.writer(
					output_file,
					delimiter=',',
					quotechar='"',
					quoting=csv.QUOTE_MINIMAL
				)
				for row in tqdm(dataset, desc='Writing CSV data'):
					csv_writer.writerow(row)
		except PermissionError:
			message = f'{os.path.normpath(output_filename)}, file may be in use.'
			log.error(message)
			quit(message)
		# Finish message
		message = f'Finished writing: {os.path.normpath(output_filename)}'
		log.info(message)
		print(message)


def build_filename(base_filename: str, append: str, extension: str = '') -> str:
	"""
	Build a new filename appending a string to the existing filename. Optionally changing the
	file extension.

	Args:
		base_filename(str): Filename to start from. This should be the csv file.
		append(str): String to append to the filename (i.e. base_filename<append>.ext)
		extension(str): This is the file extension.
			If not specified the base extension will be re-used.

	Returns:
		(str): New path and filename.
	"""

	# Build filename
	base_path = os.path.dirname(base_filename)
	filename_only = os.path.basename(base_filename)
	filename_split = os.path.splitext(filename_only)
	extension = filename_split[1] if not extension else extension
	filename_mod = '{}{}{}'.format(filename_split[0], append, extension)
	return os.path.normpath(os.path.join(base_path, filename_mod))


def find_files(search_string: str, search_path: str, extension: str) -> list:
	"""
	Search csv directory for files containing the search string.

	Args:
		search_string(str): String to search for.
		search_path(str): Path will be pulled from this string. Provide the CSV filename.
		extension(str): Extension of files to search for.

	Returns:
		(list): all files containing search_string.
	"""

	results = []
	base_path = os.path.dirname(search_path)
	for file in os.listdir(base_path):
		if search_string.lower() in file.lower() and re.search(r'\.{}$'.format(extension), file):
			results.append(os.path.join(base_path, file))
	return results


def get_filename(window_title: str, search_filter: list) -> str:
	"""
	Display a file dialog and ask the user the select their desired file.

	Args:
		title(str): Title for the file dialog window.
		filters(list): list of lists - names and extensions to filter for.
			Single filter: [['CSV files','*.csv']]
			Multiple selectable filters: [['CSV files','*.csv'],['Excel files','*.xls *.xlsx']]

	Returns:
		(str): Path and filename.
	"""

	filename = ''
	if 'tkinter' in sys.modules:
		filename = gui.get_filename_gui(window_title, search_filter)
	else:
		filename = cli.get_filename_cli(window_title, search_filter)

	if not os.path.exists(filename):
		message = f'\"{filename}\", file not found. Exiting.'
		log.error(message)
		quit(message)

	return filename


def get_directory(window_title: str, prompt: str) -> str:
    """
    Get directory from user.

    Args:
        window_title(str): Window title.

    Returns:
        (str): Absolute path to selected folder.
    """

    directory = ''
    while not os.path.exists(directory):
        if 'tkinter' in sys.modules:
            directory = gui.get_directory_gui(window_title)
        else:
            directory = cli.get_directory_cli(window_title, prompt)
    return directory


def set_to_csv(dataset: list, header: list, output_filename: str):
	"""
	Format set data for CSV export.

	Args:
		data_set(list): input data to write to file.
		csv_file(str): Name of file exported from Jira.
		header(list): Column header for csv file.
		name(str): Name to append to file.
	"""

	my_list = []
	my_list.append(header)
	for item in dataset:
		my_list.append(item)
	write_csv(my_list, output_filename)


def list_to_csv(dataset: list, output_filename: str):
	"""
	Format list for csv output. Output filename will be [filename]_[name].csv.

	Args:
		dataset(list): List of lists to write to csv.
		output_filename(str): Target path and filename.
	"""

	my_list = []

	# Get headers - each row may not contain the same so we have to gather all possible values.
	headers = []
	for row in dataset:
		for key in row.keys():
			if not key in headers:
				headers.append(key)

	# Data rows
	for row in dataset:
		# Use raw data from python-jira resultList.
		raw_data = []
		for field in headers:
			value = row.get(field)
			if not value is None:
				raw_data.append(value)
			else:
				raw_data.append('')
		my_list.append(raw_data)
	set_to_csv(my_list, headers, output_filename)


def copy_log(source_filename: str, target_filename: str):
	"""
	Copy a file from one location to another.
	"""

	shutil.copy(source_filename, target_filename)


def merge_csv(directory: str, key: str, files_dateformat: str) -> str:
	"""
	Merge multiple csv files into a single file. Paginated CSV export via rest 
	endpoint does not output columns that are not in the current export range. 
	So you need to align columns when merging.

	Args:
		directory(str): location of csv files.
		key(str): Project key.

	Returns:
		(str): Path and filename of merged CSV file.
	"""

	cli.output_message('INFO', 'Merging datasets from {}.'.format(directory))
	file_list = get_file_list(directory, key)

	header_field_counts = {}
	for file in file_list:
		read_data = read_csv(file)
		headers = read_data[0]
		header_counter = Counter(headers)
		for value in header_counter:
			if not value in header_field_counts:
				header_field_counts[value] = header_counter[value]

			if header_field_counts[value] < header_counter[value]:
				header_field_counts[value] = header_counter[value]

	dataset_header = []
	for field in header_field_counts:
		for i in range(header_field_counts[field]):
			dataset_header.append(field)

	merged_dataset = []
	merged_dataset.append(dataset_header)
	for file in tqdm(file_list, desc='Merging CSVs'):
		csv_data = read_csv(file)
		csv_headers = csv_data[0]
		csv_data = [row for row in csv_data if csv_data.index(row) != 0]
		if len(csv_data) > 0:
			column_map = export.map_subset(dataset_header, csv_headers)
			for row in csv_data:
				new_row = list(['' for field in range(len(dataset_header))])
				for i in range(len(row)):
					new_row[column_map[i]] = row[i]
				merged_dataset.append(new_row)

	# Write dataset
	date = datetime.now().strftime(files_dateformat)
	output_filename = '{}_{}.csv'.format(key, date)
	path = os.path.join(directory, output_filename)
	write_csv(merged_dataset, path)

	# return csv_data as list
	return output_filename


def get_file_list(directory: str, key: str) -> list:
	"""
	Get all filesin directory matching project_key.

	Args:
		directory(str): Directory to search for files in.
		key(str): Jira project key.

	Returns:
		(list): List of files found.
	"""

	# Get all matching files from directory
	file_list = []
	files = os.listdir(directory)
	search_string = '^{}_[0-9]*.csv'.format(key)
	for file in files:
		if re.search(search_string, file):
			file_list.append(os.path.join(directory, file))
	return file_list


def sprint_dict_to_csv(input_list: list, output_file: str):
	"""
	Format sprints for CSV export

	Args:
		input_list(list): list of sprint_info records.
		csv_file(str): Path to Jira exported CSV file.
		name(str): Name to append to file.
	"""

	dataset = [['id', 'name', 'state', 'goal', 'startDate', 'endDate', 'completeDate']]
	for list_item in input_list:
		dataset.append(
			[
				list_item.get('id'),
				list_item.get('name'),
				list_item.get('state'),
				list_item.get('goal'),
				list_item.get('startDate'),
				list_item.get('endDate'),
				list_item.get('completeDate')
			]
		)
	write_csv(dataset, output_file)


def write_file(data: str, filename: str):
	"""
	Write a file
	"""
	# Rename original csv file if exists
	if os.path.exists(filename):
		file_path = os.path.split(filename)[0]
		file_name = os.path.split(filename)[1]
		bak_count = len(glob.glob1(file_path, f'{file_name}*.bak'))
		backup_file = f'{filename}.bak'
		if bak_count != 0:
			backup_file = '{}({}).bak'.format(filename, bak_count + 1)
			try:
				os.rename(filename, backup_file)
			except IOError as exception_message:
				cli.output_message(
					'ERROR',
					'Could not write to file. {}'.format(exception_message)
				)
	with open(filename, 'w', newline='', encoding="UTF-8") as output_file:
		output_file.write(data)
	cli.output_message('INFO', 'Finished writing: {}\n'.format(filename))


def compare_files(file_a: str, file_b: str) -> bool:
	"""
	Compare two file to see if they are identical.

	Args:
		file_a(str): Filename of first file.
		file_b(str): Filename of second file.
	
	Returns:
		(bool): True if the files are the same.
	"""

	return cmp(file_a, file_b)


def compare_csv_data(dataset: list, filename: str) -> bool:
	"""
	Compare a csv dataset to the data in a file. Used to determine if a new 
	write is necessary.

	Args:
		dataset(list): Dataset pending write.
		filename(str): existing csv file.

	Returns:
		(bool): True if content of both dataset and file are the same.
	"""

	# Get data from existing file
	dataset_a = read_csv(filename)
	# Simulate new dataset as file
	sim_dataset = []
	with tempfile.TemporaryFile(mode='w+', newline='', encoding="UTF-8") as temp_file:
		# Write
		csv_writer = csv.writer(temp_file, delimiter=',', quotechar='"', 
			quoting=csv.QUOTE_MINIMAL)
		for row in dataset:
			csv_writer.writerow(row)
		# Read
		temp_file.seek(0)
		csv_reader = csv.reader(temp_file, delimiter=',')
		for row in csv_reader:
			sim_dataset.append(row)
	return sorted(dataset_a) == sorted(sim_dataset)


def write_csv_field_values(
	csv_filename: str,
	csv_dataset: list,
	dataset_title: str,
	column_header: str,
	search_list: list
	):
	"""
	Write all unique field values for a given field name.

	Args:
		csv_filename(str): filename of input CSV.
		csv_dataset(list): List of Lists(rows) containing CSV data.
		data_title(list): List of field names to export.
	"""

	# Get all columns of interest
	columns = []
	headers = csv_dataset[0]
	for search_string in search_list:
		columns += core.get_columns(headers, search_string)

	# Build dataset and insert header
	dataset = core.build_list(csv_dataset, columns)
	dataset.insert(0, [column_header])  # Insert header at top of list

	# Write values if necessary
	if len(dataset) > 0:
		output_filename = build_filename(csv_filename, '_{}'.format(dataset_title))
		write_csv(dataset, output_filename)


def local_file_attachments(csv_data: list, key: str, original_key: str, 
	csv_filename: str, namespace: SimpleNamespace) -> bool:
	"""
	Find attachments in CSV and replace the host info with "file://". The attachment link
	will have spaces replaced with the HTML escape sequence %20.

	Args:
		csv_data: CSV file read into list format.

	Returns:
		(bool): True
	"""

	# Rename attachments directory to match new key
	base_path = os.path.dirname(csv_filename)
	if original_key:
		existing_path = os.path.join(base_path, original_key)
		new_path = os.path.join(base_path, key)
		if new_path != existing_path:
			while os.path.exists(existing_path):
				try:
					os.rename(existing_path, new_path)
				except PermissionError:
					input('Unable to rename directory! Please close Windows '
						'Explorer and press Enter to retry.')

	# Local file prefix
	prefix = ''
	question = cli.ask_yes_no('Will attachments be uploaded to [jira_upload]/'
			f'{key}/secure/attachment/[id]/[filename])? (Y/N): ')
	if question:
		prefix = f'file://{key}/'
		print('Before uploading attachments with WinSCP, name attachments '
			f'folder = [base path]/{key}/secure/attachment/...')
	else:
		new_filename = input('Enter attachment root directory name '
			'(Case Sensitive): ')
		prefix = f'file://{new_filename}/'

	# Process file
	attachment_count = 0
	attachment_columns = []
	row_count = 0
	desc = 'Updating attachments for local upload'
	for row in tqdm(csv_data, desc=desc):
		if row_count == 0:  # Look for attachment and key columns
			# NOTE: Column name is plural if there is more than one.
			column_count = 0
			for column in row:
				if re.search('^attachment', column.lower()):  # match front
					attachment_columns.append(column_count)
				column_count += 1
		else:  # Process rows
			for column in attachment_columns:
				if row[column] != '' and not prefix in row[column]:
					# Replace host with file
					search_string = '/secure/'  # Division of host and path
					replace_end = row[column].find(search_string) + 1
					replace_begin = row[column].rfind(';') + 1
					hostname = (row[column])[replace_begin:replace_end]
					# Filename transforms
					field_value = csv_data[csv_data.index(row)][column]
					field_value = field_value.replace(hostname, prefix)
					field_value = field_value.replace('+', '%20')
					# Save result
					csv_data[csv_data.index(row)][column] = field_value
					attachment_count += 1
					namespace.Flags['modified'] = True

		row_count += 1
	log.info('Updated %d attachment paths.', attachment_count)


def create_config(csv_file: str, key: str, date_format: str):
	"""
	Create the starting point for a jira import configuration. This will specify the date format
	and project key to import to.

	Args:
		csv_file(str): Name of csv file to base config filename on.
		key(str): Project key
	"""

	# Basic configuration file contents
	field_mappings = {
		"Affects Version/s": {
			"jira.field": "versions"
		},
	  		"Assignee": {
			"jira.field": "assignee"
		},
		"Attachment": {
			"jira.field": "attachment"
		},
		"Comment": {
			"jira.field": "comment"
		},
		"Component/s": {
			"jira.field": "components"
		},
		"Created": {
			"jira.field": "created"
		},
		"Description": {
			"jira.field": "description"
		},
		"Issue id": {
			"jira.field": "issue-id"
		},
		"Issue key": {
			"jira.field": "issuekey"
		},
		"Issue Type": {
			"jira.field": "issuetype"
		},
		"Labels": {
			"jira.field": "labels"
		},
		"Priority": {
			"jira.field": "priority"
		},
		"Reporter": {
			"jira.field": "reporter"
		},
		"Resolution": {
			"jira.field": "resolution"
		},
		"Resolved": {
			"jira.field": "resolutiondate"
		},
		"Status": {
			"jira.field": "status"
		},
		"Summary": {
			"jira.field": "summary"
		},
		"Votes": {
			"jira.field": "votes"
		},
		"Watchers": {
			"jira.field": "watcher"
		}
		}

	basic_config = {
		"config.version" : "2.0",
		"config.project.from.csv" : "false",
		"config.encoding" : "UTF-8",
		"config.email.suffix" : "@",
		"config.field.mappings": field_mappings,
		"config.value.mappings": {},
		"config.delimiter": ",",
		"config.project" : {
			"project.type" : "null",
			"project.key" : key,
			"project.description" : "null",
			"project.url" : "null",
			"project.name" : "",
			"project.lead" : "null"
		},
		"config.date.format": date_format
		}

	basic_config = json.dumps(basic_config)

	# Set up filename [path, filename, extension]
	filename_list = []
	if '/' in csv_file:
		path = os.path.split(csv_file)
		filename_split = core.split_filename(path[1])
		filename_list = [path[0], filename_split[0], filename_split[1]]
	else:
		# filename only
		current_working_directory = os.getcwd()
		filename_split = core.split_filename(csv_file)
		filename_list = [current_working_directory, filename_split[0], 
			filename_split[1]]
	filename = (os.path.join(filename_list[0], filename_list[1]) + 
		'_CSV_Configuration.txt')
	filename = os.path.normpath(filename)

	# Write file
	if not os.path.exists(filename):
		try:
			with open(filename, 'w', newline='', encoding="utf8") as output_file:
				output_file.write(basic_config)
		except IOError as exception_message:
			cli.output_message('error', f'Unable to write {filename}. '
				f'{exception_message}')
		# Check again
		if os.path.exists(filename):
			cli.output_message('info', 'Created basic configuration '
				f'file: {filename}')
