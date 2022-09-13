#!/usr/bin/env python
# Coding = UTF-8

"""
	This module hold common functions used throughout this script.
"""

# Imports - Built-in
import base64
import concurrent.futures
from configparser import ConfigParser
import csv
from datetime import datetime
import functools
from getpass import getpass
from http import HTTPStatus
import json
import logging
from math import floor
import os
import random
from time import sleep
from types import SimpleNamespace
# Imports - 3rd Party
import requests
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
# Imports - Local
from timer import Timer


# Logging
log = logging.getLogger(__name__)


# Functions
#region Setup and Configuration
def get_config_ini(filename: str) -> ConfigParser:
	"""
	Import all config.ini data into namespace as dictionaries.
	i.e. namespace.[ini section] = {key:value, ...}

	Args:
		namespace(SimpleNamespace): Namespace to add configuration variables to.
		filename(str): Filename and path to configuration file.
	"""

	# Read config file
	config_object = ConfigParser(interpolation=None)
	if os.path.exists(filename):
		config_object.read(filename)
		return config_object
	else:
		message = f'Config file, /"{filename}/", not found! Unable to continue.'
		log.error(message)
		quit(message)


def set_config_ini(config_object: ConfigParser, filename: str):
	"""
	Update config.ini..

	Args:
		config_file: Configuration filename.
		config_object: ConfigParser object.
	"""

	# Write config.ini
	with open(filename, 'w') as file_object:
		config_object.write(file_object)


def config_to_namespace(namespace: SimpleNamespace, config_object: ConfigParser):
	"""
	Add configuration items to namespace.
	"""

	for section in config_object.sections():
		section_name = section.replace(' ','') # Remove all spaces
		section_dict = {}
		for key in config_object[section]:
			if '_list' in key:
				section_dict[key] = config_object[section][key].split()
				continue
			try: # Convert to int if able
				section_dict[key] = (config_object[section][key] if not config_object[section][key].isdigit()
					else int(config_object[section][key]))
			except:
				section_dict[key] = config_object[section][key]
		setattr(namespace, section_name, section_dict)
	
	# Flags to boolean values
	for flag in namespace.Flags:
		namespace.Flags[flag] = eval(namespace.Flags[flag])


def get_credentials(namespace: SimpleNamespace, username: str = '', passwd: str = '', pat: str = ''):
	"""
	Get credentials from user and store them in the provided namespace.
	Username and password will be used to create b64 credential used for
	basic auth to Jira.
	
	Args:
		namespace(SimpleNamespace): Namespace.
	"""

	if namespace.Flags.get('token'):
		if pat:
			namespace.token = pat
		else:
			namespace.token = input('Enter your Personal Access Token (PAT): ')
		return

	if username and passwd:
		namespace.username = username
		namespace.password = passwd
	else:
		namespace.username = input('Enter login: ')
		namespace.password = ''
		password_min_len = 8
		while len(namespace.password) < password_min_len:
			namespace.password = getpass()
			if len(namespace.password) < password_min_len:
				print(f'Password less than {password_min_len} characters, retry.')

	credentials_ascii = f"{namespace.username}:{namespace.password}".encode('ascii')
	b64_credentials = base64.b64encode(credentials_ascii)
	namespace.b64 = b64_credentials.decode('utf-8')


def connect_token(namespace: SimpleNamespace) -> SimpleNamespace:
	"""
	Create http session using the requests library. At this time, PAT authentication does not
	work with the secondary login required for elevated priviledge. Therefore, it cannot be used
	to perform import functions. You can use it for exporting data though.

	Args:
		personal_access_token(str): Jira personal_access_token(PAT).
		certificate(str): SSL verification certificate file or False

	Returns:
		(requests.Session): HTTP Session object.
	"""

	disable_warnings(InsecureRequestWarning)
	session = requests.Session()
	token = vars(namespace).get('token')
	headers = {
		"Accept": "application/json",
		"Authorization": f'Bearer {token}',
		"Content-Type": "application/json"
	}
	for header in headers:
		session.headers[header] = headers.get(header)
	session.verify = False
	adapter = requests.adapters.HTTPAdapter(
		pool_connections=namespace.TestParameters.get('max_users'),
		pool_maxsize=namespace.TestParameters.get('max_users')
	)
	session.mount('https://', adapter)
	namespace.session = session
	return namespace


