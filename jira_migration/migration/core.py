#!/usr/bin/env python
# Coding = UTF-8

"""
	This module contains the core functionality of the jira migration script.
"""

# Imports - Built-in
from datetime import datetime
from enum import Enum
import json
import logging
import os
import re
import sys
from time import time
from tqdm import tqdm
from types import SimpleNamespace
from typing import Tuple

# Imports - 3rd Party
from dateutil.parser import parse

# Imports - Local
from migration import cli

# Logging
log = logging.getLogger(__name__)


# Functions
def get_project_key(dataset: list, namespace: SimpleNamespace) -> str:
	"""
	Get project key from CSV data. Use the "Issue key" column. If not found, search for the
	"Project key" column.

	Args:
		dataset(list): Data read from CSV file.

	Returns:
		(str): project key
	"""

	key = ''
	headers = dataset[0]
	columns = []
	if not columns:
		column_search = 'Issue key'
		columns = get_columns(headers, column_search)
		for column in columns:
			key = dataset[1][column]
			key = (key.split('-'))[0]
			break

	if not columns:
		column_search = 'Project key'
		columns = get_columns(headers, column_search)
		for column in columns:
			key = dataset[1][column]
			break

	if not columns:
		if namespace.Flags.get('gui'):
			# key = gui.get_project_key()
			key = cli.get_project_key()
		else:
			key = cli.get_project_key()

	log.info('Project key = %s', key)
	return key


def get_columns(headers: list, field_Name: str) -> list:
	"""
	Search input data headers for exact matching string.

	Args:
		headers(list): headers of CSV dataset for searching.
		search_string(str): Column name to search for.

	Returns:
		(lits): List of column indices.
	"""

	indices = []
	column_index = 0
	for header in headers:
		if header == field_Name:
			indices.append(column_index)
		column_index += 1
	return indices


def validate_value(field_type: str, value: str) -> bool:
	"""
	Validate a few data types to assist with processing.

	Args:
		type(str): Field type (column name).
		value(str): value from field splitting.

	Returns:
		(bool): True if value can be interpreted as the desired type.
	"""

	DATETIMES = ['datetime']
	STRINGS = ['username', 'comment', 'filename', 'location']
	INTEGERS = ['seconds']

	field_type = field_type.lower()
	if field_type in DATETIMES:
		try:
			# Fails when re-run with my custom format. So for validation
			# replace userscore with space.
			test_value = value.replace('_', ' ')
			test = parse(test_value, fuzzy=False)
			if isinstance(test, datetime):
				return True
		except Exception as exception_message:
			log.info(
				'Unexpected value for type(%s) = %s. Error: %s',
				field_type,
				value,
				exception_message
			)
			return False
	elif field_type in STRINGS:
		if field_type == 'username':  # Username should not contain spaces.
			regex_pattern = r'\s'
			if not re.match(regex_pattern, value):
				return True
			else:
				return False
		elif field_type == 'filename':
			regex_pattern = r'^.*[.]{1}\w+$'
			if bool(re.match(regex_pattern, value)):  # filename
				return True
			else:
				return False
		elif field_type == 'location':
			regex_pattern = r'(^http|file).*[.]{1}\w+$'
			if bool(re.match(regex_pattern, value)):  # filename
				return True
			else:
				return False
		else:
			return True
	elif field_type in INTEGERS:
		try:
			test = int(value)
			if isinstance(test, int):
				return True
		except Exception as exception_message:
			print(
				'Unexpected value for type({}) = {}. Error: {}'
				.format(field_type, value, exception_message)
			)
			return False


def get_field_location(issue_key: str, dataset: list, field_value: str) -> dict:
	"""
	Locate the field_value in the dataset, constrained by issue_key.

	Args:
		issue_key(str): Jira issue key to identify row to search.
		dataset(list): CSV dataset.
		field_value(str): String to search for in row.
	
	Returns:
		(dict): {row:col}, Row and Column of data.
	"""

	coordinates = {'row':0, 'col':0}
	headers = dataset[0]
	issue_key_columns = get_columns(headers, 'Issue key')
	for column in issue_key_columns:  # column will be a integer
		for row in dataset:
			if row[column] == issue_key:
				coordinates['row'] = dataset.index(row)
				coordinates['col'] = row.index(field_value)
	return coordinates


def select_server(namespace: SimpleNamespace):
	"""
	show GUI or CLI server selection.

	Args:
		namespace(SimpleNamespace): Configuration data.
	"""

	if namespace.Flags.get('gui'):
		# gui.select_server(namespace)
		cli.select_server(namespace)
	else:
		cli.select_server(namespace)


def elapsed_time(input_time: time) -> str:
	"""
	Calculate elapsed time since input_time.

	Args:
		input_time(time.time): Time.

	Returns:
		(str): Elapsed time as string.
	"""

	time_passed = time() - input_time
	hours = divmod(time_passed, 3600)
	minutes = divmod(hours[1], 60)
	seconds = minutes[1]
	return f'{int(hours[0]):0>2}:{int(minutes[0]):0>2}:{int(seconds):0>2}'


def find_attachments(dataset: list) -> dict:
	"""
	locate attachments and return dictionary of results.

	Args:
		dataset: Data read from CSV file.

	Returns:
		(dict): Dictionary of attachments.
		{url:{original filename, Jira issue key}}
	"""

	attachment_list = []

	issue_key_columns = get_columns(dataset[0], 'Issue key')
	attachment_columns = get_columns(dataset[0], 'Attachment')
	attachment_count = 0

	cli.output_message('INFO', 'Searching for attachments.')
	for row in tqdm(dataset, desc='Scanning rows for attachments'):
		if dataset.index(row) != 0:
			for column in attachment_columns:
				if row[column] != '':
					for issue_key_col in issue_key_columns:
						attachment_list.append(f'{row[issue_key_col]};'
							f'{row[column]}')
						attachment_count += 1
	cli.output_message('info', f'Found {attachment_count} attachments.')

	attachment_dict = {}
	if attachment_count == 0: # Abort here if there are no attachments
		return attachment_dict

	# Format attachments if necessary
	jira_attachement_schema = {
		'key': 0,
		'date': 1,
		'user': 2,
		'filename': 3,
		'url': 4
		}

	for attachment in tqdm(attachment_list, desc='formatting attachment list'):
		data = attachment.split(';')
		if len(data) == 5:
			# Format data {url{filename,key}}
			attachment_dict[data[jira_attachement_schema.get('url')]] = {
				'filename': data[jira_attachement_schema.get('filename')],
				'key': data[jira_attachement_schema.get('key')]
				}
		else:
			if (validate_value('datetime', data[1]) and 
				validate_value('filename', data[2])):
				# username is missing, insert "Unknown"
				data.insert(2, 'Unknown')
			elif (validate_value('datetime', data[1]) and 
				data[2] == os.path.basename(data[3])):
				# username is missing, filename was ambiguous, insert "Unknown"
				data.insert(2, 'Unknown')	
			else:
				log.error('Unable to parse attachment entry: %s', attachment)
				continue
			# Data was able to be corrected, add dictionary entry
			attachment_dict[data[jira_attachement_schema.get('url')]] = {
				'filename': data[jira_attachement_schema.get('filename')],
				'key': data[jira_attachement_schema.get('key')]
				}
			# Update dataset
			issue_key = attachment.split(';')[0]
			search_string = ';'.join(attachment.split(';')[1:])
			new_value = ';'.join(data[1:])
			location = get_field_location(issue_key, dataset, search_string)
			dataset[location.get('row')][location.get('col')] = new_value
			log.info('Malformed field corrected for %s(%d:%d) = %s', issue_key, 
				location.get('row'), location.get('col'), new_value)
	return attachment_dict


