#!/usr/bin/env python
# Coding = UTF-8

"""
	This module contains functions exclusive to pre-import functionality.
"""

# Imports - built in
from http import HTTPStatus
import logging
import os
import sys
from types import SimpleNamespace

# Imports - Local
from migration import cli, core, io_module, web


# Logging
log = logging.getLogger(__name__)


# Functions
def import_pre(namespace: SimpleNamespace):
	"""
	Perform steps that have to be done before CSV can be imported.
	"""

	log.info('\nPre-Import Started')

	# Common variables from namespace
	session = namespace.session
	base_url = namespace.url
	username = namespace.username
	retries = namespace.General.get('retries')
	timeout = namespace.General.get('timeout')
	page_step = namespace.General.get('page_step')
	sleep_duration = namespace.General.get('sleep_duration')
	datetime_format_fields = namespace.DateFormats.get('fields')
	datetime_format_version = namespace.DateFormats.get('version')
	datetime_columns_simple = namespace.SimpleColumns.get('datetime')
	columns_compound = namespace.CompoundColumns.get('columns')
	column_exclusions = namespace.ColumnExclusions.get('columns')
	rest_endpoint_screen_import = \
		namespace.CustomRESTEndpoints.get('screen_import')
	rest_endpoint_epic_status = namespace.CustomRESTEndpoints.get('epic_status')

	# Get csv file and validate path
	csv_file = ''
	while not os.path.exists(csv_file):
		csv_file = io_module.get_filename('Select your CSV file', 
			[['CSV files', '*.csv']])
		cli.output_message('info', f"Selected file: {csv_file}")

	# Read CSV and remove empty columns
	csv_data = io_module.read_csv(csv_file)
	resulting_dataset = core.remove_empty_columns(csv_data)
	if resulting_dataset[1] is True: # True if empty columns were removed
		csv_data = resulting_dataset[0] # Dataset minus empty columns
		namespace.Flags['modified'] = True

	# Get project keys and rekey if necessary
	cli.output_message('info', '\nChecking project key')
	project_key = core.get_project_key(csv_data, namespace)
	namespace.__setattr__('project_key_org', project_key.upper())
	new_key = input(f'Exported key = \"{project_key}\". Enter new key to '
		're-key project, leave blank to keep current key: ')
	if new_key:
		namespace.__setattr__('project_key', new_key.upper())
		csv_data = core.replace_project_key(namespace, csv_data, 
			namespace.project_key_org, namespace.project_key)
	else:
		namespace.__setattr__('project_key', project_key)

	# Create project if necessary
	cli.output_message('info', '\nValidating project.')
	while not web.project_exists(session, base_url, namespace.project_key, 
		HTTPStatus.OK, retries, timeout):
		if cli.ask_yes_no(f'{namespace.project_key} not found in Jira. Create '
			'project with Gaia? (Y/N): '):
			web.create_gaia_project(namespace, session, base_url, namespace.project_key)
		else:
			sys.exit('Create project and run script again.')
	cli.output_message('info', f'{namespace.project_key} project found.')

	# Add project roles
	project_roles = []
	permissions_valid = False
	while not permissions_valid:
		# Get project Roles
		project_roles = web.get_project_roles(session, base_url, 
			namespace.project_key, HTTPStatus.OK, retries, timeout)
		# Check if user has permissions to continue
		permissions_valid = web.validate_permissions(session, base_url, 
			namespace.project_key, username, retries, timeout)
		if not permissions_valid:
			web.set_user_roles(session, base_url, namespace.project_key, 
				project_roles, username, retries, timeout)
			permissions_valid = web.validate_permissions(session, base_url, 
				namespace.project_key, username, retries, timeout)
		if permissions_valid:
			# Check if groups need to be assigned
			web.validate_project_groups(session, base_url, 
				namespace.project_key, username, project_roles, retries, timeout)
		else:
			cli.output_message('error', 'Unable to validate user '
				'permissions. Verify you have project admin permission '
				'for the project before continuing.')
			if int(input('Press Enter to continue (0 to quit): ')) == 0:
				quit()

	# Update screens if desired
	web.import_screens(session, base_url, rest_endpoint_screen_import, 
		csv_file, namespace.project_key, retries, timeout)
		
	# Perform necessary CSV modifications
	csv_data = core.update_datetimes(csv_data, datetime_format_fields,
		datetime_columns_simple, columns_compound, column_exclusions, namespace)

	# Import user table
	cli.output_message('info', '\nChecking for user CSVs.')
	file_search_string = '_Users'
	files = io_module.find_files(file_search_string, csv_file, 'csv')
	imported_usernames = None
	if len(files) == 1:
		if cli.ask_yes_no('Would you like to update usernames from user '
			'table? (Y/N): '):
			filename = files[0]  # Only one file returned = index 0
			if os.path.exists(filename):
				imported_usernames = io_module.read_csv(filename)
				imported_usernames = core.list_to_dict(imported_usernames)
				core.replace_usernames(namespace, csv_data, imported_usernames)
			else:
				cli.output_message('error', 'No user table found for import.')
	elif len(files) > 1:
		# Select correct file
		user_file = ''
		while not os.path.exists(user_file):
			cli.output_message('info', 'More than one user file found. '
				'Please select correct file.')
			user_file = io_module.get_filename('Select your _Users CSV file', 
				[['CSV files', '*.csv']])

		if cli.ask_yes_no('Would you like to update usernames from user '
			'table? (Y/N): '):
			imported_usernames = io_module.read_csv(user_file)
			imported_usernames = core.list_to_dict(imported_usernames)
			core.replace_usernames(namespace, csv_data, imported_usernames)
	files = None

	# Import version data
	cli.output_message('info', 'Checking for version CSVs.')
	file_search_string = '_Versions'
	files = io_module.find_files(file_search_string, csv_file, 'csv')
	if len(files) > 0:
		cli.output_message('info', f'Found {len(files)} version file(s).')
		for file in files:
			if '.bak' in file:
				cli.output_message('info', f'Skipping backup file, {file}.')
			else:
				versions = io_module.read_csv(file)
				web.import_versions(session, base_url, namespace.project_key, 
				versions, datetime_format_version, retries, timeout)
	files = None

	# Import Components
	cli.output_message('info', 'Checking for component CSVs.')
	file_search_string = '_Components'
	files = io_module.find_files(file_search_string, csv_file, 'csv')
	if len(files) > 0:
		cli.output_message('info', f'Found {len(files)} component file(s).')
		for file in files:
			if '.bak' in file:
				cli.output_message('info', f'Skipping backup file, {file}.')
			else:
				components = io_module.read_csv(file)
				web.import_components(namespace, session, base_url, 
					namespace.project_key, components)
	files = None

	# For Filters, Boards, and Sprints user must have project permissions.
	flag_import_sprints = cli.ask_yes_no('Would you like to import sprint '
		'data? (Y/N): ')
	has_valid_permission = web.validate_permissions(session, base_url,
		namespace.project_key, username, retries, timeout)
	if flag_import_sprints and has_valid_permission:
		cli.output_message('info', '\nChecking filters')
		filter_id = web.create_filter(namespace, session, base_url, 
			namespace.project_key, project_roles, retries, timeout)
		cli.output_message('info', 'Checking boards')
		board_id = web.create_board(session, base_url, 
			namespace.project_key, filter_id, retries, timeout)
		# Import sprints - Boards must exist before creating sprints
		cli.output_message('info', '\nChecking for sprint CSVs.')
		file_search_string = '_Sprints'
		sprint_files = io_module.find_files(file_search_string, 
			csv_file, 'csv')
		web.import_sprints(namespace, session, base_url,
			sprint_files, board_id, csv_data, retries, timeout, 
			page_step)
		sprint_files = None
	elif not has_valid_permission:
		cli.output_message('warning', 'Unable to validate permissions. Please '
			'verify you are a project admin, some functions may not work.')

	# Update CSV with sprint data
	if flag_import_sprints:
		boards = web.get_boards(session, base_url, namespace.project_key, 
			retries, timeout)
		existing_sprints = web.get_sprints_from_board_list(session, base_url, 
			boards, retries, timeout, page_step)
		if len(existing_sprints) > 0:
			csv_data = web.find_and_replace_sprints(session, base_url, 
				namespace.project_key, csv_data, retries, timeout, page_step, 
				namespace)
		else:
			if cli.ask_yes_no('No sprints found. Is this a child project '
				'with sprints in the parent?\nWould you like to update '
				'sprint with identifiers from a parent project? (Y/N): '):
				new_key = input('Please enter the parent project key for '
					'sprint lookup: ')
				new_key = new_key.upper()
				if web.project_exists(session, base_url, new_key, 
					HTTPStatus.OK, retries, timeout):
					csv_data = web.find_and_replace_sprints(session, base_url, 
						new_key, csv_data, retries, timeout, page_step, 
						namespace)

	# Update attachment fields (option -f/--file)
	attachment_count = core.count_attachments(csv_data)
	if attachment_count > 0:
		cli.output_message('info', f'Found {attachment_count} attachments.')
		if cli.ask_yes_no('Are you importing attachments from the server\'s '
			'local storage? (Y/N): '):
			io_module.local_file_attachments(csv_data, namespace.project_key, 
				namespace.project_key_org, csv_file, namespace)

	# Update epic links to contain epic name
	# Does the data contain Epics?
	has_epics = False
	field_name = "Issue Type"
	headers = csv_data[0]
	issue_type_column = core.get_columns(headers, field_name)
	for col in issue_type_column:
		issue_type_list = [row[col].lower() for row in csv_data if 
			csv_data.index(row) != 0]
		issue_type_set = set(issue_type_list)
		if 'Epic'.lower() in issue_type_set:
			has_epics = True
			if cli.ask_yes_no('Would you like to replace Issue '
				'Keys with Epic Names in the Epic Link column? (Y/N): '):
				epic_dict = core.get_epic_link_dict(csv_data)
				if epic_dict is not None:
					modified = core.find_and_replace_in_column(csv_data, 'Epic Link', 
						epic_dict)
					if modified:
						namespace.Flags['modified'] = True
	
	# Validate Epic Statuses
	if has_epics:
		cli.output_message('info', 'CSV contains Epics; validating statuses.')
		valid_epic_status = web.validate_epic_status(namespace.session, 
			namespace.url, namespace.project_key, csv_data, retries, timeout, 
			namespace.username, rest_endpoint_epic_status)
		if valid_epic_status:
			namespace.Flags['modified'] = True

	# Perform find and replace if necessary
	if cli.ask_yes_no('\nWould you like to find and replace column values? '
		'(Y/N): '):
		if core.interactive_find_and_replace(csv_data):
			namespace.Flags['modified'] = True

	# Create starter config file
	io_module.create_config(csv_file, namespace.project_key, 
		namespace.DateFormats.get('jira'))

	# Write Final CSV for import
	if namespace.Flags['modified']:
		csv_file_size = os.path.getsize(csv_file)/1e+6
		if csv_file_size > 10.0:  # File will be too large to import as single file.
			cli.output_message('info', 'CSV is >10mb, CSV will need to be '
				'split into chunks less than 10mb to import. Import by '
				'heirarchy (i.e. Capability > Epic > Story)')
			io_module.write_csv(csv_data, csv_file)
			# io_module.split_csv(csv_data, csv_file)
			# io_module.write_csv(csv_data, csv_file, 'Epics')
			# io_module.write_csv(csv_data, csv_file, 'NoEpics')
		else:
		# 	if cli.ask_yes_no('Would you like to separate Epics into their '
		# 		'own file? (Y/N): '):
		# 		io_module.write_csv(csv_data, csv_file, True)
		# 	else:
			io_module.write_csv(csv_data, csv_file)

	# Perform CSV import to Jira at this time
	print(f'\nPlease import {csv_file} before continuing. If using server-side '
		'upload for attachments, please make sure attachments are uploaded to '
		'the correct location. When the import is complete, run this script, '
		'selecting the post-import operation to update sprint statuses and '
		'upload attachments if using direct upload. (Note: original uploader '
		'and date are lost during direct upload).\n')