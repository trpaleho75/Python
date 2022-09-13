#!/usr/bin/env python
# Coding = UTF-8

"""
	This module provides all command line interaction with the user.
"""

# Imports - Built-in
from datetime import datetime
import logging
import re
from tqdm import tqdm
from types import SimpleNamespace

# Imports - 3rd party
from dateutil.parser import parse

# Imports - Local
import migration.core as core
import migration.cli as cli
import migration.io_module as io_module


# Logging
log = logging.getLogger(__name__)


# Functions
def offline_only(namespace: SimpleNamespace):
	"""
	While offline all data comes from the CSV file. Create users, sprints, versions, and components.
	Add .csv and .key to namespace.

	Args:
		namespace(Simplenamespace): Namespace containing configuration data.
	"""

	# Get CSV file from user.
	namespace.csv = io_module.get_filename('Select your CSV file', [['CSV files', '*.csv']])

	# Read CSV data and pull project key.
	csv_dataset = io_module.read_csv(namespace.csv)
	namespace.key = core.get_project_key(csv_dataset, namespace)

	# Unatended export
	auto = namespace.Flags.get('unattended')

	# Get headers
	headers = csv_dataset[0]

	# Create user table
	user_table = [['Username', 'NT Username']]
	if cli.ask_yes_no('Create user table from CSV? (Y/N): ', auto):
		user_list = create_user_list_offline(csv_dataset, namespace)
		cli.output_message('INFO', f'Writing {len(user_list)} users to csv.')
		new_filename = io_module.build_filename(namespace.csv, '_Users')
		for user in user_list:
			user_table.append([user,''])
		user_table.append(['remap_user', ''])
		io_module.write_csv(user_table, new_filename)

	# Get components
	if cli.ask_yes_no('Create component table (Y/N): ', auto):
		field_list = ['Component/s']
		io_module.write_csv_field_values(namespace.csv, csv_dataset, 
			'Components', 'name', field_list)

	# Get sprints
	if cli.ask_yes_no('Create sprint table (Y/N): ', auto):
		field_list = ['Sprint']
		io_module.write_csv_field_values(namespace.csv, csv_dataset, 'Sprints',
			'name', field_list)

	# Get versions
	if cli.ask_yes_no('Create version table (Y/N): ', auto):
		field_list = ['Fix Version/s', 'Affects Version/s']
		io_module.write_csv_field_values(namespace.csv, csv_dataset, 
			'Versions', 'name', field_list)

	# Write updated csv if necessary
	if namespace.Flags.get('modified'):
		message = (
			"""
			CSV data modified, writing updated data. \nExtraneous semicolons have been
			converted to hex, ASCII Chr(59) -> %03b. Extra semicolons will prevent Jira
			from parsing fields correctly on import.
			"""
			)
		cli.output_message('info', message)
		io_module.write_csv(csv_dataset, namespace.csv)

	# Metrics - display elapsed time
	cli.finish_message(namespace.start, namespace.csv, namespace.key)


def create_user_list_offline(dataset: list, namespace: SimpleNamespace) -> list:
	"""
	Create a table of unique users for system import. The simple_username_columns
	and compound_username_columns constants listed above, are common to Jira.
	If the source instance is modified, some editing to the two lists below may
	be necessary.

	Args:
		dataset(list): CSV data represented as list of rows.

	Returns:
		(list): List of users
			[['Username', 'NT Username'],['John Doe', 'jdoe52']]
	"""

	# Output variable
	users = []

	# Get issue key column for troubleshooting
	headers = dataset[0]
	issue_key_column = core.get_columns(headers, 'Issue key')
	issue_key_column = (
			issue_key_column[0] if len(issue_key_column) == 1 else quit('Issue key error')
		)

	# search columns for simple value fields that contain usernames
	simple_columns = []
	for heading in namespace.SimpleColumns.get('username'):
		columns = core.get_columns(headers, heading)
		for column in columns:
			simple_columns.append(column)

	# search columns for compound value fields that contain usernames
	compound_columns = []
	for heading in namespace.CompoundColumns.get('columns'):
		columns = core.get_columns(headers, heading)
		for column in columns:
			compound_columns.append(column)

	# Parse usernames from columns and add to list
	row_count = 0
	for row in tqdm(dataset, desc='Parsing rows for usernames'):
		issue_key = row[issue_key_column]
		if dataset.index(row) != 0:
			for column in simple_columns:
				try:
					field_value = row[column]
					if field_value:
						if not field_value in users:
							users.append(field_value)
				except Exception as exception_message:
					message = f'{issue_key}: {headers[column]}. Error: {exception_message}'
					log.error(message)
			for column in compound_columns:
				try:
					field_value = row[column]
					if field_value:
						username = ''
						# Precheck field for malformed data and delete if necessary
						if field_value.count(';') == 0:
							message = (f'{issue_key}: Deleted Malformed \"{headers[column]}\"' +
								f' = {field_value}')
							log.error(message)
							dataset[row_count][column] = ""
							break
						else:
							data = split_compound_offline(
								issue_key,
								field_value,
								headers[column],
								dataset,
								namespace
								)
							if len(data) > 0:
								username = data.get('username')
								if username and not username in users:
									users.append(username)
							else:
								message = (f'{issue_key}: Unable to parse {headers[column]} ' +
									f'field = {field_value}.')
								log.error(message)
				except Exception as exception_message:
					message = (f'{issue_key}: Bad {headers[column]} compound field = ' +
						f'{exception_message}')
					log.error(message)
		row_count += 1
	log.info('Completed parsing user data')
	users = sorted(users)
	return users