def fix_oversize_fields(namespace: SimpleNamespace, csv_data: list, attachment_path: str,
	project_key: str) -> list:
	"""
	Take the content of an oversized field and dump it into an attachment.
	Replace the original content with a link to the new file. Single value
	fields will be replaced with a link to the attachment. Compound fields,
	comments and work log entries, will have the link inserted into the
	comment field.
	"""

	# Determine maximum number of attachment per issue
	attachment_columns = get_columns(csv_data[0], 'Attachment')
	max_attachments = len(attachment_columns)

	# Identify oversize field values
	oversize_fields = []
	for i in tqdm(range(len(csv_data)), desc='Identifying oversized fields'):
		for j in range(len(csv_data[i])):
			if csv_data[i][j] and len(csv_data[i][j]) >= 2**15:
				oversize_fields.append([i, j])

	for field in tqdm(oversize_fields, desc='Converting oversized field '
		'values to attachments'):
		row = field[0]
		col = field[1]
		issue_id = csv_data[row][(get_columns(csv_data[0], 'Issue key'))[0]]
		creator = csv_data[row][(get_columns(csv_data[0], 'Creator'))[0]]
		created = csv_data[row][(get_columns(csv_data[0], 'Created'))[0]]
		# Calculate remaining attachment fields
		remaining = 0
		for index in attachment_columns:
			if csv_data[row][index] == '':
				remaining += 1

		next_attachment_index = None
		if remaining > 0:
			next_attachment_index = attachment_columns[max_attachments - 
				remaining]
		else:
			# Create new column
			attachment_columns.append(extend_attachment_columns(
				attachment_columns, csv_data))
			next_attachment_index = attachment_columns[-1]
			max_attachments = len(attachment_columns)

		# Get field name
		field_name = csv_data[0][col]
		field_data = ''
		attachment_name = ''
		if field_name in namespace.CompoundColumns.get('columns'):
			# Get field schema (Almost impossible for these to be attachments)
			schema = namespace.Schemas.get(field_name.lower())
			split_field = str(csv_data[row][col]).split(';', len(schema))
			field_values_by_schema = {schema[i]:split_field[i] for i in range(len(schema))}
			split_comment = split_field[schema.index('comment')]
			split_username = split_field[schema.index('username')]
			attachment_name = '{}_{}_{}_{}.txt'\
				.format(issue_id.replace('-', ''), split_username, 
					field_name, col)
			field_data = split_comment
		else:
			attachment_name = '{}_{}_{}_{}.txt'\
				.format(issue_id.replace('-', ''), creator, field_name, col)
			field_data = csv_data[row][col]

		# Create attachment
		max_attachment_folder = find_max_attachment_folder(attachment_path)
		attachment_file_path = os.path.join(attachment_path, 'secure', 
			'attachment', str(max_attachment_folder))
		full_attachment_filename = os.path.join(attachment_file_path, 
			attachment_name)
		if os.path.exists(attachment_file_path):
			if (len(os.listdir(attachment_file_path)) > 0 and 
				not os.path.exists(full_attachment_filename)):
				attachment_file_path = os.path.join(attachment_path, 'secure', 
					'attachment', str(max_attachment_folder + 1))
				full_attachment_filename = os.path.join(attachment_file_path, 
					attachment_name)
				os.makedirs(attachment_file_path)
				# Write attachment
				with open(full_attachment_filename, "w") as attachment:
					attachment.write(field_data)
		else:
			os.makedirs(attachment_file_path)
			# Write attachment
			with open(full_attachment_filename, "w") as attachment:
				attachment.write(field_data)

		# Replace original content with link to new attachment
		replace_begin = 0
		replace_end = full_attachment_filename.find('secure')
		hostname = (full_attachment_filename)[replace_begin:replace_end]
		link = full_attachment_filename.replace(hostname, 
			f'file://{project_key}/')
		link = link.replace('\\', '/')

		# Build attachment entry
		field_format = namespace.DateFormats.get('fields')
		datetime = datetime_to_dateobject(created).strftime(field_format)
		csv_data[row][next_attachment_index] = f'{datetime};{creator};{attachment_name};{link}'

		# Remove Original bad content
		attachment_link = f'[^{attachment_name}]'
		if field_name not in namespace.CompoundColumns.get('columns'): 
			replacement_content = attachment_link
		else:
			# Configure replacement content to match schema
			if field_name == 'Attachment': # Should never see one of these.
				replacement_content = [datetime,creator,attachment_link,link]
			elif field_name == 'Comment' or field_name == 'Log Work':
				replacement_content = split_field
				replacement_content[schema.index('comment')] = attachment_link
			else:
				log.error('Unknown compound field replacement attempted: '
					'{%s}@{%d}:{%d}',issue_id, row, col)
		csv_data[row][col] = ';'.join(replacement_content)

		# CSV Data modified
		log.info('%s(%d:%d): Oversized field moved to %s. Field updated with '
			'link: %s', issue_id, row, col, attachment_file_path, 
			replacement_content)
		namespace.Flags['modified'] = True


def extend_attachment_columns(attachment_columns: list, csv_data: list) -> list:
	"""
	Add new column of data to end of csv dataset. Columns have to be added to the end to keep
	data alinged.
	"""

	# Extend all rows
	for i in range(len(csv_data)):
		csv_data[i].append('')

	# Add header
	csv_data[0][-1] = 'Attachment'

	return len(csv_data[0]) - 1


def find_max_attachment_folder(attachment_path: str) -> int:
	"""
	"""

	# If there is not attachment folder return 0
	if attachment_path is None:
		return 0

	base_path = attachment_path
	base_path = os.path.join(base_path, 'secure', 'attachment')
	while not os.path.exists(base_path):
		base_path = os.makedirs(base_path)
		return 0

	dirs = os.walk(base_path)
	folder_list = [int(os.path.basename(dir[0])) for dir in dirs if
		os.path.basename(dir[0]).isdigit()]
	max_folder = max(folder_list)
	return max_folder


