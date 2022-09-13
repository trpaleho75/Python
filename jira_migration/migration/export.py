#!/usr/bin/env python
# Coding = UTF-8

"""
	This module will contain functions exclusive to the export of
	Jira projects.
"""

# Imports - Built-in
import http
import logging
import os
import time
from tqdm import tqdm
from types import SimpleNamespace

# Imports - Local
from migration import cli, core, io_module, web


# Logging
log = logging.getLogger(__name__)


# Functions
def export(namespace: SimpleNamespace):
	"""
	Export project data from a Jira server.
	"""

	log.info("\nExport Started")

	# Common variables from namespace
	retries = namespace.General.get('retries')
	timeout = namespace.General.get('timeout')
	page_step = namespace.General.get('page_step')
	sleep_duration = namespace.General.get('sleep_duration')
	auto = namespace.Flags.get('unattended')

	csv_data = []
	filename = ''
	while filename == '':
		if cli.ask_yes_no('Do you have a CSV file already? (Y/N): '):
			filename = io_module.get_filename('Select your CSV file', 
				[['CSV files', '*.csv']])
			csv_data = io_module.read_csv(filename)
			namespace.project_key = core.get_project_key(csv_data, namespace)
		else:
			namespace.project_key = input('Enter project key to '
				'export: ').upper()
			if web.project_exists(namespace.session, namespace.url,
				namespace.project_key, http.HTTPStatus.OK, retries, timeout):
				directory = io_module.get_directory(
					'Select CSV export directory.',
					'Select CSV export directory.'
					)
				filename = web.get_all_issues(namespace.session,namespace.url,
					namespace.project_key, directory, 
					namespace.DateFormats.get('files'), page_step, retries,
					timeout, sleep_duration)
			while len(csv_data) == 0:
				if os.path.exists(filename):
					csv_filesize = os.path.getsize(filename)
					if csv_filesize > 0:
						csv_data = io_module.read_csv(filename)
					else:
						cli.output_message('error', 'Empty CSV. Exiting...')
						quit()
				if not os.path.exists(filename):
					# Wait a sec
					time.sleep(sleep_duration)
	
	# Remove empty columns
	if cli.ask_yes_no('find and remove empty columns? (Y/N): ', auto):
		resulting_dataset = core.remove_empty_columns(csv_data)
		if resulting_dataset[1] is True:
			csv_data = resulting_dataset[0]
			namespace.Flags['modified'] = True

	# Create user table
	user_table = [['Username', 'NT Username']]
	if cli.ask_yes_no('Create user table from CSV? (Y/N): ', auto):
		user_list = create_user_list_online(namespace, csv_data)
		cli.output_message('INFO', f'Writing {len(user_list)} users to csv.')
		user_table_filename = io_module.build_filename(filename, '_Users')
		for user in user_list:
			user_table.append([user,''])
		user_table.append(['remap_user', ''])
		io_module.write_csv(user_table, user_table_filename)

	# Get components
	cli.output_message('INFO', 'Checking for components in project.')
	components = web.get_project_components(namespace.session, namespace.url,
		namespace.project_key, retries, timeout)
	if len(components) > 0:
		if cli.ask_yes_no(f'Found {len(components)} components in '
			f'{namespace.project_key}. Would you like to export components? '
			'(Y/N): ', auto):
			components_filename = io_module.build_filename(filename,
				'_Components')
			io_module.list_to_csv(components, components_filename)
		else:
			log.info('No components found. No component table created.')

	# Get Boards and Filters
	cli.output_message('INFO', 'Checking boards in project.')
	boards = web.get_boards(namespace.session, namespace.url, 
		namespace.project_key, retries, timeout)
	if len(boards) > 0:
		if cli.ask_yes_no(f'Found {len(boards)} boards in '
			f'{namespace.project_key}. Do you want to Export boards and '
			'associated filters? (Y/N): ', auto):
			# Get Board Details
			board_configs = web.get_board_configs(namespace.session,
				namespace.url, boards, retries, timeout)
			# Get filters
			filter_ids = [config.get('filter').get('id') for config in 
				board_configs]
			filters = web.get_filters(namespace.session, namespace.url,
				filter_ids, retries, timeout)
			# Write board data
			io_module.list_to_csv(board_configs,
				io_module.build_filename(filename, '_Board_Configs'))
			io_module.list_to_csv(filters, io_module.build_filename(filename,
				'_Board_Filters'))

	# Get sprints
	if len(boards) > 0:
		if cli.ask_yes_no('Would you like to view available sprint data '
			'for export? (Y/N): ', auto):
			web.display_sprints(namespace.session, namespace.url, boards,
				namespace.project_key, retries, timeout, page_step)
			if cli.ask_yes_no('Would you like to export sprint data? (Y/N): ', 
				auto):
				for board in boards:
					# Sanitize board name
					board_name = board.get('name').replace(' ', '_')
					board_name = board.get('name').replace('/', '_')
					sprints = web.get_sprints_from_board_id(namespace.session, 
						namespace.url, board.get('id'), page_step, retries, 
						timeout)
					if len(sprints) > 0:
						sprint_filename = io_module.build_filename(filename,
							f'_Sprints-{board_name}')
						io_module.sprint_dict_to_csv(sprints, sprint_filename)

	# Get versions
	versions = web.get_version_info(namespace.session, namespace.url, 
		namespace.project_key, retries, timeout)
	if len(versions) > 0:
		if cli.ask_yes_no(f'Found {len(versions)} versions in '
			f'{namespace.project_key}. Would you like to export versions? (Y/N): ', 
			auto):
			io_module.list_to_csv(versions, io_module.build_filename(filename,
				'_Versions'))

	# Export checklists
	checklists_exported = False
	if cli.ask_yes_no('Would you like to export checklists? (Y/N): ', auto):
		checklists_exported = True
		# Build filename
		append = '_Checklists'
		ext = '.json'
		checklist_filename = io_module.build_filename(filename, append, ext)
		web.export_checklists(namespace.session, namespace.url, 
			checklist_filename, namespace.project_key, page_step, retries, 
			timeout)
		

	# Export screens
	screens_exported = False
	if cli.ask_yes_no('Would you like to export screens (SDTE Only)? (Y/N): ', 
		auto):
		screens_exported = True
		append = '_Screens'
		ext = '.json'
		new_filename = io_module.build_filename(filename, append, ext)
		web.export_screens(namespace.session, namespace.url,
			namespace.CustomRESTEndpoints.get('screen_export'), 
			namespace.project_key, new_filename, retries, timeout)

	# Write field list
	if checklists_exported or screens_exported:
		fields = web.get_fields(namespace.session, namespace.url, retries, 
			timeout)
		io_module.list_to_csv(fields, io_module.build_filename(filename,
			'_Fields'))

	# Download attachments
	attachments = core.find_attachments(csv_data)
	if len(attachments) > 0:
		if cli.ask_yes_no(f'Found {len(attachments)} attachments in '
			f'{namespace.project_key}. Would you like to download attachments (Y/N): ', 
			auto):
			web.direct_download(namespace.session, namespace.url, attachments,
				filename, namespace.project_key, retries, timeout)

	# Convert long fields to attachments
	# get attachment directory
	if cli.ask_yes_no('Scan and fix oversized fields (>32767 bytes))? '
		'(Y/N): ', auto):
		target_path = os.path.dirname(filename)
		target_path = '{}/{}'.format(target_path, namespace.project_key)
		core.fix_oversize_fields(namespace, csv_data, target_path, 
			namespace.project_key)

	# Write updated csv if necessary
	if namespace.Flags.get('modified'):
		cli.output_message('info', 'CSV data modified, writing updated data. '
			'\nExtraneous semicolons have been converted to hex, ASCII '
			'Chr(59) -> %03b. Extra semicolons will prevent Jira from parsing '
			'fields correctly on import.')
		io_module.write_csv(csv_data, filename)

	# Metrics - display elapsed time
	cli.finish_message(namespace.start, filename, namespace.project_key)