def split_compound_offline(issue_key: str, field_value: str, field_name: str, 
	dataset: list, namespace: SimpleNamespace) -> dict:
	"""
	Split compound field value into dictionary of individual values. Individual values are
	separated by semicolons, but sometimes a field contains semicolons which cause improper
	splitting of the field. If field splits into more than the expected number of values,
	user assistance will be requested. Will skip "last" fields since they cannot be imported.

	Args:
		key(str): Issue key being processed
		field_value (str): Raw data from cvs cell.
		field_name (str): Name of column to identify expected value by field schema.
		dataset (list): Full dataset for updating records based on manual split. Will replace
			semicolons with the equivalent hex character code (';' = %03b).
		namespace(SimpleNamespace): Configuration information.

	Returns:
		(dict): dictionary of values contained in the field.
	"""

	values = {}
	if field_name in namespace.ColumnExclusions.get('columns'):
		values = {}  # Do not process.
	else:
		schema = namespace.Schemas.get(field_name.replace(' ', '').lower())
		split_field = field_value.split(';')
		while len(split_field) != len(schema):
			split_field = _auto_data_split_offline(issue_key, field_value, field_name, dataset)
		else:
			for field in schema:
				field_value = split_field[schema.index(field)]
				if core.validate_value(field, field_value):
					values[field] = field_value

	return values