def datetime_to_dateobject(datetime_string: str) -> datetime:
	"""
	Convert various Jira datetime representation into 24hr time. Formats must comply with
	Java SimpleDateFormat:
	https://confluence.atlassian.com/adminjiraserver073/importing-data-from-csv-861253680.html

	Witnessed time formats:
		A) 2021-06-09T15:25:31.217-0400
		A1) 2017-12-04T07:13:55.326-07:00
		A2) 2017-08-07 10:29:49.243
		# B) 20/Jan/20 9:51 AM (Unpadded hour - forced padding makes this one obsolete)
		B) 01/Jan/06 07:04 AM (Padded hour)
		C) 12/17/2019  2:40:00 PM (Unpadded hour)
		D) Dec/13/2017 07:03 AM
		E) 06/08/2020 18:34
		E2) 6/8/2020 (Unpadded version of E)
		F) 2021-06-04
		G) 24/06/2005_11:16 # This is my format: should be unique so the script won't get confused.
		H) 12/14/21 01:33 PM # GIDE format
		I) Dec 01, 2019 12:00 PM
		J) June 14, 2022 2:13:12 PM EDT

	Args:
		datetime_string: string representing a Jira datetime.

	Returns:
		Standardised Python datetime object.
	"""

	# Left pad any single digits with 0.
	datetime_string = re.sub(r'(\b\d{1}\b)', r'0\1', datetime_string)

	# Determine which datetime format you have
	format_a = r'\d{4}-(0[0-9]|1[0-2])-(0[0-9]|[1-2][0-9]|3[0-1])T(0[0-9]|1[0-9]|2[0-3]):'\
		r'(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9]).\d{3}[+-]\d{4}'
	format_a1 = r'\d{4}-(0[0-9]|1[0-2])-(0[0-9]|[1-2][0-9]|3[0-1])T(0[0-9]|1[0-9]|2[0-3]):'\
		r'(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9]).\d{3}[+-](0[0-9]|1[0-9]|2[0-3]):'\
		r'(0[0-9]|[1-5][0-9])'
	format_a2 = r'\d{4}-(0[0-9]|1[0-2])-(0[0-9]|[1-2][0-9]|3[0-1])\s(0[0-9]|1[0-9]|2[0-3]):'\
		r'(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9]).\d+'
	format_b = r'(0[1-9]|[1-2][1-9]|3[0-1]|)\/\w{3}\/\d{2}'\
		r'\s+(0[0-9]|1[0-2]):([0-5][0-9])\s+([A,P]M)'
	format_c = r'(([0-9])|([0-9]|1[0-2]))\/([0-5][0-9])\/\d{4}\s+([0-9]|1[0-2]):([0-5][0-9]):'\
		r'([0-5][0-9])\s+([A,P]M)'
	format_d = r'\w{3}\/([0-5][0-9])\/\d{4}\s+(0[0-9]|1[0-2]):(0[0-9]|[1-5][0-9])\s+([A,P]M)'
	format_e = r'(0[0-9]|1[0-2])\/(0[1-9]|[1-2][0-9]|3[0-1])\/\d{4}\s+(0[0-9]|1[0-9]|2[0-3]):'\
		r'([0-5][0-9])'
	format_f = r'\d{4}-(0[0-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])'
	# Format G is the result of running this script (meaning it's already been processed)
	format_g = r'(0[1-9]|[1-2][0-9]|3[0-1])\/(0[0-9]|1[0-2])\/\d{4}_(0[0-9]|1[0-9]|2[0-3]):'\
		r'([0-5][0-9])'
	format_h = r'(([0-9])|([0-9]|1[0-2]))\/([0-5][0-9])\/\d{2}'\
		r'\s+(0[0-9]|1[0-2]):([0-5][0-9])\s+([A,P]M)'
	format_i = r'\w{3}\s([0-5][0-9]),\s\d{4}\s(0[0-9]|1[0-2]):(0[0-9]|[1-5][0-9])\s+([A,P]M)'
	format_j = r'\w+\s([0-3][0-9]),\s\d{4}\s(\d|[0-9]|1[0-2]):(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9])\s+([A,P]M)\s\w{3}'

	format_string = ''
	if re.search(format_a, datetime_string):
		format_string = r'%Y-%m-%dT%H:%M:%S.%f%z'
	elif re.search(format_a1, datetime_string):
		# Remove colon from timezone
		search_pattern = r'([+-])(\d([0-9]|1[0-9]|2[0-3])):(\d([0-9]|[1-5][0-9]))'
		replacement_pattern = r'\1\2\4'
		datetime_string = re.sub(search_pattern, replacement_pattern, datetime_string)
		format_string = r'%Y-%m-%dT%H:%M:%S.%f%z'
	elif re.search(format_a2, datetime_string):
		format_string = r'%Y-%m-%d %H:%M:%S.%f'
	elif re.search(format_b, datetime_string):
		# hour_start_index = datetime_string.find(' ') + 1  # +1 to retain the space
		# hour_stop_index = datetime_string.find(':')
		# hour = datetime_string[hour_start_index:hour_stop_index]
		# hour = int(hour.strip())
		format_string = r'%d/%b/%y %I:%M %p'
	elif re.search(format_c, datetime_string):
		hour_start_index = datetime_string.find(' ') + 1  # +1 to retain the space
		hour_stop_index = datetime_string.find(':')
		hour = datetime_string[hour_start_index:hour_stop_index]
		hour = int(hour.strip())
		if hour < 10:  # Pad hour to two digits
			head = datetime_string[:hour_start_index]
			tail = datetime_string[hour_stop_index:]
			datetime_string = '{}0{}{}'.format(head, str(hour), tail)
		format_string = r'%m/%d/%Y %I:%M:%S %p'
	elif re.search(format_d, datetime_string):
		format_string = r'%b/%d/%Y %I:%M %p'
	elif re.search(format_e, datetime_string):
		format_string = r'%m/%d/%Y %H:%M'
	elif re.search(format_f, datetime_string):
		format_string = r'%Y-%m-%d'
	elif re.search(format_g, datetime_string):
		format_string = r'%d/%m/%Y_%H:%M'
	elif re.search(format_h, datetime_string):
		format_string = r'%m/%d/%y %I:%M %p'
	elif re.search(format_i, datetime_string):
		format_string = r'%b %d, %y %I:%M %p'
	elif re.search(format_j, datetime_string):
		format_string = r'%M %d, %y %h:%m:%s %a %z'
	else:
		cli.output_message(
				'ERROR',
				'\"{}\" using an unrecognized date format. Please update patterns.'
						.format(datetime_string)
			)
		quit()

	datetime_object = None
	if not format_string == '':
		datetime_object = datetime.datetime.strptime(datetime_string, format_string)
	else:
		cli.output_message('ERROR', f'Unable to parse datetime value: \"{datetime_string}\"')

	if datetime_object is None:
		try:
			# Excel serial date format (i.e. 44287.3166666667 = 04/01/2021 07:36)
			date_float = float(datetime_string)
			base = datetime.datetime(1899, 12, 30)
			delta = datetime.timedelta(days=date_float)
			datetime_object = base + delta
		except ValueError:
			cli.output_message('ERROR', f'Unhandled date format: \"{datetime_string}\"'.format())
	return datetime_object