def map_subset(superset_headers: list, subset_headers: list) -> dict:
	"""
	Map columns of subset to a superset of columns. We can't itterate over
	values because list.index() only finds the first value, so we use index
	with range() to ensure that all columns get mapped.

	Args:
		superset_headers(list): List of headers to match to.
		subset_headers(list): List of headers to align with superset.

	Returns:
		(dict): pairs of superset:subset columns.
	"""

	superset_length = len(superset_headers)

	subset_length = len(subset_headers)
	subset_map = {i: -1 for i in range(subset_length)}
	for i in range(subset_length):
		# Get column name and occurrence count
		column_name = subset_headers[i]
		column_name_count = subset_headers.count(column_name)
		# Determine the target index
		if column_name_count > 1:
			# List indices matching value in subset
			subset_indices = []
			for j in range(subset_length):
				if subset_headers[j] == column_name:
					subset_indices.append(j)
			# List indices matching value in superset
			superset_indices = []
			for j in range(superset_length):
				if superset_headers[j] == column_name:
					superset_indices.append(j)
			# Match subset to superset indices
			if len(superset_indices) >= len(subset_indices):
				for subset_index in subset_indices:
					index = subset_indices.index(subset_index)
					superset_index = superset_indices[index]
					if subset_map[subset_index] == -1:
						subset_map[subset_index] = superset_index
		else:
			superset_index = superset_headers.index(column_name)
			subset_map[i] = superset_index
	return subset_map