def connect_http(namespace: SimpleNamespace):
	"""
	Create http session using the requests library.

	Args:
		certificate(str): SSL verification certificate file or False
		b64_credentials(str): Base 64 encoded username:password for basic auth.

	Returns:
		(requests.Session): HTTP Session object.
	"""

	disable_warnings(InsecureRequestWarning)
	session = requests.Session()
	username = vars(namespace).get('b64')
	headers = {
		"Accept": "application/json",
		"Authorization": f'Basic {username}',
		"Content-Type": "application/json"
		}
	for header in headers:
		session.headers[header] = headers.get(header)
	session.verify = False
	adapter = requests.adapters.HTTPAdapter(
		pool_connections=namespace.TestParameters.get('max_users'),
		pool_maxsize=namespace.TestParameters.get('max_users')
	)
	session.mount('https://', adapter)
	namespace.session = session


def get_user(namespace: SimpleNamespace):
	"""
	Get username from Jira
	"""

	url = f"{namespace.Server.get('url')}/rest/api/2/myself"
	response = namespace.session.get(url)
	if response.status_code != HTTPStatus.OK:
		log.error('Unable to retrieve user info: %s', response)
		return
	
	namespace.username = json.loads(response.text).get('name')
	while not namespace.username:
		namespace['username'] = input("Unable to retrieve username. Please enter your Jira username: ")
#endregion


def get_issue_types(namespace: SimpleNamespace) -> dict:
	"""
	Get all issue types so we can identify their id's.

	Args:
		namespace: Configuration data.
	
	Returns:
		dict: {name:id}
	"""

	url = f"{namespace.Server.get('url')}/rest/api/2/issuetype"
	response = namespace.session.get(url)
	if response.status_code != HTTPStatus.OK:
		log.error('Unable to retrieve list of Issue Types: %s', response)
		return
	
	response_json = json.loads(response.text)
	return {issue_type.get('name'):issue_type.get('id') for issue_type in response_json}


def get_fields(namespace: SimpleNamespace) -> dict:
	"""
	
	"""

	url = f"{namespace.Server.get('url')}/rest/api/2/field"
	response = namespace.session.get(url)
	if response.status_code == HTTPStatus.OK:
		return {field.get('name'):field.get('id') for field in json.loads(response.text)}
	else:
		message = f'Failed to retrieve field dictionary: {response.text}'
		log.error(message)
		return {}


def get_link_types(namespace: SimpleNamespace):
	"""
	Get all available link types.

	Args:
		namespace: Configuration data.
	
	Modifies:
		namespace: Adds "LinkTypes" argument and populates it with {name:id}.
	"""

	url = f"{namespace.Server.get('url')}/rest/api/2/issueLinkType"
	response = namespace.session.get(url)
	if response.status_code == HTTPStatus.OK:
		namespace.link_types = {link.get('name'):link.get('id') for link in json.loads(response.text).get('issueLinkTypes')}
	else:
		message = f"Unable to query link types: {response.text}"
		log.error(message)


def get_transitions(namespace: SimpleNamespace, issue_key: str) -> dict:
	"""
	Get available transitions from the current status.
	query (?expand=transitions.fields) returns required fields for transition
	if any.

	Args:

	Returns:
		dict: {name:id}
	"""

	url = f"{namespace.Server.get('url')}/rest/api/2/issue/{issue_key}/transitions"
	response = namespace.session.get(url)
	if response.status_code == HTTPStatus.OK:
		return {transition.get('name'):transition.get('id') for transition in json.loads(response.text).get('transitions')}
	else:
		message = f"Unable to query {issue_key}'s workflow transitions: {response.text}"
		log.error(message)