def build_list(input_dataset: list, column_list: list) -> list:
	"""
	Build list with values from listed columns.

	Args:
		input_dataset(list):
		column_list(list):

	Returns:
		(list): list of lists(rows): [[row],[row],...]
	"""
	# Split headers from data rows.
	input_dataset_headers = input_dataset[0]
	input_dataset_rows = [row for row in input_dataset if row != 
		input_dataset_headers]

	# Get all values in columns
	value_list = []
	for row in input_dataset_rows:
		for col in column_list:
			cell = row[col]
			if cell != '':
				value_list.append(cell)
	# Keep only unique values
	value_set = set(value_list)
	unique_values = [[value] for value in value_set]
	return unique_values


def remove_empty_columns(input_data: list) -> Tuple[list, bool]:
	"""
	Remove columns without data

	Args:
		namespace(SimpleNamespace): Configuration data.
		input_data: CSV data represented as list of rows.

	Returns:
		(list): New input_data without empty columns; or Original dataset.
		(bool): True if columns were removed.
	"""

	csv_headers = input_data[0]
	column_counts = {i: 0 for i in range(len(csv_headers))}

	new_csv_data = []
	modified = False

	empty_cols = []
	desc = 'Identifying empty columns'
	for column in tqdm(column_counts.keys(), desc=desc):
		count = 0
		for row in input_data:
			content = row[column]
			if content != '':
				count += 1
		column_counts[column] = count - 1 # -1 to remove headers from count
		if count == 0:
			empty_cols.append(f'({column}){csv_headers[column]}')

	# count empty columns
	empty_column_list = []
	empty_column_count = 0
	for column in column_counts:
		if column_counts.get(column) == 0:
			empty_column_list.append(column)
			empty_column_count += 1

	# Remove empty columns
	if empty_column_count > 0:
		desc = f'Rebuilding dataset without empty columns'
		for row in tqdm(input_data, desc=desc):
			new_row = []
			for column in column_counts:
				if not column in empty_column_list:
					new_row.append(row[column])
			new_csv_data.append(new_row)
		modified = True

	if modified:
		log.info('%d Empty Columns Removed: %s', empty_column_count, 
			str(empty_cols))
		return new_csv_data, True

	return input_data, False


def replace_project_key(namespace: SimpleNamespace, csv_data: list, 
	old_key: str, new_key: str) -> list:
	"""
	Replace project key with new value. Exclude attachment columns.

	Args:
		namespace(SimpleNamespace): Configuration data.
		csv_data: CSV data represented as list of rows.
		old_key(str): Key to replace.
		new_key(str): New project key.

	Returns:
		(int): Number of replacements made.
	"""

	row_count = 0
	replacement_count = 0
	csv_headers = csv_data[0]
	csv_rows = [row for row in csv_data if csv_data.index(row) != 0]
	for row in tqdm(csv_rows, 'Updating project keys'):
		column_count = 0
		for col in row:
			if col and not 'attachment' in csv_headers[column_count].lower():
				# \b matches whole word only (Word Boundry)
				# re.subn keeps track of replacement count
				# result = [replaced string, replacement count]
				result = re.subn(
					r'\b{}\b(-\d*)'.format(old_key),
					r'{}\1'.format(new_key),
					col
				)
				csv_rows[row_count][column_count] = result[0] # replaced string
				replacement_count += result[1] # replacement count
			column_count += 1
		row_count += 1

	namespace.Flags['modified'] = True
	cli.output_message('info', f'Key update complete. Replaced '
		f'{replacement_count} instances of "{old_key}" with "{new_key}".\n')

	new_dataset = [csv_data[0]] + csv_rows
	return new_dataset


def find_leaves(node: dict, field_list: list) -> list:
	"""
	Find all leaf values in terminal nodes without braches. These are the fields on all the screen
	tabs.
	"""

	leaf = True
	for key in node.keys():
		if isinstance(node.get(key), dict):
			leaf = False
			leaves = find_leaves(node.get(key), field_list)
	if leaf:
		for key in node.keys():
			field_list.append(node.get(key))

	return field_list


def update_leaves(node: dict, update_dict: dict):
	"""
	In place update of all leaf values.
	"""

	leaf = True

	for key in node.keys():
		if isinstance(node.get(key), dict):
			leaf = False
			update_leaves(node.get(key), update_dict)
	if leaf:
		for key in node.keys():
			if (node.get(key) in update_dict.keys()) and (node.get(key) != \
				update_dict.get(node.get(key))):
				node[key] = update_dict.get(node.get(key))


def update_datetimes(csv_data: list, datetime_format: str, 
	simple_column_list: list, compound_column_list: list, 
	column_exclusions: list, namespace: SimpleNamespace) -> bool:
	"""
	Helper function to update a datetime.

	Args:
		csv_data: CSV data represented as list of rows.

	Uses:
		_get_columns
		datetime_to_dateobject
	"""

	cli.output_message('info', 
		f'Normalizing time format to \"{datetime_format}\".')

	# Get headers
	headers = csv_data[0]

	# Get issue key row
	issue_key_column = get_columns(headers, 'Issue key')
	issue_key_column = issue_key_column[0]

	# Find simple datetime fields
	log.info('Searching for simple datetime columns.')
	simple_columns = []
	for heading in simple_column_list:
		column_indices = get_columns(headers, heading)
		for index in column_indices:
			simple_columns.append(index)

	# Find compound datetime fields
	log.info('Searching for compound datetime columns.')
	compound_columns = []
	for heading in compound_column_list:
		column_indices = get_columns(headers, heading)
		for index in column_indices:
			compound_columns.append(index)

	# Fix any inconsistent values
	modified = False
	for row in tqdm(csv_data, desc='Fixing datetime values'):
		if csv_data.index(row) != 0:
			issue_key = row[issue_key_column]
			for column in simple_columns:
				if row[column] != '':
					new_datetime = datetime_to_dateobject(row[column])
					csv_data[csv_data.index(row)][column] = \
						new_datetime.strftime(datetime_format)
					modified = True
			for column in compound_columns:
				if row[column] != '':
					column_header = csv_data[0][column]
					column_schema = namespace.Schemas.get(column_header.lower())
					data = split_compound(row[column], column_header, 
						column_schema, csv_data, issue_key, 
						compound_column_list, column_exclusions)
					datetime_string = None
					if len(data) > 0:
						datetime_string = data.get('datetime')
					else:
						log.info('Unable to process compound column(%s): %s',
							column_header, row[column])
						continue
					new_datetime = datetime_to_dateobject(datetime_string)
					new_datetime = new_datetime.strftime(datetime_format)
					csv_data[csv_data.index(row)][column] = (
						csv_data[csv_data.index(row)][column]).replace(
						datetime_string, new_datetime)
					modified = True
	cli.output_message('info', 'Finished updating datetime values.')
	if modified:
		namespace.Flags['modified'] = True
	return csv_data


