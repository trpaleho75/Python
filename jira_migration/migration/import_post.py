#!/usr/bin/env python
# Coding = UTF-8

"""
	This module will contain functions exclusive to the post-import functionality.
"""

# Imports - built in
from http import HTTPStatus
import logging
import os
from types import SimpleNamespace

# Imports - Local
from migration import cli, core, io_module, web


# Logging
log = logging.getLogger(__name__)


def import_post(namespace: SimpleNamespace):
	"""
	Perform steps after CSV data has been imported.
	"""

	log.info('\nPost-Import Started')

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
	datetime_format_sprint_tz = namespace.DateFormats.get('sprint_tz')
	datetime_columns_simple = namespace.SimpleColumns.get('datetime')
	columns_compound = namespace.CompoundColumns.get('columns')
	column_exclusions = namespace.ColumnExclusions.get('columns')
	checklist_exclusions = namespace.ChecklistExclusions
	rest_endpoint_checklists = \
		namespace.CustomRESTEndpoints.get('checklist_import')

	# Get csv file and validate path
	csv_file = ''
	while not os.path.exists(csv_file):
		print('Select your CSV file: ', end = '')
		csv_file = io_module.get_filename('Select your CSV file', 
			[['CSV files', '*.csv']])
		print(csv_file)

	# Read CSV and remove empty columns
	csv_data = io_module.read_csv(csv_file)
	resulting_dataset = core.remove_empty_columns(csv_data)
	if resulting_dataset[1] is True:
		csv_data = resulting_dataset[0]
		namespace.Flags['modified'] = True

	# Get project
	cli.output_message('info', '\nChecking project key')
	namespace.__setattr__('project_key', 
		core.get_project_key(csv_data, namespace))
	cli.output_message('info', f'\nFound project key: {namespace.project_key}')

	# Verify project exists
	project_exists = False
	cli.output_message('INFO', '\nValidating project.')
	if not web.project_exists(session, base_url, namespace.project_key, HTTPStatus.OK, 
		retries, timeout):
		cli.output_message('WARNING', f'Project {namespace.project_key} not found. Not '
			'all features will work.')
	else:
		cli.output_message('INFO', f'{namespace.project_key} project found.')
		project_exists = True

	# Import Checklists
	if cli.ask_yes_no('Would you like to import checklist items? (Y/N): '):
		json_file = ''
		while not os.path.exists(json_file):
			print('Select the checklist json export file: ', end = '')
			json_file = io_module.get_filename('Select the checklist json '
				'export file', [['JSON files', '*.json']])
			print(json_file)

		web.import_checklists(session, base_url, rest_endpoint_checklists, 
			namespace.project_key, json_file, checklist_exclusions, retries, 
			timeout)

	# Update sprint status
	if project_exists:
		question = cli.ask_yes_no('Would you like to update sprint states '
			'(i.e. active or closed)? (Y/N): ')
		if question:
			cli.output_message('WARNING',
				'Please note: Sprint planning dates are imported along with '
				'the sprint. Sprint actual start and complete dates are only '
				'set by the "Start Sprint" and "Complete Sprint" buttons '
				'within the web interface. There is no facility to set or '
				'modify these dates via REST.')
			web.set_sprint_status(session, base_url, namespace.project_key, csv_file,
				datetime_format_sprint_tz, retries, timeout, page_step)
	else:
		cli.output_message(
			'WARNING',
			'Project {} not found. Unable to update sprints.'.format(namespace.project_key)
			)

	# Direct upload attachments (future integration)
	# Count attachments
	attachment_count = core.count_attachments(csv_data)
	if attachment_count > 0:
		if cli.ask_yes_no('Would you like to validate all attachments? (Y/N): '):
			cli.output_message(
				'INFO',
				'\nCSV contains references to {} attachment(s). Validating.'
				.format(attachment_count)
				)
			web.upload_attachments(session, base_url, csv_data, csv_file)