#region Random JQL Query
def jql_query(namespace: SimpleNamespace, query: str):
	"""
	Perform JQL query.

	Args:
		namespace: Configuration data.
		query: JQL query to execute.
	
	Returns:
		dict: JSON representation of search results.
	"""

	# Start timer
	timer = Timer()
	timer.start()

	# Pagination variables
	max_results = 50
	start_at = 0
	total = 0

	query_data = []
	while True:
		url = f"{namespace.Server.get('url')}/rest/api/2/search?jql={query}&maxResults={max_results}&startAt={start_at}"
		response = namespace.session.get(url)
		if response.status_code == HTTPStatus.OK:
			# Save page and set up next
			response_json = json.loads(response.text)
			for issue in response_json.get('issues'):
				query_data.append(issue)
			total = response_json.get('total')
			
			if total > start_at:
				start_at += max_results
				log.info(f"Query paginated: {query}")
			else: # End while
				log.info(f"Query complete: {query}")
				break
		else:
			message = f"Unable to execute query: {response.text}, {response.content}"
			log.error(message)
			break
	# Not interested in return data
	namespace.queries.append(timer.stop())


def select_random_query(namespace: SimpleNamespace) -> str:
	"""
	Perform a random JQL query from the available queries in configuration.

	Args:
		input_list: list of values.

	Returns:
		int: index of selected item.
	"""

	random_project = random.choice(namespace.Projects.get('key_list'))
	random_issue_type = random.choice(namespace.Projects.get('issue_types_list'))
	if not namespace.issue_statuses.get(random_project):
		namespace.issue_statuses[random_project] = get_issue_statuses(namespace, random_project)
	random_issue_type = random.choice(namespace.Projects.get('issue_types_list'))
	random_status = random.choice(namespace.issue_statuses[random_project].get(random_issue_type))

	replacement_dict = {
		'{project_list}': ', '.join(namespace.Projects.get('key_list')),
		'{project_key}': random_project,
		'{issue_status}': random_status,
		'{issue_type}': random_issue_type,
		'{username}': namespace.username
	}

	random_query = random.choice([query for query in namespace.JQL.keys()])
	query = replace_by_dict(namespace.JQL.get(random_query), replacement_dict)
	return query


def replace_by_dict(original_string: str, replacement_dict: dict) -> str:
	"""
	Perform all replacements in string from dictionary.

	Args:
		original_string: String to make replacements in.
		replacement_dict: dictionary of replacements {old:new, ...}
	
	returns:
		str: Updated string
	"""

	new_string = original_string
	for entry in replacement_dict:
		new_string = new_string.replace(entry, replacement_dict.get(entry))
	return new_string


def get_issue_statuses(namespace: SimpleNamespace, project_key: str):
	"""
	Get valid statuses for the given project.
	"""

	url = f"{namespace.Server.get('url')}/rest/api/2/project/{project_key}/statuses"
	response = namespace.session.get(url)
	if response.status_code == HTTPStatus.OK:
		response_json = json.loads(response.text)
		return {issue_type.get('name'):[status.get('name') for status in issue_type.get('statuses')] for issue_type in response_json}
	else:
		message = f"Unable to query {project_key}'s issue statuses: {response.text}"
		log.error(message)	


def randomize_query_execution(namespace: SimpleNamespace) -> int:
	"""
	Flip a coin, run a query.
	"""

	max_issues = namespace.TestParameters.get('max_issues')
	max_queries = namespace.TestParameters.get('max_queries')
	if max_issues > max_queries:
		bias_factor = round(max_issues / max_queries)
		eightball = [True]
		for _ in range(bias_factor - 1):
			eightball.append(False)
		return 1 if random.choice(eightball) else 0
	elif max_issues < max_queries:
		bias_factor = round(max_queries / max_issues)
		eightball = [False]
		for _ in range(bias_factor - 1):
			eightball.append(True)	
		return floor(bias_factor) if random.choice(eightball) else 0
	else:
		return 1
#endregion


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