def split_compound(field_value: str, column_type: str, column_schema: list,
	dataset: list, issue_key: str, compound_column_list: list, 
	column_exclusions: list) -> dict:
	"""
	Split compound field value into dictionary of individual values. 
	Individual values are separated by semicolons, but sometimes a field 
	contains semicolons which cause improper splitting of the field. If field 
	splits into more than the expected number of values, user assistance will 
	be requested.

	Args:
		field_value (str): Raw data from cvs cell.
		column_type (str): Name of column to identify expected value by field 
			schema.

	Returns:
		(dict): dictionary of values contained in the field.

	Uses:
		split_compound_field(field_value: str, schema: list) -> dict:
	"""

	values = {}
	if column_type in column_exclusions:
		return {}  # Do not process excluded columns.
	split_field = field_value.split(';')
	while len(split_field) != len(column_schema):
		split_field = _auto_data_split(field_value, column_type, 
			column_schema, dataset, issue_key)
	else:
		for field in column_schema:
			field_value = split_field[column_schema.index(field)]
			if validate_value(field, field_value):
				values[field] = field_value
	return values


def _auto_data_split(input_data: str, field_type: str, field_schema: list,
	input_list: list, issue_key: str) -> list:
	"""
	Automatically split compound fields. Compound fields are semicolon 
	delimited, but if a user uses semicolons in their comments the field 
	will not split correctly and the import will fail. This function attempts
	to identify extraneous semicolons and replace them with their hex
	equivalent so import can be performed.

	Args:
		input_data(str): Value of compound field.
		field_type(str): Type of filed. Used for validation and schema 
							identification.
		input_list(list): List of CSV data. Corrected field value will be 
							written back.

	Returns:
		(list): List with values corrected.
	"""

	sys.setrecursionlimit(10**6)
	dataset = []
	delimiter = ';'
	hex_delimiter = '%3b'
	location = get_field_location(issue_key, input_list, input_data)

	# log if field is less than target schema length
	if len(input_data.split(delimiter)) < len(field_schema):
		try:
			log.warning('Invalid input in {%s}, (%s should have %d '
				'values = %s).', issue_key, field_type, len(field_schema),
				';'.join(field_schema))
		except UnicodeEncodeError as exception_message:
			log.error('Unicode Encoding Error: %s', exception_message)
		new_values = None
		# Attempt to determine missing part
		split_values = input_data.split(';', maxsplit=len(field_schema))
		# attachment missing username
		if field_type == 'attachment' and len(split_values) == 3:
			reverse_index_filename = (field_schema[::-1].index('filename') * -1) - 1
			reverse_index_location = (field_schema[::-1].index('location') * -1) - 1
			# Filename transforms to match url encoding
			test_filename = split_values[reverse_index_filename]
			test_filename = test_filename.replace(' ', '+')
			test_filename = test_filename.replace('@', '%40')
			test_filename = test_filename.replace('=', '%3D')
			if test_filename in split_values[reverse_index_location]:
				split_values.insert(field_schema.index('username'), 'Unknown')
				new_values = split_values
		elif field_type == 'comment' and len(split_values) == 2:
			if validate_value('datetime', 
				split_values[field_schema.index('datetime')]):
				split_values.insert(field_schema.index('username'), 'Unknown')
				new_values = split_values
		else: # User input required
			input_data = input('Fix the above string (copy and paste here): ')
			parse_input = input_data.split(';', maxsplit=len(field_schema))
			if len(parse_input) == len(field_schema):
				new_values = parse_input
		# update existing data
		if new_values:
			input_data = ';'.join(new_values)
			input_list[location.get('row')][location.get('col')] = input_data
			log.warning(
				'Input modified at %d:%d = %s',
				location.get('row') + 1,
				location.get('col'),
				input_data
				)
	elif len(input_data.split(delimiter)) > len(field_schema):
		try:
			log.warning('Invalid input in {%s}, (%s should have %d '
				'values = %s).', issue_key, field_type, len(field_schema),
				';'.join(field_schema))
		except UnicodeEncodeError as exception_message:
			log.error('Unicode Encoding Error: %s', exception_message)
		new_values = None
		# Attempt to determine missing part
		split_values = input_data.split(';', maxsplit=len(field_schema))
		# Field split larger than schema
		if field_type == 'log work' and len(split_values) > len(field_schema):
			# Test field in reverse (seconds > username > datetime > comment)
			new_values = []
			remaining_input = input_data
			subfield_index = len(field_schema) - 1
			while len(new_values) != len(field_schema):
				if len(new_values) == (len(field_schema) - 1):
					# use all remaining input
					value = remaining_input.replace(';','%3b')
				else:
					value = remaining_input[len(remaining_input) - 
						(remaining_input[::-1].index(';')):]
				if validate_value(field_schema[subfield_index], value):
					if field_schema[subfield_index] == 'username' and value == '':
						value = 'Unknown'
					new_values.insert(0, value)
					remaining_input = remaining_input[:len(remaining_input) - 
						(remaining_input[::-1].index(';') + 1)]
					subfield_index -= 1
				else:
					cli.output_message('error', 'Unable to process '
						f'/"{field_type}/" at {location}')

		# update existing data
		if new_values:
			input_data = ';'.join(new_values)
			input_list[location.get('row')][location.get('col')] = input_data
			log.warning('Input modified at %d:%d = %s', 
				location.get('row') + 1, location.get('col'), input_data)
	# Process a valid field value
	working_string = input_data
	schema_index = 0
	while len(working_string) > 0:
		this_field = working_string.split(delimiter, maxsplit=1)
		if len(this_field) > 1:
			if working_string.count(delimiter) > 0:
				# there is more to split
				next_field = this_field[1].split(delimiter, maxsplit=1)
				if field_schema[schema_index] != field_schema[-1]:
					test_next = validate_value(field_schema[schema_index + 1], next_field[0])
					if test_next:
						test_this = validate_value(field_schema[schema_index], this_field[0])
						if test_this:
							dataset.append(this_field[0])
							schema_index += 1
							working_string = this_field[1]
						else:
							cli.output_message('error', 'Invalid data at '
								f'[row,col] = {location}: {input_data}')
					else: # Next piece is not the right type = bad split
						working_string = working_string.replace(delimiter, hex_delimiter, 1)
				else: # This is the last schema field
					# Last field but there is more to split, replace remaining delimiters
					working_string = working_string.replace(delimiter, hex_delimiter, 1)
			else: # No next field
				working_string = working_string.replace(delimiter, hex_delimiter, 1)
		else: # Only one piece left
			#Validate and add to dataset
			test = validate_value(field_schema[schema_index], this_field[0])
			if test:
				dataset.append(this_field[0])
				working_string = ''

	if -1 not in location.values():
		new_string = ';'.join(dataset)
		input_list[location.get('row')][location.get('col')] = new_string
	return dataset