def create_user_list_online(namespace: SimpleNamespace, dataset: list) -> list:
	"""
	Create a table of unique users for system import. The 
	simple_username_columns	and compound_username_columns constants listed 
	above, are common to Jira. If the source instance is modified, some 
	editing to the two lists below may be necessary.

	Args:
		dataset(list): CSV data represented as list of rows.

	Returns:
		(list): List of users
			[['Username', 'NT Username'],['John Doe', 'jdoe52']]
	"""

	log.info('Parsing user table data')

	# Output variable
	users = []

	# Get issue key column for troubleshooting
	dataset_headers = dataset[0]
	dataset_rows = [row for row in dataset if dataset.index(row) != 0]
	issue_key_column = dataset_headers.index('Issue key')

	# search columns for simple value fields that contain usernames
	simple_columns = []
	for heading in namespace.SimpleColumns.get('username'):
		columns = core.get_columns(dataset_headers, heading)
		for column in columns:
			simple_columns.append(column)

	# search columns for compound value fields that contain usernames
	compound_columns = []
	for heading in namespace.CompoundColumns.get('columns'):
		columns = core.get_columns(dataset_headers, heading)
		for column in columns:
			compound_columns.append(column)

	# Parse usernames from columns and add to list
	row_count = 0
	for row in tqdm(dataset_rows, desc='Parsing dataset for usernames'):
		issue_key = row[issue_key_column]
		for column in simple_columns:
			try:
				field_value = row[column]
				if field_value != '' and not field_value in users:
					users.append(field_value)
			except Exception as exception_message:
				message = (f'Corrupt simple field found in \"{issue_key}\", '
					f'expected column {column}. Error: {exception_message}')
				cli.output_message('error', message)
		for column in compound_columns:
			try:
				field_value = row[column]
				if field_value != '':
					username = ''
					column_header = dataset_headers[column]
					# Precheck field for malformed data and delete if necessary
					if field_value.count(';') == 0:
						cli.output_message('error','Deleted Malformed '
							f'\"{column_header}\" field in \"{issue_key}'
							f'({column}:{row_count})\" = {field_value}')
						dataset[row_count][column] = ""
						break
					else:
						data = web.split_compound_online(namespace, issue_key,
							field_value, column_header, dataset)
					if len(data) > 0:
						username = data.get('username')
						if username != '' and not username in users:
							users.append(username)
					else:
						log.error('Unable to parse %s field in %s ,at row %d, '
						'col %d.', column_header, issue_key, row_count, column)
			except Exception as exception_message:
				row_index = dataset.index(row)
				message = (f'Bad compound field found in row {row_index}, '
					f'column {column}. Error: {exception_message}')
				cli.output_message('error', message)
		row_count += 1

	# Sort user list and return data
	return sorted(users)