def write_csv(dataset: dict):
	"""
	Write collected values to CSV.
	"""
	
	timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
	filename = f'load_test_metrics_{timestamp}.csv'
	with open(filename, 'w', newline='', encoding="UTF-8") as csv_file:
		csv_writer = csv.writer(csv_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
		# Determine array size
		max_cols = len(dataset)
		max_rows = 0
		for key in dataset.keys():
			if len(dataset.get(key)) > max_rows:
				max_rows = len(dataset.get(key))
		# Pre-poluate new array
		new_dataset = []
		for i in range(max_rows):
			new_dataset.append(['' for i in range(max_cols)])
		# Write dataset rows to columns
		col_counter = 0
		for value_list in [dataset.get(key) for key in dataset.keys()]:
			row_counter = 0
			for value in value_list:
				new_dataset[row_counter][col_counter] = value
				row_counter += 1
			col_counter += 1
		# Add header row
		new_dataset.insert(0, [key for key in dataset.keys()])
		# Write new dataset to file
		for row in new_dataset:
			csv_writer.writerow(row)

	file_path = os.path.join(os.getcwd(), filename)
	message = f'Finished writing: {os.path.normpath(file_path)}'
	log.info(message)


def elapsed_time(seconds: float) -> str:
	"""
	Calculate elapsed time since input_time.

	Args:
		seconds: elapsed seconds.

	Returns:
		(str): Elapsed time as string hours:minutes:seconds.
	"""

	hours = divmod(seconds, 3600)
	minutes = divmod(hours[1], 60)
	seconds = minutes[1]
	return f'{int(hours[0]):0>2}:{int(minutes[0]):0>2}:{int(seconds):0>2}'


def random_delay(namespace: SimpleNamespace) -> int:
	"""
	Radomize a delay (sleep) to better simulate user interaction.
	"""

	randomize_factor = round(namespace.TestParameters.get('user_delay_seconds') / 2)
	user_delay = namespace.TestParameters.get('user_delay_seconds') + \
		random.randint(-abs(randomize_factor), randomize_factor)
	return user_delay


def create_thread(namespace: SimpleNamespace, job):
	# Create issues and apply operations
	if job.__name__ == 'create_issue':
		job(namespace)
	elif job.__name__ == 'upload_attachment':
		sleep(random_delay(namespace))
		job(namespace)
	elif job.__name__ == 'transition_issue':
		sleep(random_delay(namespace))
		job(namespace)
	elif job.__name__ == 'add_comment':
		sleep(random_delay(namespace))
		job(namespace)
	elif job.__name__ == 'link_issue':
		sleep(random_delay(namespace))
		job(namespace)
	elif job.__name__ == 'jql_query':
		sleep(random_delay(namespace))
		job(namespace, select_random_query(namespace))
	elif job.__name__ == 'delete_issue':
		job(namespace)


def execute_threads(namespace: SimpleNamespace, jobs: list):
	max_threads = namespace.TestParameters.get('max_users')
	with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
		partial_function = functools.partial(create_thread, namespace)
		executor.map(partial_function, jobs)


def clean_existing(namespace: SimpleNamespace):
	"""
	remove any existing issues from target projects.
	"""

	# Pagination variables
	max_results = 50
	start_at = 0
	total = 0

	# Get any existing issues
	existing_issues = []
	target_projects = ', '.join(namespace.Projects.get('key_list'))
	query = f'project in ({target_projects})'
	while True:
		url = f"{namespace.Server.get('url')}/rest/api/2/search?jql={query}&fields=key&maxResults={max_results}&startAt={start_at}"
		response = namespace.session.get(url)
		if response.status_code == HTTPStatus.OK:
			# Save page and set up next
			response_json = json.loads(response.text)
			for issue in response_json.get('issues'):
				existing_issues.append(issue.get('key'))
			total = response_json.get('total')
			if total > start_at:
				start_at += max_results
			else: # End while
				break
		else:
			message = f"Unable to execute query: {response.text}"
			log.error(message)
			break

	if len(existing_issues) > 0:
		log.warn(f"Attempting to delete {len(existing_issues)} existing issues")

	issue_delete_status = []
	for issue in existing_issues:
		url = f"{namespace.Server.get('url')}/rest/api/2/issue/{issue}?Subtasks=true"
		response = namespace.session.delete(url)
		if response.status_code == HTTPStatus.NO_CONTENT:
			issue_delete_status.append(True)
		else:
			issue_delete_status.append(False)
	
	if all(issue_delete_status):
		log.info(f"All existing issues deleted")
	else:
		occurrence = {item: issue_delete_status.count(False) for item in issue_delete_status}
		log.info(f"Failed to delete {occurrence.get(False)} issue.")

	