def list_to_dict(my_list: list) -> dict:
	"""
	Convert list to dictionary:

	Args:
		my_list: input list.

	Returns:
		Dictionary representation of input list.
	"""

	my_dict = {}
	for row in my_list:
		column_index = 0
		if my_list.index(row) != 0:
			for column in row:
				if column_index == 0:
					my_dict[row[0]] = {}
				else:
					my_dict[row[0]].update({my_list[0][column_index]: column})
				column_index += 1
	return my_dict


def replace_usernames(namespace: SimpleNamespace, csv_data: list, 
	user_dict: dict):
	"""
	Replace usernames with target instance usernames.

	Args:
		csv_data: CSV data represented as list of rows.
		user_dict: dict {username:'',NT Username:''}

	Uses:
		Imports:
			re
			progress.bar
		Helpers:
			_output_info
	"""

	headers = csv_data[0]

	# Replace key in csv data
	row_count = 0
	replacement_count = 0
	for username in tqdm(user_dict, desc='Updating usernames'):
		if not username:
			continue
		replacement_name = ''
		if not user_dict[username].get('NT Username').strip():
			replacement_name = user_dict.get('remap_user').get('NT Username')
		else:
			replacement_name = user_dict[username].get('NT Username')
		for row in csv_data:
			if csv_data.index(row) != 0:
				column_count = 0
				for field_value in row:
					if field_value and field_value.find(username) != -1:
						# re.subn keeps track of replacement count
						# result = [replaced string, count]
						result = []
						if (headers[column_count] in 
							namespace.SimpleColumns.get('username')):
							result = re.subn(r'{}'.format(username), 
								replacement_name, field_value)
						# \b matches whole word only (Word Boundry), works for compound fields
						elif (headers[column_count] in 
							namespace.CompoundColumns.get('columns')):
							result = re.subn(r'\b{}\b'.format(username),
								replacement_name, field_value)
						if result:
							csv_data[csv_data.index(row)][column_count] = (
								result[0])
							replacement_count += result[1]
					column_count += 1
			row_count += 1
	if replacement_count > 0:
		namespace.Flags['modified'] = True
		cli.output_message('INFO', 'Updated {replacement_count} usernames.\n')


def datetime_to_dateobject(datetime_string: str) -> datetime:
	"""
	Convert various Jira datetime representation into 24hr time. Formats must comply with
	Java SimpleDateFormat:
	https://confluence.atlassian.com/adminjiraserver073/importing-data-from-csv-861253680.html

	Witnessed time formats:
		A) 2021-06-09T15:25:31.217-0400
		A1) 2017-12-04T07:13:55.326-07:00
		A2) 2017-08-07 10:29:49.243
		# B) 20/Jan/20 9:51 AM (Unpadded hour - forced padding makes this one obsolete)
		B) 01/Jan/06 07:04 AM (Padded hour)
		C) 12/17/2019  2:40:00 PM (Unpadded hour)
		D) Dec/13/2017 07:03 AM
		E) 06/08/2020 18:34
		E2) 6/8/2020 (Unpadded version of E)
		F) 2021-06-04
		G) 24/06/2005_11:16 # This is my format: should be unique so the script won't get confused.
		H) 12/14/21 01:33 PM # GIDE format
		I) Dec 01, 2019 12:00 PM

	Args:
		datetime_string: string representing a Jira datetime.

	Returns:
		Standardised Python datetime object.
	"""

	# Left pad any single digits with 0.
	if datetime_string:
		datetime_string = re.sub(r'(\b\d{1}\b)', r'0\1', datetime_string)

	# Determine which datetime format you have
	format_a = (r'\d{4}-(0[0-9]|1[0-2])-(0[0-9]|[1-2][0-9]|3[0-1])T(0[0-9]|'
		r'1[0-9]|2[0-3]):(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9]).\d{3}[+-]'
		r'\d{4}')
	format_a1 = (r'\d{4}-(0[0-9]|1[0-2])-(0[0-9]|[1-2][0-9]|3[0-1])T(0[0-9]|'
		r'1[0-9]|2[0-3]):(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9]).\d{3}[+-](0'
		r'[0-9]|1[0-9]|2[0-3]):(0[0-9]|[1-5][0-9])')
	format_a2 = (r'\d{4}-(0[0-9]|1[0-2])-(0[0-9]|[1-2][0-9]|3[0-1])\s(0[0-9]|'
		r'1[0-9]|2[0-3]):(0[0-9]|[1-5][0-9]):(0[0-9]|[1-5][0-9]).\d+')
	format_b = (r'(0[1-9]|[1-2][1-9]|3[0-1]|)\/\w{3}\/\d{2}\s+(0[0-9]|1[0-2])'
		r':([0-5][0-9])\s+([A,P]M)')
	format_c = (r'(([0-9])|([0-9]|1[0-2]))\/([0-5][0-9])\/\d{4}\s+([0-9]|'
		r'1[0-2]):([0-5][0-9]):([0-5][0-9])\s+([A,P]M)')
	format_d = (r'\w{3}\/([0-5][0-9])\/\d{4}\s+(0[0-9]|1[0-2]):(0[0-9]|[1-5]'
		r'[0-9])\s+([A,P]M)')
	format_e = (r'(0[0-9]|1[0-2])\/(0[1-9]|[1-2][0-9]|3[0-1])\/\d{4}\s+(0'
		r'[0-9]|1[0-9]|2[0-3]):([0-5][0-9])')
	format_f = r'\d{4}-(0[0-9]|1[0-2])-(0[1-9]|[1-2][0-9]|3[0-1])'
	# Format G is the result of running this script (already processed)
	format_g = (r'(0[1-9]|[1-2][0-9]|3[0-1])\/(0[0-9]|1[0-2])\/\d{4}_(0[0-9]|'
		r'1[0-9]|2[0-3]):([0-5][0-9])')
	format_h = (r'(([0-9])|([0-9]|1[0-2]))\/([0-5][0-9])\/\d{2}\s+(0[0-9]|'
		r'1[0-2]):([0-5][0-9])\s+([A,P]M)')
	format_i = (r'\w{3}\s([0-5][0-9]),\s\d{4}\s(0[0-9]|1[0-2]):(0[0-9]|[1-5]'
		r'[0-9])\s+([A,P]M)')

	format_string = ''
	if re.search(format_a, datetime_string):
		format_string = r'%Y-%m-%dT%H:%M:%S.%f%z'
	elif re.search(format_a1, datetime_string):
		# Remove colon from timezone
		search_pattern = (r'([+-])(\d([0-9]|1[0-9]|2[0-3])):'
			r'(\d([0-9]|[1-5][0-9]))')
		replacement_pattern = r'\1\2\4'
		datetime_string = re.sub(search_pattern, replacement_pattern, 
			datetime_string)
		format_string = r'%Y-%m-%dT%H:%M:%S.%f%z'
	elif re.search(format_a2, datetime_string):
		format_string = r'%Y-%m-%d %H:%M:%S.%f'
	elif re.search(format_b, datetime_string):
		# hour_start_index = datetime_string.find(' ') + 1  # +1 retain space
		# hour_stop_index = datetime_string.find(':')
		# hour = datetime_string[hour_start_index:hour_stop_index]
		# hour = int(hour.strip())
		format_string = r'%d/%b/%y %I:%M %p'
	elif re.search(format_c, datetime_string):
		hour_start_index = datetime_string.find(' ') + 1  # +1 retain space
		hour_stop_index = datetime_string.find(':')
		hour = datetime_string[hour_start_index:hour_stop_index]
		hour = int(hour.strip())
		if hour < 10:  # Pad hour to two digits
			head = datetime_string[:hour_start_index]
			tail = datetime_string[hour_stop_index:]
			datetime_string = '{}0{}{}'.format(head, str(hour), tail)
		format_string = r'%m/%d/%Y %I:%M:%S %p'
	elif re.search(format_d, datetime_string):
		format_string = r'%b/%d/%Y %I:%M %p'
	elif re.search(format_e, datetime_string):
		format_string = r'%m/%d/%Y %H:%M'
	elif re.search(format_f, datetime_string):
		format_string = r'%Y-%m-%d'
	elif re.search(format_g, datetime_string):
		format_string = r'%d/%m/%Y_%H:%M'
	elif re.search(format_h, datetime_string):
		format_string = r'%m/%d/%y %I:%M %p'
	elif re.search(format_i, datetime_string):
		format_string = r'%b %d, %y %I:%M %p'
	else:
		cli.output_message('error', f'\"{datetime_string}\" using an '
			'unrecognized date format. Please update patterns.')
		quit()

	datetime_object = None
	if not format_string == '':
		datetime_object = datetime.strptime(datetime_string, 
			format_string)
	else:
		cli.output_message('error', 'Unable to parse datetime value: '
			f'\"{datetime_string}\"')

	if datetime_object is None:
		try:
			# Excel serial date format 
			# (i.e. 44287.3166666667 = 04/01/2021 07:36)
			date_float = float(datetime_string)
			base = datetime(1899, 12, 30)
			delta = datetime.timedelta(days=date_float)
			datetime_object = base + delta
		except ValueError:
			cli.output_message('error', 'Unhandled date format: '
				f'\"{datetime_string}\"')
	return datetime_object