def _auto_data_split_offline(
	issue_key: str,
	field_value: str,
	field_type: str,
	csv_data: list,
	namespace: SimpleNamespace
	) -> list:
	"""
	Automatically split compound fields. Compound fields are semicolon delimited, but if a user
	uses semicolons in their comments the field will not split correctly and the import will fail.
	This function attempts to identify extraneous semicolons and replace them with their hex
	equivalent so import can be performed.

	Args:
		field_value(str): Value of compound field.
		field_type(str): Type of filed. Used for validation and schema identification.
		input_list(list): List of CSV data. Corrected field value will be written back.

	Returns:
		(list): List with values corrected.
	"""

	headers = csv_data[0]
	dataset = []
	delimiter = ';'
	hex_delimiter = '%3b'
	schema = namespace.Schemas.get(field_type.replace(' ', '').lower())
	location = core.get_field_location(issue_key, csv_data, field_value)

	# log if field doesn't match target schema length
	if len(field_value.split(delimiter)) < len(schema):
		schema_str = '; '.join(schema)
		message = (f'{issue_key}: Invalid input, {field_type} should have {len(schema)} values' +
					f' = {schema_str}: {field_value}')
		log.warning(message)

		new_values = None
		# Attempt to determine missing part
		split_values = field_value.split(';', maxsplit=len(schema))
		# attachment missing username
		if field_type == 'attachment':
			new_values = _auto_split_attachment(issue_key, field_value, schema)
		elif field_type == 'comment' and len(split_values) == 2:
			message = f'{issue_key}: Error splitting compound field ({field_type}) = {field_value}'
			log.warning(message)
			datetime_valid = core.validate_value('datetime', split_values[schema.index('datetime')])
			if datetime_valid:
				split_values.insert(schema.index('username'), 'Unknown')
				new_values = split_values
		else:  # User input required
			field_value = input('Fix the above string (copy and paste here): ')
			parse_input = field_value.split(';', maxsplit=len(schema))
			if len(parse_input) == len(schema):
				new_values = parse_input
		# update existing data
		if new_values:
			new_field_value = ';'.join(new_values)
			csv_data[location.get('row')][location.get('col')] = new_field_value
			message = (f'Input modified at ' + location.get('row') + ':' + location.get('col') +
				f' = {new_field_value}')
			log.warning(message)

	# Process a valid field value
	working_string = field_value
	schema_index = 0
	while len(working_string) > 0:
		this_field = working_string.split(delimiter, maxsplit=1)
		if len(this_field) > 1:
			if working_string.count(delimiter) > 0:
				# there is more to split
				next_field = this_field[1].split(delimiter, maxsplit=1)
				if schema[schema_index] != schema[-1]:
					test_next = core.validate_value(schema[schema_index + 1], next_field[0])
					if test_next:
						test_this = core.validate_value(schema[schema_index], this_field[0])
						if test_this:
							dataset.append(this_field[0])
							schema_index += 1
							working_string = this_field[1]
						else:
							log.error(f'{issue_key}: Invalid data = {field_value}')
					else:  # Next piece is not the right type = bad split
						working_string = working_string.replace(delimiter, hex_delimiter, 1)
				else:  # This is the last schema field
					# Last field but there is more to split, replace remaining delimiters
					working_string = working_string.replace(delimiter, hex_delimiter, 1)
			else:  # No next field
				working_string = working_string.replace(delimiter, hex_delimiter, 1)
		else:  # Only one piece left
			#Validate and add to dataset
			test = core.validate_value(schema[schema_index], this_field[0])
			if test:
				dataset.append(this_field[0])
				working_string = ''

	if -1 not in location.values():
		new_string = ';'.join(dataset)
		csv_data[location.get('row')][location.get('col')] = new_string
		namespace.Flags.modified = True
	return dataset


def _auto_split_attachment(issue_key: str, field_value: str, field_schema: list) -> list:
	"""
	Get specific portions of a compound field. Order is important to help ensure that the correct
	data is isolated. [0, 3, 2, 1]
	"""

	new_field_values = ['' for field in field_schema]
	split_field = field_value.split(';', maxsplit=len(field_schema))

	# Validate datetime = field_schema[0] can be evaluated as date/time
	for value in split_field:
		try:
			# datetime_value = split_field[field_schema.index('datetime')]
			test = parse(value, fuzzy=False)
			if isinstance(test, datetime):
				new_field_values[field_schema.index('datetime')] = value
				split_field.remove(value)
				break
		except:
			# Exceptions will be thrown whenever the data isn't the first field.
			message = 'Value not at expected location'
			log.warn(message)
			continue


	# Validate location = field_schema[3] is a string starting with http or file and containing ://
	regex_pattern = r'(^http|file).*[.]{1}\w+$'
	for value in split_field:
		if len(re.findall(regex_pattern, value)) == 1:
			new_field_values[field_schema.index('location')] = value
			split_field.remove(value)
			break

	# Validate filename = field_schema[2] is a string with a dot and single word extension
	regex_pattern = r'^.*[.]{1}\w+$'
	for value in split_field:
		if len(re.findall(regex_pattern, value)) == 1:
			# Filename transforms to match url encoding
			value = value.replace(' ', '+')
			value = value.replace('@', '%40')
			value = value.replace('=', '%3D')
			new_field_values[field_schema.index('filename')] = value
			split_field.remove(value)
			break

	# Validate username = field_schema[1] is a string with no whitespace
	regex_pattern = r'\s'
	for value in split_field:
		if not re.match(regex_pattern, value):  # Field contains something without whitespace
			new_field_values[field_schema.index('username')] = value
		else:  # Field contains whitespace (Invalid username)
			new_field_values[field_schema.index('username')] = 'Unknown'
	if not split_field and not new_field_values[field_schema.index('username')]:  # Field is null
		new_field_values[field_schema.index('username')] = 'Unknown'

	if not all(new_field_values):
		message = f'{issue_key}: Unable to parse value, {field_value}'
		log.error(message)
		print(message)

	return new_field_values