def merge_dataset(dataset_a, dataset_b) -> list:
	"""
	Merge two datasets that do not contain duplicate headings but may not contain the same columns.
	"""

	full_dataset = []
	if len(dataset_a) > 0:
		dataset_a_headers = dataset_a[0]
		dataset_a_rows = [row for row in dataset_a if dataset_a.index(row) != 0]
	else:
		dataset_a_headers = []
		dataset_a_rows = []

	dataset_b_headers = dataset_b[0]
	dataset_b_rows = [row for row in dataset_b if dataset_b.index(row) != 0]

	if dataset_a_headers == dataset_b_headers:
		# Simple merge
		full_dataset = dataset_a
		for row in dataset_b_rows:
			full_dataset.append(row)
	else:
		# Complex merge
		# Merge headers and use index of headers to add rows
		full_headers = sorted(list(dataset_a_headers + dataset_b_headers))
		full_dataset.append(full_headers)

		# Align set a to new column structure
		map_a_to_full = {i: -1 for i in range(len(dataset_a_headers))}
		for i in range(len(dataset_a_headers)):
			# Get column name and count
			value = dataset_a_headers[i]
			value_count = dataset_a_headers.count(value)
			# Determine target index
			if value_count > 1:
				value_indices = []
				for j in range(len(dataset_a_headers)):
					if dataset_a_headers[j] == value:
						value_indices.append(j)
				target_indices = []
				for j in range(len(full_headers)):
					if full_headers[j] == value:
						target_indices.append(j)
				for index in value_indices:
					value_index = value_indices.index(index)
					target_index = target_indices[value_index]
					if map_a_to_full[index] == -1:
						map_a_to_full[index] = target_index
			else:
				target_index = full_headers.index(value)
				map_a_to_full[i] = target_index

		for row in dataset_a_rows:
			new_row = list(['' for field in range(len(full_headers))])
			for col in range(len(row)):
				new_row[map_a_to_full.get(col)] = row[col]
			if new_row not in full_dataset:
				full_dataset.append(new_row)
			new_row = None

		map_b_to_full = {i: -1 for i in range(len(dataset_b_headers))}
		for i in range(len(dataset_b_headers)):
			# Get column name and count
			value = dataset_b_headers[i]
			value_count = dataset_b_headers.count(value)
			# Determine target index
			if value_count > 1:
				value_indices = []
				for j in range(len(dataset_b_headers)):
					if dataset_b_headers[j] == value:
						value_indices.append(j)
				target_indices = []
				for j in range(len(full_headers)):
					if full_headers[j] == value:
						target_indices.append(j)
				for index in value_indices:
					value_index = value_indices.index(index)
					target_index = target_indices[value_index]
					if map_b_to_full[index] == -1:
						map_b_to_full[index] = target_index
			else:
				target_index = full_headers.index(value)
				map_b_to_full[i] = target_index

		for row in dataset_b_rows:
			new_row = list(['' for field in range(len(full_headers))])
			for col in range(len(row)):
				new_row[map_b_to_full.get(col)] = row[col]
			if new_row not in full_dataset:
				full_dataset.append(new_row)
			new_row = None

	full_dataset = remove_empty_columns(full_dataset)
	return full_dataset


def find_and_replace_in_column(csv_data: list, column_name:str, 
	lookup_dict: dict) -> bool:
	"""
	Search within specified column for values matching dict keys and 
	replace with dict values. Return true if any replacements are made.

	Args:

	Returns:

	"""
	
	headers = csv_data[0]
	target_columns = get_columns(headers, column_name)
	modified = False
	for row in range(len(csv_data)):
		for col in target_columns:
			field_value = csv_data[row][col]
			if field_value != '' and field_value in lookup_dict.keys():
				new_value = lookup_dict.get(field_value)
				csv_data[row][col] = new_value
				modified = True
	return modified


def count_attachments(csv_data: list) -> int:
	"""
	Get a count of attachments in a CSV dataset.

	Args:

	Returns:

	"""

	headers = csv_data[0]
	csv_rows = [row for row in csv_data if csv_data.index(row) != 0]
	attachment_columns = get_columns(headers, 'Attachment')
	# Remove columns that contain "attachment"
	for col in attachment_columns:
		if not re.search('^attachment$', headers[col].lower()):
			attachment_columns.remove(col)

	attachment_count = 0
	for row in csv_rows:
		for col in attachment_columns:
			if row[col] != '':
				attachment_count += 1
	return attachment_count


def get_epic_link_dict(csv_data: list) -> dict:
	"""
	Get {issue_key: Epic_name} for all epics.

	Args:

	Returns:

	"""

	headers = csv_data[0]
	issue_key_columns = get_columns(headers, 'Issue Key')
	epic_name_columns = get_columns(headers, 'Epic Name')
	issue_key_epic_name_dict = {}
	csv_rows = [row for row in csv_data if csv_data.index(row) != 0]
	for row in csv_rows:
		for col in epic_name_columns:
			epic_name = row[col]
			if epic_name:
				for issue_key_column in issue_key_columns:
					issue_key_epic_name_dict[row[issue_key_column]] = epic_name
	return issue_key_epic_name_dict


def interactive_find_and_replace(csv_data: list) -> bool:
	"""
	Find and replace column values interactively.

	Args:
		csv_data: CSV data represented as list of rows.
	"""

	modified = False
	while True:
		column_name = input('Type a column name or leave blank to quit: ')
		if column_name == '':  # Exit condition
			break
		search_string = input(
			'Enter string to search for in "{}": '.format(column_name))
		replacement_string = input(
			'Enter string to replace "{}": '.format(search_string))

		headers = csv_data[0]
		cols = get_columns(headers, column_name)
		if len(cols) > 0:
			# Replace key in csv data
			row_count = 0
			replacement_count = 0
			desc = (f'Replacing "{search_string}" with "{replacement_string}" '
				f'in column "{column_name}"')
			for row in tqdm(csv_data, desc=desc):
				if csv_data.index(row) != 0:
					for col in cols:
						if csv_data[csv_data.index(row)][col] == search_string:
							csv_data[csv_data.index(row)][col] = csv_data[
								csv_data.index(row)][col].replace(
									search_string, replacement_string)
							replacement_count += 1
							modified = True
				row_count += 1
			cli.output_message('info', f'Completed {replacement_count} '
				f'replacements of \"{search_string}\" with '
				f'\"{replacement_string}\", in column \"{column_name}\"')
		else:
			cli.output_message('info', f'{column_name}, not found.')
	return modified


def split_filename(input_filename: str) -> list:
	"""
	Split a filename into name and extension. Applicable to windows files with standard three
	letter extensions.

	Args:
		input_filename(str):

	Returns:
		(list): [filename, extension]
	"""

	reverse_string = input_filename[::-1]
	separator_index = reverse_string.index('.')
	reverse_extension = reverse_string[:separator_index]
	reverse_filename = reverse_string[separator_index + 1:]  # +1 to remove extension delimiter
	extension = reverse_extension[::-1]
	filename = reverse_filename[::-1]
	return [filename, extension]


def rekey_checklist(input_data: dict, key: str) -> dict:
	"""
	Replace project key in checklist data.
	"""

	new_dataset = {}
	for item in input_data:
		if item[:item.index('-')] != key:
			new_key = key + item[item.index('-'):]
			new_dataset[new_key] = input_data[item]
		else:
			new_dataset[item] = input_data[item]
	return new_dataset


def remove_invalid_checklist(input_data: dict) -> dict:
	"""

	"""

	new_dataset = {}

	for issue in input_data:  # Dict
		new_dataset[issue] = {}
		for field in input_data[issue]:  # Dict
			# if field value isn't a list, skip it
			if type(input_data[issue][field]) == list:
				new_dataset[issue][field] = input_data[issue][field]
	return new_dataset


def remove_special_chars_from_checklist(input_data: dict) -> dict:
	"""

	"""

	new_dataset = {}
	remove_characters_list = [r'"']

	for issue in input_data:  # Dict
		for field in input_data[issue]:  # Dict
			checklist_length = len(input_data[issue][field])
			for index in range(checklist_length):  # List
				for case in remove_characters_list:
					input_data[issue][field][index]['name'] = \
						input_data[issue][field][index]['name'].replace(case, '')
		new_dataset[issue] = input_data[issue]
	return new_dataset


def get_attachment_data(attachment_list: list) -> dict:
	"""
	Given a list of attachments from CSV, return filename plus data.

	Expected attachment field schema: 'date; author; filename; url'

	Args:
		attachment_list(list): list of attachments for a single issue.

	Returns:
		(list): List of filenames
	"""

	class Attachment_Schema(Enum):
		"""
		This is the expected name and order of data within an attachment.
		"""
		datetime = 0
		uploader = 1
		filename = 2
		url = 3

	filename_dict = {}
	for attachment in attachment_list:
		split_attachment = attachment.split(';')
		filename_dict[split_attachment[Attachment_Schema.filename.value]] = [
			split_attachment[Attachment_Schema.datetime.value],
			split_attachment[Attachment_Schema.uploader.value],
			split_attachment[Attachment_Schema.url.value]
			]
	return filename_dict


def get_formatted_current_datetime(format_string: str) -> str:
	"""
	Get current time and return as string matching given format.

	Reference:
		%Y - 4-digit year
		%y - zero padded 2-digit year
		%m - zero padded month
		%d - zero padded day
		%H - zero padded 24-hour hour
		%I - zero padded 12-hour hour
		%M - zero padded minute
		%S - zero padded seconds
		%f - zero padded microseconds
		%z - UTC timezone offset +-HHMM

	Common Jira formats:
		Sprints: %Y-%m-%dT%H:%M:%S.%f%z

	Args:
		format_string(str): strftime format string.

	Returns:
		(str): Formatted time string.
	"""

	now = datetime.now()
	return now.strftime(format_string)


def get_issue_types(csv_data: list) -> list:
	"""
	Get list of issue types included in the CSV.
	
	"""

	# Get Issue type column.
	issue_type_columns = get_columns(csv_data[0], 'Issue Type')

	# Get Issue Type names
	issue_types = []
	data_rows = [row for row in csv_data if csv_data.index(row) != 0]
	for column in issue_type_columns:
		column_values = set([row[column] for row in data_rows])
		for value in column_values:
			issue_types.append(value)
	
	return issue_types
