#!/usr/bin/env python
# Coding = UTF-8

"""
	This module contains functions used to generically interact with the web.
"""


# Imports - built in
from http import HTTPStatus
import json
from json.decoder import JSONDecodeError
import logging
import os
from platform import platform
import re
import sys
import time
from tqdm import tqdm
from types import SimpleNamespace
from typing import Union
from urllib import parse as urlparse


# Imports - 3rd party
from dateutil.parser import parse
import requests
from urllib3 import disable_warnings, exceptions
from urllib3.exceptions import InsecureRequestWarning

# Imports - Local
from migration import cli, core, io_module


# Logging
log = logging.getLogger(__name__)


# Functions
def use_ssl(namespace: SimpleNamespace):
	"""
	Set certificate file if using SSL.
	"""

	# SSL verification var
	namespace.__setattr__('ssl_verify', False)

	# Get certificate file and validate that it exists, not that it is a valid cert.
	if not namespace.offline and namespace.SSL.get('enabled'):
		if 'https' in namespace.url:
			if os.path.exists(namespace.SSL.get('file')):
				namespace.ssl_verify = namespace.SSL.get('file')

	if not namespace.ssl_verify:
		disable_warnings(InsecureRequestWarning)
		if 'https' in vars(namespace).get('url'):
			cli.output_message('warning', 'Certificate not provided, SSL Verification disabled.')


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

	session = requests.Session()
	token = vars(namespace).get('token')
	headers = {
		"Accept": "application/json",
		"Authorization": f'Bearer {token}',
		"Content-Type": "application/json"
	}
	for header in headers:
		session.headers[header] = headers.get(header)
	session.verify = vars(namespace).get('ssl_verify')
	namespace.session = session
	return namespace


def connect_http(namespace: SimpleNamespace) -> SimpleNamespace:
	"""
	Create http session using the requests library.

	Args:
		certificate(str): SSL verification certificate file or False
		b64_credentials(str): Base 64 encoded username:password for basic auth.

	Returns:
		(requests.Session): HTTP Session object.
	"""

	session = requests.Session()
	username = vars(namespace).get('b64')
	headers = {
		"Accept": "application/json",
		"Authorization": f'Basic {username}',
		"Content-Type": "application/json"
		}
	for header in headers:
		session.headers[header] = headers.get(header)
	session.verify = vars(namespace).get('ssl_verify')
	namespace.session = session
	return namespace


def validate_and_authorize_url(namespace: SimpleNamespace) -> bool:
	"""
	Check URL for a Jira instance. This test verifies that the user can
	authenticate to the server.

	Args:
		username(str): Username to connect to server with.
			session(requests.Session): Session object contains user
				credentials for testing.
			url(str): Jira server URL.
			cert(str): Cert file for SSL verification.
			*pat(str): Personal Access Token.
			*username(str):
			*password(str):
			*b64(str):

	Returns:
		(bool): True if URL is accessible.
	"""

	log.info('Checking for Jira and testing credentials...')

	# Get namespace keys that may exist (vars(namespace) will return None if
	# the key doesn't exist, instead of an exception)
	url = vars(namespace).get('url')
	if not url:
		log.error('Unable to continue. No URL provided.')

	jira_version = None
	user_displayname = ''
	try:
		# Validate there is a Jira server at url. REST returns {dict}
		rest_path = f'{url}/rest/api/2/serverInfo'
		rest_response = rest_get(
			namespace.session,
			rest_path,
			HTTPStatus.OK,
			namespace.General.get('retries'),
			namespace.General.get('timeout')
			)
		if rest_response:
			jira_version = rest_response.get('version')

		# Get current user if using PAT. This validates the user,
		# but we'll do it again.
		if vars(namespace).get('token'):
			rest_path = f'{url}/rest/auth/latest/session'
			rest_response = rest_get(
				namespace.session,
				rest_path,
				HTTPStatus.OK,
				namespace.General.get('retries'),
				namespace.General.get('timeout')
				)
			if rest_response:
				namespace.username = rest_response['name']

		# Check if the provided user has permissions on the server
		# We'll do this by searching for the user in Jira. User search
		# cannot be performed anonymously so it's a fair check. Rest
		# returns {dict}
		if not vars(namespace).get('username'): # Can use dot notation for username after this
			log.error('Could not determine username. Please check username and retry.')

		rest_path = f'{url}/rest/api/2/user?username={namespace.username}'
		rest_response = rest_get(
			namespace.session,
			rest_path,
			HTTPStatus.OK,
			namespace.General.get('retries'),
			namespace.General.get('timeout')
			)
		if rest_response:
			user_displayname = rest_response.get('displayName')
	except ConnectionError as error_message:
		message = f'Cannot access {url}. Error = {error_message}'
		cli.output_message('error', message)

	# Return bool, values are stored in namespace.
	validated = all([jira_version, user_displayname])
	if validated:
		message = (f'{namespace.username}, authorized on {url}. '
			f'Jira version: {jira_version}.')
		cli.output_message('info', message)
	else:
		message = (f'{namespace.username} does not have access to {url}. '
			'Check credentials.')
		cli.output_message('error', message)
	return validated


def rest_get(session: requests.Session, url: str,
	expected_status: HTTPStatus, retries: int,
	timeout: int) ->Union[list, dict]:
	"""
	Perform a REST API call and return results. Paginate if necessary.

	Args:
		session(requests.Session): HTTP session object.
		url(str): URL of rest endpoint, (server url + rest endpoint).
		expected_status(http.HTTPStatus): Status code you are expecting
		from response.

	Returns:
		(Union[list, dict]): JSON data may come back as a list or dict.
	"""

	# Perform request
	retry = retries
	mark_time = time.time()
	http_response = None
	while retry > 0:
		try:
			http_response = session.get(url, timeout=timeout)
			if http_response.status_code == expected_status:
				break
			if (http_response.status_code == HTTPStatus.UNAUTHORIZED or
				http_response.status_code == HTTPStatus.FORBIDDEN):
				cli.output_message('error', 'Authentication failed')
				break
			if http_response.status_code == HTTPStatus.NOT_FOUND:
				log.warning(http_response.text)
				break
			if http_response.status_code == HTTPStatus.BAD_REQUEST:
				cli.output_message('warning', http_response.text)
				break
		except exceptions.ReadTimeoutError as error_message:
			log.error(f'HTTP Connection timeout. check query and retry. '
				f'{error_message}')
			retry -= 1
			break
		except requests.exceptions.ChunkedEncodingError as error_message:
			log.error(f'ChunkedEncodingError: {error_message}. Try Reducing'
				'step size')
			retry -= 1
			break
		except requests.exceptions.ConnectionError as error_message:
			log.error(f'ConnectionError: {error_message}.')
			break
		retry -= 1
	log.info('%s - Query completed. Elapsed time %s', url,
		core.elapsed_time(mark_time))

	if http_response == None:
		cli.output_message('error', f'No response from: {url}.')
		quit()

	# Interpret response
	data = {}
	if http_response.status_code == expected_status:
		try:
			data = json.loads(http_response.text)
		except JSONDecodeError as error_message:
			message = f'Error decoding JSON. Exiting script. {error_message}'
			log.error(message)
			quit(message)
	else:
		log.error('%s returned HTTP=%d. Aborting.', url,
			http_response.status_code)
	return data


def rest_post(session: requests.Session, rest_path: str, payload: dict,
	target_status: HTTPStatus) -> dict:
	"""
	Perform a REST API call via HTTP POST and return results.

	Args:
		session(requests.session):
		rest_path(str): Url and rest path for post.
		payload(dict): Dict of values to post.
		target_status(http.HTTPStatus): Expected status code.

	Returns:
		(dict): Data returned from post.
	"""

	response = None
	payload = json.dumps(payload)
	response = session.post(rest_path, payload)
	if response.status_code == target_status and response.text:
		response = json.loads(response.text)
	else:
		log.info(
			'%s returned HTTP = %d.',
			rest_path,
			response.status_code
			)
	return response


def rest_get_json(session: requests.Session, rest_path: str,
	expected_status: HTTPStatus, retries: int,
	timeout: int) -> requests.models.Response:
	"""
	Perform a REST API call and return results. Paginate if necessary.

	Args:
		session(requests.Session): HTTP session object.
		rest_path(str): URL of rest endpoint, (server url + rest endpoint).

	Returns:
		(Union[list, dict]): JSON data may come back as a list or dict.
	"""

	response = None
	retry = retries
	while retry > 0:
		mark_time = time.time()
		try:
			http_response = session.get(rest_path, timeout=timeout)
		except exceptions.ReadTimeoutError as exception_message:
			cli.output_message('error', f'HTTP Connection timeout. '
				f'{exception_message}')
			sys.exit()
		except BaseException as exception_message:
			cli.output_message('error', 'Error occurred during REST Get '
			f'operation: {exception_message}')
			sys.exit()
		log.info('%s - Query completed. %s', rest_path,
			core.elapsed_time(mark_time))

		status_code = http_response.status_code
		if status_code == expected_status:
			response = http_response
			break
		elif (status_code == HTTPStatus.UNAUTHORIZED or
				status_code == HTTPStatus.FORBIDDEN):
			# Do not retry on authentication failures. User may have
			# typo in password and may get locked out of their account if we
			# keep trying.
			log.error('%s returned HTTP=%d. Aborting.', rest_path, status_code)
			print("Server reports authentication error. Aborting.")
			exit()
		else:
			log.info('%s returned HTTP=%d. Retries remaining = %d',
				rest_path, status_code, retry)
			retry -= 1
	return response


def rest_delete(session: requests.Session, rest_path: str) -> bool:
	"""
	Perform a http delete.

	Args:
		session: Requests.Session object (Contains headers including authentication).
		rest_path(str): URL + REST path.

	Returns:
		(bool): True if delete was successful.
	"""

	http_result = session.delete(rest_path)
	if http_result.status_code == HTTPStatus.NO_CONTENT:
		return True
	else:
		log.error(f"{rest_path} returned {http_result.status_code}: {http_result.text}")
		return False


def project_exists(session: requests.Session, base_url: str, key: str,
	expected_status: HTTPStatus, retries: int, timeout: int) -> bool:
	"""
	This REST endpoint returns http status code 200 if the project exists.

	Args:
		session(requests.Session): HTTP connection session object.
		server(str): URL of Jira server.
		key(str): Jira project key to search for.

	Returns:
		(bool): True if project exists.
	"""

	validated = False
	rest_path = f'{base_url}/rest/api/2/project/{key}'
	response = rest_get(session, rest_path, expected_status, retries, timeout)
	if response.get('key') == key:
		validated = True
	return validated


def get_all_issues(session: requests.Session, base_url: str, key: str,
	directory: str,	file_dateformat: str, page_step: int = 250,
	retries: int = 3, timeout: int = 90, nap: int = 5) -> str:
	"""
	Get all issue in a project.

	Args:
		session(requests.Session): HTTP connection object.
		base_url(str): URL of Jira server.
		key(str): Project key.
		directory(str): Target directory for CSV output.
		page_step(int): Number of records to download per query.
		retries(int): Number of attempts to download data.
		timeout(int): Number of seconds to wait for downloads.

	Returns:
		(str): Path and filename of new CSV file.
	"""

	# Set up query for exporting CSVs
	jql_query = f'PROJECT={key} ORDER BY issuekey ASC'
	jql_query = jql_query.replace(' ', '%20')
	jql_query = jql_query.replace('=', '%3d')
	rest_path = (f'{base_url}/sr/jira.issueviews:searchrequest-csv-all-fields'
		f'/temp/SearchRequest.csv?jqlQuery={jql_query}')
	start = 0
	page_count = 0
	retry_count = 0
	while True:  # Yes this is an infinite loop if unbroken
		response = None
		# Get chunk
		paginate_jql = f'{rest_path}&tempMax={page_step}&pager/start={start}'
		cli.output_message('info', f'Retreiving issues (start={start}, '
			f'step={page_step})')
		mark = time.time()
		try:
			response = session.get(paginate_jql, timeout=timeout)
		except ConnectionError as error_message:
			# Try again
			retry_count += 1
			if retry_count < retries:
				cli.output_message('warning', "Connection error: retrying.")
				time.sleep(nap)
				continue
			else:
				cli.output_message('error', 'Connection error: No more '
					'retries. Quitting.')
				quit(error_message)
		except:
			message = (f'{get_all_issues.__name__} - HTTP Connection timeout. '
				'Try smaller step size.')
			cli.output_message('error', message)
		cli.output_message('info', f'Query completed.'
			f'{core.elapsed_time(mark)}')
		
		# Status check
		if response is None:
			cli.output_message('error', f'No data returned from '
				f'{get_all_issues.__name__}')
			quit()

		# Write chunk
		if response.status_code == HTTPStatus.OK and response.text:
			output_filename = f'{key}_{page_count}.csv'
			path = os.path.join(directory, output_filename)
			with open(path, 'w', encoding="UTF-8") as output_file:
				output_file.write(response.text)
				output_file.close()
			cli.output_message('info', f'Finished writing: {path}\n')
		else:
			message = ('Response was empty. Verify project exists and you '
				'have access.')
			cli.output_message('warning', message)
			quit()
		# Read chunk and add to array
		page = io_module.read_csv(path)
		# +1 header row is always present if data is returned
		if len(page) < page_step + 1:
			# No more pages
			break
		else:
			# Set up next page
			page_count += 1
			start += page_step

	# Merge csv files
	merged_filename = io_module.merge_csv(directory, key, file_dateformat)
	merged_filename = os.path.join(directory, merged_filename)

	# Remove temp csv files
	file_list = os.listdir(directory)
	search_string = '^{}_[0-9]*.csv'.format(key)
	for file in file_list:
		if re.search(search_string, file):
			os.remove(os.path.join(directory, file))

	return merged_filename


def get_all_issues_online(session: requests.Session, base_url: str, key: str, 
	retries: int, timeout: int, step: int) -> list:
	"""
	Get all issues. The output of the REST search query is paginated. The page size
	can be configured using the PAGINATED_STEP constant at the top of this script.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(list): List of results
	"""

	cli.output_message('INFO', 'Getting all issues from project.')
	start = 0
	issue_list = []
	progress_bar = tqdm(desc='Retreiving issues', total=step)
	while True:  # Yes this is an infinite loop if unbroken
		# Build query string
		jql_query = '?jql=PROJECT={} ORDER BY issuekey ASC&fields=key'.format(key)
		jql_query = jql_query.replace(' ', '%20')
		pagination_string = '&startAt={}&maxResults={}'.format(str(start), str(step))
		rest_path = '{}/rest/api/2/search{}{}'.format(base_url, jql_query, pagination_string)
		try:
			response = rest_get(session, rest_path, HTTPStatus.OK, 
				retries, timeout)
			# Get total and update progress bar max
			response_total = response.get('total')
			if response_total is not None and response_total != progress_bar.total:
				progress_bar.total = response_total
			# Add results to list
			issues = response.get('issues')  # List of issues without metadata
			issue_count = 0
			if issues:
				for issue in issues:
					issue_list.append(issue)
					progress_bar.update()
				issue_count = len(response.get('issues'))
			# Paginate or bust
			if issue_count == step:
				start += step
			elif issue_count < step:
				break
		except exceptions.ReadTimeoutError:
			cli.output_message(
				'ERROR',
				'{} - HTTP Connection timeout. Try smaller step size.'
				.format(get_all_issues.__name__)
				)
	progress_bar.close()
	return issue_list


def get_issue(session: requests.Session, base_url: str, issue_key: str, 
	fields: list = [], retries: int = 3, timeout: int = 90) -> dict:
	"""
	Get a single Jira issue using the REST endpoint:
		/rest/api/2/issue/{issueIdOrKey}

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira issue key.

	Returns:
		(dict): Returns a full representation of the issue for the given
		issue key
	"""

	fields_param = ('?fields=' + ','.join(fields)) if fields else ''
	rest_path = f'{base_url}/rest/api/2/issue/{issue_key}{fields_param}'
	response = rest_get(session, rest_path, HTTPStatus.OK, retries,
		timeout)
	return response


def split_compound_online(namespace: SimpleNamespace, key: str,
	field_value: str, field_name: str, dataset: list) -> dict:
	"""
	Split compound field value into dictionary of individual values.
	Individual values are separated by semicolons, but sometimes a field 
	contains semicolons which cause improper splitting of the field. If 
	field splits into more than the expected number of values, user 
	assistance will be requested. Will skip "last" fields since they cannot
	be imported.

	Args:
		field_value (str): Raw data from cvs cell.
		field_name (str): Name of column to identify expected value by field
			schema.
		dataset (list): Full dataset for updating records based on manual
			split. Will replace semicolons with the equivalent hex character
			code (';' = %03b).

	Returns:
		(dict): dictionary of values contained in the field.
	"""

	values = {}
	if field_name in namespace.ColumnExclusions.get('columns'):
		values = {}  # Do not process.
	elif field_name in ['Attachment', 'Comment', 'Log Work']:
		schema_name = field_name.replace(' ','').lower()
		schema = namespace.Schemas.get(schema_name)
		split_field = field_value.split(';')
		while len(split_field) != len(schema):
			split_field = _auto_data_split_online(namespace, key, field_value,
				field_name, dataset, schema)
		else:
			for field in schema:
				field_value = split_field[schema.index(field)]
				if core.validate_value(field, field_value):
					values[field] = field_value
	return values


def _auto_data_split_online(namespace: SimpleNamespace, key: str,
	field_value: str, field_type: str, csv_data: list, schema: list) -> list:
	"""
	Automatically split compound fields. Compound fields are semicolon 
	delimited, but if a user uses semicolons in their comments the field
	will not split correctly and the import will fail. This function
	attempts to identify extraneous semicolons and replace them with their hex
	equivalent so import can be performed.

	Args:
		field_value(str): Value of compound field.
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
	location = core.get_field_location(key, csv_data, field_value)

	# If a compound field is missing fields
	if len(field_value.split(delimiter)) < len(schema):
		log.warning('%s: Invalid input at row:col = %d:%d, (%s should have %d'
			' values = %s): %s',
			key,
			location.get('row') + 1,
			location.get('col'),
			field_type,
			len(schema),
			';'.join(schema),
			field_value
		)

		# Get issue data from Jira for reference
		issue = get_issue(namespace.session, namespace.url, key, [],
			namespace.General.get('retries'), namespace.General.get('timeout'))

		# Attempt to correct missing data
		new_values = None  # List of correct values matching schema
		split_values = field_value.split(';', maxsplit=len(schema))
		if field_type.lower() == 'attachment':
			online_attachments = issue.get('fields').get('attachment')
			online_values = ['' for field in schema]
			for attachment in online_attachments:
				csv_attachment_location = split_values[-1]
				if attachment.get('content') == csv_attachment_location:
					online_values[schema.index('datetime')] = attachment.get('created')
					online_values[schema.index('username')] = 'Unknown' if not attachment.get(
						'author') else attachment.get('author').get('key')
					online_values[schema.index('filename')] = attachment.get('filename')
					online_values[schema.index('location')] = attachment.get('content')
			new_values = online_values
		elif field_type.lower() == 'comment':
			online_comments = issue.get('fields').get('comment').get('comments')
			online_values = ['' for field in schema]
			for comment in online_comments:
				csv_time = parse(comment.get('created'), fuzzy=False).strftime('%d/%b/%Y %H:%M')
				online_time = parse(split_values[schema.index('datetime')], fuzzy=False).strftime('%d/%b/%Y %H:%M')
				if online_time == csv_time:
					online_values[schema.index('datetime')] = comment.get('created')
					online_values[schema.index('username')] = 'Unknown' if not comment.get(
						'author') else comment.get('author').get('key')
					online_values[schema.index('comment')] = comment.get('body')
			new_values = online_values
		else:  # User input required for unhandled cases and worklog entries
			print('\n{}'.format(field_value))
			field_value = input('Fix the above string (copy and paste here): ')
			parse_input = field_value.split(';', maxsplit=len(schema))
			if len(parse_input) == len(schema):
				new_values = parse_input

		# update existing data
		if new_values:
			field_value = ';'.join(new_values)
			csv_data[location.get('row')][location.get('col')] = field_value
			log.info(
				'%s: Input modified at %d:%d = %s',
				key,
				location.get('row') + 1,
				location.get('col'),
				field_value
			)
		return new_values
	elif len(field_value.split(delimiter)) == len(schema):
		return field_value.split(delimiter)
	else:  # Too many fields
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
								cli.output_message(
									'ERROR',
									'Invalid data at {} = {}'
									.format(
										location,
										field_value
									)
								)
						else:  # Next piece is not the right type = bad split
							working_string = working_string.replace(delimiter, hex_delimiter, 1)
					else:  # This is the last schema field
						# Last field remove trailing delimiters
						working_string = working_string.replace(delimiter, '', 1)
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
			namespace.Flags['modified'] = True
			log.info(
				'%s: Input modified at %d:%d = %s',
				key,
				location.get('row') + 1,
				location.get('col'),
				field_value
			)
		return dataset


def get_project_components(session: requests.Session, base_url: str, key: str, 
	retries: int, timeout: int) -> list:
	"""
	Get all components in a project via the REST API.

	Args:
		session(requests.Session): HTTP session object.
		server(str): URL of Jira server.
		key(str): Jira project key to get versions for.

	Returns:
		(list): Component information from Jira
	"""

	component_list = []
	rest_path = f'{base_url}/rest/api/2/project/{key}/components'
	try:
		component_list = rest_get(session, rest_path, HTTPStatus.OK, retries, timeout)
	except exceptions.ReadTimeoutError:
		cli.output_message(
			'error',
			f'{get_project_components.__name__} - HTTP Connection timeout. check query and retry'
		)
	return component_list


def get_boards(session: requests.Session, base_url: str, key: str,
	retries: int, timeout: int) -> list:
	"""
	Get all boards in the target project that the user has access to.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(list): [{id:'', 'self':'', 'name':'', 'type':''}, ...]
	"""

	boards = []
	last_page = False
	start_at = 0
	max_results = 50
	cli.output_message('INFO', 'Retrieving board list')
	while not last_page:
		rest_path = (f'{base_url}/rest/agile/1.0/board?projectKeyOrId={key}'
		f'&startAt={start_at}&maxResults={max_results}')
		results = rest_get(session, rest_path, HTTPStatus.OK, retries,
			timeout)
		if not len(results) > 0:
			break  # No boards found
		if len(results.get('values')) == 0:
			break
	   # Set up url for next page if exists
		if not results.get('isLast') is None:  # In case there were no boards returned
			if not results.get('isLast'):
				start_at += max_results
			else:
				last_page = True
		# Add page to results
		for board in results['values']:
			boards.append(board)
	return boards


def get_board_configs(session: requests.Session, server: str, board_list: list,
	retries: int, timeout: int) -> list:
	"""
	Get configuration data for each board in the list. Board configs contain more info that
	the board list itself.

	Args:
		session(requests.Session): HTTP connection session object.
		server(str): URL of Jira server.
		board_list(list): List of boards to get configs for. Board Id is the relevant field.

	Returns:
		(list): List of board configs.
	"""

	data = []
	for this_board in board_list:
		board_id = this_board.get('id')
		rest_path = f'{server}/rest/agile/1.0/board/{board_id}/configuration'
		results = rest_get(session, rest_path, HTTPStatus.OK, retries,
			timeout)
		data.append(results)
	return data


def get_filters(session: requests.Session, server: str, filter_list: list,
	retries: int, timeout: int) -> list:
	"""
	Get filter data for each filter pulled from the board config.

	Args:
		session(requests.Session): HTTP connection session object.
		server(str): URL of Jira server.
		filter_ids(list): List of filter ids.

	Returns:
		(list): List of filter configurations.
	"""

	all_filters = []
	for filter_id in filter_list:
		rest_path = f'{server}/rest/api/2/filter/{filter_id}'
		result = rest_get(session, rest_path, HTTPStatus.OK, retries, 
			timeout)
		if result not in all_filters:
			all_filters.append(result)
	return all_filters


def display_sprints(session: requests.Session, base_url: str, boards: list, 
	key: str, retries: int, timeout: int, page_step: int):
	"""
	Get user to select a project board. Sprints are queried and the number
	of sprints in each board is displayed in the table.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		boards(list): List of scrum/kanban boards found in project.
		key(str): Jira project key.
	"""

	table_title = '{} Project Boards'.format(key)
	table_columns = ['#', 'Name', 'Id', 'type', 'Sprints']
	table_dataset = []
	board_menu_num = 1
	# For each board get info then get sprints
	for board in boards:
		board_name = board.get('name')
		board_id = board.get('id')
		board_type = board.get('type')
		# Get sprints if scrum board, if kanban the sprints will be empty.
		sprints = []
		if board_type == 'scrum':
			sprints = get_sprints_from_board_id(session, base_url, board_id, 
				retries, timeout, page_step)
		# Add record to dataset
		table_dataset.append([board_menu_num, board_name, board_id, 
			board_type, len(sprints)])
		board_menu_num += 1
	# Display table
	cli.print_table(table_title, table_columns, table_dataset)


def get_sprints_from_board_id(session: requests.Session, base_url: str, 
	board_id: int, retries: int, timeout: int, page_step: int) -> list:
	"""
	Get all sprints associated with a given board id. This rest path
	returns a dictionary.

	Args:
		session: Requests.Session object (Contains headers including authentication).
		base_url: URL of Jira server..
		board_id: Jira id number of board.

	Returns:
		(list): [{name:{id, self, state, startDate, endDate, originBoardId, goal}}]
	"""

	sprints = []
	last_page = False
	start_at = 0

	while not last_page:
		rest_path = (f'{base_url}/rest/agile/1.0/board/{board_id}/sprint/?'
			f'startAt={start_at}&maxResults={page_step}')
		results = rest_get(session, rest_path, HTTPStatus.OK, retries, 
			timeout)

		# Exit loop if no results
		if not results.get('values') or len(results.get('values')) == 0:
			break

		# Add page to results
		for sprint in results['values']:
			sprints.append(sprint)
		
		# If there is a next page, set query parameters.
		if not results.get('isLast'):
			last_page = True
		else:
			start_at += page_step
	return sprints


def get_sprints_from_board_list(session: requests.Session, base_url: str, 
	board_list: list, retries: int, timeout: int, page_step: int) -> list:
	"""
	Get all sprints. To get sprints you have to get all the boards in the project. Then,
	search each board for all the sprints on the board. Since a sprint may exist on more
	than one board you have to get a unique set of sprints. Once you have the unique set
	you can build the list of actual sprints associated with the project.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		board_list(list): list of all boards in project

	Returns:
		(list): List of results
	"""

	unique_sprints = []

	cli.output_message('info', 'Getting all sprints from project.')
	try:
		board_ids = [board.get('id') for board in board_list if 
			board.get('type') == 'scrum']
	except AttributeError as exception_message:
		cli.output_message('error', exception_message)
		return unique_sprints

	all_sprints = []
	for id in board_ids:
		sprints = get_sprints_from_board_id(session, base_url, id, retries, 
			timeout, page_step)
		if len(sprints) > 0:
			all_sprints += sprints

	all_sprint_ids = [sprint.get('id') for sprint in all_sprints]
	unique_sprint_ids = set(all_sprint_ids)
	for id in unique_sprint_ids:
		for sprint in all_sprints:
			if sprint.get('id') == id:
				unique_sprints.append(sprint)
				break
	return unique_sprints


def get_version_info(session: requests.Session, base_url: str, key: str, 
	retries: int, timeout: int) -> list:
	"""
	Get all versions in a project via the REST API.

	Args:
		session(requests.Session): Jira session object.
		server(str): URL of Jira server.
		key(str): Jira project key to get versions for.

	Returns:
		(list): Version information from Jira
	"""

	version_list = []
	rest_path = f'{base_url}/rest/api/2/project/{key}/versions'
	result = rest_get(session, rest_path, HTTPStatus.OK, retries, timeout)
	if len(result) > 0:
		version_list = result
	return version_list


def export_checklists(session: requests.Session, base_url: str, 
	output_filename: str, key: str, page_step: int, retries: int, 
	timeout: int):
	"""

	"""

	# Output variable
	checklist_data = []

	# Checklist custom field type
	field_type_string = 'com.okapya.jira.checklist:checklist'

	# Get field list and search for checklists
	fields = get_fields(session, base_url, retries, timeout)
	fields_custom = [field for field in fields if field.get('custom') is True]
	fields_custom_w_schema = [field for field in fields_custom if 
		field.get('schema') is not None]
	fields_checklists = [field for field in fields_custom_w_schema if
		field.get('schema').get('custom') == field_type_string]

	# Short circuit if there aren't any checklist fields.
	if len(fields_checklists) == 0:
		cli.output_message('INFO', 'No checklists detected. Continuing...\n')
		return

	# Get issue id list {key:{fields:{field_id:[{rank:{name, checked, mandatory, id, rank}},...]}}}
	issues = get_issue_ids(session, base_url, key, page_step, retries, timeout)
	issue_key_list = [issue.get('key') for issue in issues]
	checklist_field_ids = [field.get('id') for field in fields_checklists]
	checklist_data = {}
	for issue in tqdm(issue_key_list, desc='Scanning issues'):
		issue_dict = {}
		issue_details = get_issue(session, base_url, issue, 
			checklist_field_ids, retries, timeout)
		# Get field list
		issue_details_fields = issue_details.get('fields')
		for field in issue_details_fields:
			if issue_details_fields[field]:
				issue_dict[field] = issue_details_fields[field]
		checklist_data[issue] = issue_dict
	# Output checklist data
	checklist_json = json.dumps(checklist_data)
	io_module.write_file(checklist_json, output_filename)


def get_fields(session: requests.Session, base_url: str, retries: int, 
	timeout: int) -> list:
	"""
	Get all Jira fields for mapping field names to id.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.

	Returns:
		(list): List of dictionaries representing all fields, both System and Custom.
			[{id:'', name:'', ...}, ...]
	"""

	rest_path = '{}/rest/api/2/field'.format(base_url)
	http_response = rest_get(session, rest_path, HTTPStatus.OK, retries, 
		timeout)
	return http_response


def get_issue_ids(session: requests.Session, base_url: str, key: str, 
	page_step: int, retries: int, timeout: int) -> list:
	"""
	Get all issues. The output of the REST search query is paginated. The page size
	can be configured using the PAGE_STEP constant at the top of this script.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(list): List of results
	"""

	cli.output_message('INFO', 'Getting all issues from project.')
	start = 0
	issue_list = []
	progress_bar = tqdm(desc='Retreiving issues', total=page_step)
	while True:  # Yes this is an infinite loop if unbroken
		# Build query string
		jql_query = '?jql=PROJECT={} ORDER BY issuekey ASC&fields=key'.format(key)
		jql_query = jql_query.replace(' ', '%20')
		pagination_string = '&startAt={}&maxResults={}'\
			.format(str(start), str(page_step))
		rest_path = (f'{base_url}/rest/api/2/search{jql_query}'
			f'{pagination_string}')
		try:
			response = rest_get(session, rest_path, HTTPStatus.OK, 
				retries, timeout)
			# Get total and update progress bar max
			response_total = response.get('total')
			if (response_total is not None and response_total > 
				progress_bar.total):
				progress_bar.total = response_total
			# Add results to list
			issues = response.get('issues')  # List of issues without metadata
			if issues:
				for issue in issues:
					issue_list.append(issue)
					progress_bar.update()
			issue_count = len(response.get('issues'))
			# Paginate or bust
			if issue_count == page_step:
				start += page_step
			elif issue_count < page_step:
				break
		except exceptions.ReadTimeoutError:
			cli.output_message(
				'ERROR',
				'{} - HTTP Connection timeout. Try smaller step size.'
				.format(get_all_issues.__name__)
			)
	progress_bar.close()
	return issue_list


def export_screens(session: requests.Session, base_url: str, 
	rest_endpoint: str, key: str, filename: str, retries: int, timeout: int):
	"""
	Call scriptrunner custom REST endpoint for screen export. Get data for the
		given project and write the JSON to a file.

	Test URL: https://jira-sdteob.web.boeing.com/rest/scriptrunner/latest/custom/screens?key=AGA

	Args:
		session(requests.Session):
		base_url(str):
		key(str):
	"""

	query = '?key={}'.format(key)
	rest_path = '{}{}{}'.format(base_url, rest_endpoint, query)
	http_response = rest_get_json(session, rest_path, HTTPStatus.OK, retries, timeout)

	# Write screens to file
	if http_response:
		io_module.write_file(http_response.text, filename)


def direct_download(session: requests.Session, base_url: str, 
	attachment_dict: dict, csv_file: str, key: str, retries: int, 
	timeout: int):
	"""
	Download attachments from Jira.

	Args:

	Returns:

	"""
	# Get the current working directory (for use later)
	owd = os.getcwd()

	# get attachment directory
	target_path = os.path.dirname(csv_file)
	target_path = '{}/{}'.format(target_path, key)

	success_count = 0
	for attachment in tqdm(attachment_dict, desc='Downloading attachments'):
		attachment_filename = attachment_dict.get(attachment).get('filename')
		attachment_issue_key = attachment_dict.get(attachment).get('key')
		# Splitting the attachment at base_url leaves only the attachment path,
		# the front is empty
		attachment_path = attachment.split(base_url)[1]
		if not attachment_path:
			log.error('Invalid path split attempting to process \"%s\". '
				'Skipping attachment', attachment_dict.get(attachment))
			continue
		new_path = '{}{}'.format(target_path, attachment_path)
		new_path = os.path.dirname(new_path)
		if not os.path.exists(new_path):
			os.makedirs(new_path)
		# Prepare target location and filename
		os.chdir(new_path)
		new_file = '{}/{}'.format(new_path, attachment_filename)
		# Get attachment content
		http_response = rest_get_json(session, attachment, HTTPStatus.OK, 
			retries, timeout)
		if not http_response:
			cli.output_message('error', f'Error downloading attachment from '
				f'{attachment_issue_key} = {attachment_filename}')
			continue
		attachment_data = http_response.content
		# Save content to file
		with open(attachment_filename, 'wb') as content:
			content.write(attachment_data)
		# Verify write
		if os.path.exists(attachment_filename):
			log.info(
				'Downloaded \"%s\", from %s, to \"%s\".',
				attachment_filename, attachment, new_file
			)
			success_count += 1
	os.chdir(owd)
	cli.output_message('info', f'Downloaded({success_count}/'
		f'{len(attachment_dict)}) files to \"{target_path}\".')


def create_gaia_project(namespace: SimpleNamespace, session: requests.Session, 
	base_url: str, key: str) -> bool:
	"""
	Create a project using the Gaia plugin for Jira.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(bool): True if project created successfully.
	"""

	# Choose Gaia template
	project_template = get_gaia_tempate(namespace, session, base_url)
	# Get required info for the POST payload
	new_project_name = input('Enter the new project\'s Name: ')
	cli.output_message('INFO', 'Select a project lead')
	project_lead = get_jira_user(namespace, session, base_url)
	project_type = 'software'
	# Build payload
	payload = {
		'templateName': project_template,
		'newProjectName': new_project_name,
		'newProjectKey': key,
		'projectLead': project_lead,
		'projectType': project_type,
		'copySchemes': True
	}
	rest_path = f'{base_url}/plugins/servlet/gaia/rest/project'
	project_created = rest_post(session, rest_path, payload, 
		HTTPStatus.OK)
	if project_created:
		cli.output_message('INFO', '{}({}) created.'.format(new_project_name, key))
	return project_created


def get_gaia_tempate(namespace: SimpleNamespace, session: requests.Session, 
	base_url: str) -> str:
	"""
	Get all Gaia templates, display table of results, get user to pick one.

	Args:

	Returns:
	"""

	rest_path = f'{base_url}/plugins/servlet/gaia/rest/project'
	# results = rest_get(session, rest_path, HTTPStatus.Ok, 
	# 	namespace.General.get('retries'), namespace.General.get('timeout'))
	results = session.get(rest_path)
	if results.status_code != HTTPStatus.OK:
		cli.output_message('Error', f'Invalid response from request: {results.text}')
		sys.exit()
	results_json = json.loads(results.text)
	results_array = [result for result in results_json if result.get('isEnabled') == True]
	templates = []
	user_selection = None
	if len(results_array) > 0:
		# Create list of templates
		row = 1
		for template in results_array:
			templates.append([row, template.get('templateName')])
			row += 1
		cli.print_table('Gaia Templates', ['Id', 'Template Name'], templates)
		# Select a template
		while True:
			user_selection = int(input('Select a Template Id: '))
			if user_selection in [row[0] for row in templates]:
				break
		template_name_index = 1
		selected_template_name = templates[user_selection - 1][template_name_index]
	return selected_template_name


def get_jira_user(namespace: SimpleNamespace, session: requests.Session, 
	base_url: str) -> str:
	"""
	Search Jira for a user.

	Args:

	Returns:

	"""

	user_selection = None
	while user_selection is None:
		user_list = []
		search_string = input('Enter name, email, or username to search for: ')
		rest_path = (f'{base_url}/rest/api/2/user/search?username='
			f'{search_string}')
		# results = rest_get(session, rest_path, HTTPStatus.Ok, 
		# 	namespace.General.get('retries'), namespace.General.get('timeout'))
		results = session.get(rest_path)
		if results.status_code != HTTPStatus.OK:
			cli.output_message('Error', f'Invalid response from request: {results.text}')
			sys.exit()
		results = json.loads(results.text)
		result_count = len(results)
		# Build list of users for display
		if result_count > 0:
			count = 1
			for result in results:
				username = result.get('name')
				display_name = result.get('displayName')
				email = result.get('emailAddress')
				user_list.append([count, display_name, username, email])
				count += 1
			# Display list
			cli.print_table('User Query Results', 
				['#', 'Name', 'Username', 'Email Address'], user_list)
			user_input = ''
			while user_input == '':
				# Get and validate user input
				user_input = input('Enter number of user or \'0\' to search '
					'again: ')
				user_input_int = int(user_input) - 1
				if user_input_int == -1:
					break
				else:
					if user_input_int in range(result_count):
						user_list_username_index = 2
						user_selection = (user_list[user_input_int]
							[user_list_username_index])
					else:
						cli.output_message('warning', 
							f'Invalid Input: {user_input}')
						user_input = ''
						continue
		else:
			print('No user matched search string. Please try again.')
	return user_selection


def create_custom_field(session: requests.Session, base_url: str, 
	field_record: list) -> str:
	"""
	Create necessary custom field and return it's field record.
	field_record = ['id', 'name', 'custom', 'orderable', 'navigable', 'searchable', 'clauseNames', 'schema']
	"""

	rest_path = '{}/rest/api/2/field'.format(base_url)
	field_name = field_record[1]
	field_schema = json.loads(field_record[-1].replace("'", '"'))
	field_type = field_schema.get('custom')
	payload = {'name':field_name, 'type':field_type}
	result = rest_post(session, rest_path, payload, HTTPStatus.CREATED)
	return result.get('id')


def get_project_roles(session: requests.Session, base_url: str, key: str, 
	http_status: HTTPStatus, retries: int, timeout: int) -> list:
	"""
	Get all project roles.

	Returns:
		(list): List of dictionary entries:
			[{self:str, name:str, id:int, description:str, actors:[str, ...]}, ...]
	"""

	roles = []
	rest_path = f'{base_url}/rest/api/2/project/{key}/role'
	results = rest_get(session, rest_path, http_status, retries, timeout)
	progress_bar_desc = 'Getting {} project role details'.format(key)
	for url in tqdm(results.values(), desc=progress_bar_desc):
		details = rest_get(session, url, HTTPStatus.OK, retries, timeout)
		roles.append(details)
	return roles


def validate_permissions(session: requests.Session, base_url: str, key: str, 
	username: str, retries: int, timeout: int) -> bool:
	"""
	Check permission to make sure user has sufficient permission to execute script.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.
		username(str): Username to validate.

	Returns:
		(bool): True if user has admin rights on the given project.
	"""

	permissions_list = ['PROJECT_ADMIN', 'MOVE_ISSUE', 'DELETE_ISSUE', 'CLOSE_ISSUE', 'BROWSE']
	query = f"permissions={','.join(permissions_list)}&projectKey={key}&username={username}"
	url = f"{base_url}/rest/api/2/user/permission/search?{query}"
	response = rest_get(session, url, HTTPStatus.OK, retries, timeout)
	if response:
		return True
	return False


def set_user_roles(session: requests.Session, base_url: str, key:str, 
	project_roles: list, username: str, retries: int, timeout: int) -> list:
	"""
	Set basic permissions for the user running the script.

	Categories = 'atlassian-user-role-actor'

	Args:


	Returns:
		(list): True if role was added.
	"""

	results = []

	user_role = 'user'
	# Admin project roles
	admin_roles = [
		'Administrator',
		'Issue Closer',
		'Issue Deleter',
		'Issue Mover',
		'Project Admin',
		'Project Member',
		'Sprint Manager'
		]
	# Get IDs for each admin role
	admin_role_ids = [project_role.get('id') for project_role in 
		project_roles if project_role.get('name') in admin_roles]
	if not len(admin_role_ids) == len(admin_roles):
		cli.output_message('warning', 'Not all expected admin roles were found. '
			'Please check your Permission scheme.')
	# Add admin user (you) to all project roles.
	admin_users = [username]
	results.append(add_to_role(session, base_url, key, admin_role_ids, 
		user_role, admin_users))


def set_project_roles(session: requests.Session, base_url: str, key:str, 
	project_roles: list, username: str, retries: int, timeout: int) -> list:
	"""
	Set basic permissions for a project based on the SDTE Internal Work Instructions:
	https://confluence-sdteob.web.boeing.com/display/SDEWI/Create+Jira+Project.
	These permissions are also required to create the filters for boards created
	with this script.

	Categories = 'atlassian-user-role-actor' or 'atlassian-group-role-actor'

	Args:


	Returns:
		(list): True if role was added.
	"""

	results = []

	user_role = 'user'
	group_role = 'group'
	# Admin project roles
	admin_roles = [
		'Issue Closer',
		'Issue Deleter',
		'Issue Mover',
		'Project Admin',
		'Project Member',
		'Sprint Manager'
		]
	# Get IDs for each admin role
	admin_role_ids = [project_role.get('id') for project_role in 
		project_roles if project_role.get('name') in admin_roles]
	if not len(admin_role_ids) == len(admin_roles):
		cli.output_message('error', 'Not all expected admin roles were found. '
			'Please check your Permission scheme.')
	# Add admin user (you) to all project roles.
	admin_users = [username]
	results.append(add_to_role(session, base_url, key, admin_role_ids, 
		user_role, admin_users))
	# Get admin group's SDTEOB_<key>_admin and add to all project roles.
	cli.output_message('info', f'Searching for {key} admin groups.')
	admin_groups = []
	admin_group_name = get_jira_group(session, base_url, key.upper(),
		'_admin', retries, timeout)
	admin_groups.append(admin_group_name)
	results.append(add_to_role(session, base_url, key, admin_role_ids, 
		group_role, admin_groups))
	
	# Member project roles.
	member_roles = [
		'Issue Closer',
		'Project Member'
		]
	# Get IDs for each member role.
	member_role_ids = [role.get('id') for role in project_roles if 
		role.get('name') in member_roles]
	if not all(member_role_ids):
		cli.output_message('error', 'Not all expected user roles were found. '
			'Please check your Permission scheme.')
	# Add user group to member project roles.
	cli.output_message('info', f'Searching for {key} user groups.')
	member_groups = []
	member_groups.append(get_jira_group(session, base_url, key.upper(),
		'_user', retries, timeout))
	results.append(add_to_role(session, base_url, key, member_role_ids, 
		group_role, member_groups))
	return results


def add_to_role(session: requests.Session, base_url: str, key: str, 
	role_ids: list, category: str, names: list) -> list:
	"""
	Add a list of users or groups to a project role. The category must match the type of entity
	being added (https://docs.atlassian.com/software/jira/docs/api/REST/8.13.1/#api/2/project/
	{projectIdOrKey}/role-setActors)
	Categories = 'atlassian-user-role-actor' or 'atlassian-group-role-actor'

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.
		role_ids(list): List of role id's from Jira.
		category(str): Category of role actor (see description above).
		names(list): Users to add to roles.

	Returns:
		(list): Result of each add
	"""

	results = []
	for role_id in role_ids:
		rest_path = f'{base_url}/rest/api/2/project/{key}/role/{role_id}'
		payload = {category: names}
		result = session.post(rest_path, json.dumps(payload))
		if result.status_code == HTTPStatus.OK:
			results.append(result)
			log.info(f'Role id = {role_id}, adding users: {names}')
		elif 'already' in result.text:
			results.append(result)
			log.info(f'Role id = {role_id}, users already in role: {names}')
		else:
			results.append(None)
			log.info(f'Role id = {role_id}, unable to add users to role: {names}')
	return results


def get_jira_group(session: requests.Session, base_url: str, key: str, 
	search_string: str, retries: int, timeout: int) -> str:
	"""
	Searches for a group name in Jira. If the search string is not 
	provided, prompt for string.

	Args:


	Returns:

	"""

	groups = []
	group_count = len(groups)
	while group_count < 1:
		# Search for groups
		if search_string is None:
			search_string = input('Enter part of a group name to search for '
				'(case sensitive): ')
			rest_path = (f'{base_url}/rest/api/2/groups/picker?'
				f'query={search_string}')
			search_prompt = (f'No results matching \"{search_string}\". '
			'Starting interactive search.')
		else:
			rest_path = f'{base_url}/rest/api/2/groups/picker?query={key}'
			search_prompt = (f'No results matching \"{key}{search_string}\". '
				'Starting interactive search.')
		results = rest_get(session, rest_path, HTTPStatus.OK, retries, timeout)
		# Parse results
		group_names = [group.get('name') for group in results.get('groups')]
		groups = [name for name in group_names if search_string in name]
		group_count = len(groups)
		# if nothing returned, search again.
		if group_count == 0:
			cli.output_message('info', search_prompt)
			search_string = None
			continue
		# Build group table and display
		table_title = '\"{}\" Groups Found'.format(search_string)
		table_columns = ['#', 'Group Name']
		table_dataset = []
		count = 1
		for group in groups:
			table_dataset.append([count, group])
			count += 1
		cli.print_table(table_title, table_columns, table_dataset)
		# Get user selection
		user_selection = None
		while user_selection is None:
			user_selection = input('Select a group (enter number, 0 for new '
				'search): ')
			try:
				user_selection_int = int(user_selection) - 1
			except ValueError as exception_message:
				cli.output_message('warning', 
					'Invalid Input Error: {exception_message}')
				user_selection = None
				continue
			if user_selection_int == -1:
				search_string = None
				group_count = 0
				break
			elif user_selection_int not in range(group_count):
				cli.output_message('warning', 
					f'Invalid input: {user_selection}')
				user_selection = None
	return groups[user_selection_int]


def get_permission_scheme(session: requests.Session, base_url: str, key: str, 
	retries: int, timeout: int)-> dict:
	"""
	Get permission scheme used by project.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(dict): Results from query.
	"""

	rest_path = f'{base_url}/rest/api/2/project/{key}/permissionscheme'
	response = rest_get(session, rest_path,	HTTPStatus.OK, retries, timeout)
	return response


def get_permissions(session: requests.Session, base_url: str, 
	permission_scheme: dict, retries: int, timeout: int) -> dict:
	"""
	Get permissions contained in a permission scheme.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		permission_scheme(dict): Results of permission scheme query.

	Returns:
		(dict): Results from query.
	"""

	rest_path = (f"{base_url}/rest/api/2/permissionscheme/" 
		f"{permission_scheme.get('id')}/permission")
	results = rest_get(session, rest_path, HTTPStatus.OK, retries, timeout)
	return results


def validate_project_groups(session: requests.Session, base_url: str, key: str,
	username: str, project_roles: list, retries: int, timeout: int):
	"""
	Simple check to see if any groups have been assigned permissions to the 
	project. If not, call set_project_roles.

	"""

	# Find groups in project
	groups = []
	group_count = 0
	for role in project_roles:
		actors = role.get('actors')
		if len(actors) > 0:
			group_actors = [actor.get('name') for actor in actors if 
				'group' in actor.get('type')]
			group_count = len(group_actors)
			if group_count > 0:
				for group_actor in group_actors:
					if not group_actor in groups:
						groups.append(group_actor)
	if groups:
		return True

	if not groups:
		groups = set_project_roles(session, base_url, key, project_roles, 
			username, retries, timeout)

	return False


def import_versions(session: requests.Session, base_url: str, key: str, 
	versions: list, datetime_format_versions: str, retries: int, timeout: int):
	"""
	Create versions in Jira using the REST API.

	NOTE: The field listed below in rest_version_schema are the only ones 
	imported by the	rest api. Start date is not set on creation.

	Args:
		namespace(SimpleNamespace): Configuration data.
		session: Requests.Session object (including authentication)
		base_url: URL of Jira server
		key: Project key of project to add versions to.
		version_csv: Version data from csv.
			[{}, ...]
	"""

	# Determine which fields to use
	rest_version_schema = [
		'description',
		'name',
		'archived',
		'released',
		'releaseDate',
		'startDate',
		'overdue'
		]

	# Until I learn a better way, comprehend only row 0
	versions_headers = versions[0]
	versions_rows = [version for version in versions if 
		versions.index(version) != 0]

	# Get existing versions from Jira
	existing_versions = get_version_info(session, base_url, key, retries, 
		timeout)
	existing_version_names = []
	if existing_versions:
		existing_version_names = [version['name'] for version in 
			existing_versions]

	#  Rest path and url will change if a create or update is performed
	created_version_count = 0
	for version in tqdm(versions_rows, desc='Creating necessary versions'):
		version_name_index = versions_headers.index('name')
		csv_version_name = version[version_name_index]
		if csv_version_name not in existing_version_names:
			# Build payload
			payload = {'project': key}
			for field in rest_version_schema:
				if field in versions_headers:
					csv_value = version[versions_headers.index(field)]
					if csv_value != '':
						if csv_value.lower() in ['true', 'false']:
							payload[field] = csv_value.lower()
						elif 'Date' in field:
							datetime_obj = core.datetime_to_dateobject(
								csv_value)
							payload[field] = datetime_obj.strftime(
								datetime_format_versions)
						else:
							# payload[field] = csv_value.replace('/','-')
							payload[field] = csv_value
			# Create version
			rest_path = '{}/rest/api/2/version'.format(base_url)
			result = rest_post(session, rest_path, payload, 
				HTTPStatus.CREATED)
			if result:
				log.info('Created version %s.', payload)
				created_version_count += 1
	cli.output_message('info', f'Added {created_version_count}/'
		f'{len(versions_rows)} versions. Version import complete.')


def import_components(namespace: SimpleNamespace, session: requests.Session, 
	base_url: str, key: str, component_list: list):
	"""
	Create components in the target project.

	Args:
		session(JIRA): Jira connection using the python-jira library.
		key(str): Project key for target Jira instance.
		component_list(list): List of components exports from jira using the python-jira library.
	"""

	# component_schema = [
	#     'self',
	#     'id',
	#     'name',
	#     'assigneeType',
	#     'realAssigneeType',
	#     'isAssigneeTypeValid',
	#     'project',
	#     'projectId',
	#     'archived'
	# ]

	# Format incoming data
	component_headers = component_list[0]
	component_rows = [row for row in component_list if 
		component_list.index(row) != 0]

	# Get existing components from project
	existing_component_names = []
	rest_path = '{}/rest/api/2/project/{}/components'.format(base_url, key)
	existing_components = rest_get(session, rest_path, HTTPStatus.OK, 
		namespace.General.get('retries'), namespace.General.get('timeout'))
	existing_component_names = [component.get('name') for component in 
		existing_components]

	# Add any component that does not already exist
	created_component_count = 0
	component_max = len(component_rows)
	for component in tqdm(component_rows, 
		desc='Creating necessary components'):
		component_name = component[component_headers.index('name')]
		if not component_name in existing_component_names:
			payload = {}
			payload['name'] = component_name
			try:
				description_index = component_headers.index('description')
				description = component[description_index]
				if description != '':
					payload['description'] = description
			except ValueError as exception_details:
				log.info(
					'Component \"%s\", has no description. %s',
					component_name,
					exception_details
					)
			payload['project'] = key
			rest_path = '{}/rest/api/2/component'.format(base_url)
			result = rest_post(session, rest_path, payload, 
				HTTPStatus.CREATED)
			if result:
				log.info('Created component %s.',payload)
				created_component_count += 1
	cli.output_message('info', f'Added {created_component_count}/'
		f'{component_max} components. Component import complete.')


def create_filter(namespace:SimpleNamespace, session: requests.Session, 
	base_url: str, key: str, project_roles: list, retries: int, 
	timeout: int) -> int:
	"""
	If there are already boards in the project do not create this filter.
	"""

	boards = get_boards(session, base_url, key, retries, timeout)
	if len(boards) > 0:
		return None

	# rest_filter_schema = [
	#     'name',
	#     'description',
	#     'jql',
	#     'favourite',
	#     'editable'
	# ]

	# Build payload
	payload = {
		'name': f'{key} All Issues Filter',
		'description': f'Created as base filter for {key}',
		'jql': f'project = {key} ORDER BY Rank ASC',
		'favourite': False,
		'editable': False
		}

	# Create filter
	filter_id = None
	rest_path = '{}/rest/api/2/filter'.format(base_url)
	result = rest_post(session, rest_path, payload, HTTPStatus.OK)
	if result:
		log.info('Created filter %s.', payload)
		filter_id = result.get('id')

	# Set share permissions
	project_id = get_project_id(session, base_url, key, 
		namespace.General.get('retries'), namespace.General.get('timeout'))
	project_role_dict = {role.get('name'): role.get('id') for role in 
		project_roles}
	project_admin_payload = {
		'type': 'projectRole',
		'projectId': project_id,
		'projectRoleId': project_role_dict.get('Project Admin'),
		'view': 'true',
		'edit': 'true'
		}
	project_member_payload = {
		'type': 'projectRole',
		'projectId': project_id,
		'projectRoleId': project_role_dict.get('Project Member'),
		'view': 'true',
		'edit': 'false'
		}
	add_project_roles = [project_admin_payload, project_member_payload]
	if not filter_id is None:
		rest_path = f'{base_url}/rest/api/2/filter/{filter_id}/permission'
		for payload in add_project_roles:
			result = rest_post(session, rest_path, payload, 
				HTTPStatus.CREATED)
	return filter_id


def get_project_id(session: requests.Session, base_url: str, key: str, 
	retries: int, timeout: int) -> int:
	"""
	Get the project id for a given project key.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(int): Id of project key.
	"""

	project_id = None
	rest_path = f'{base_url}/rest/api/2/project/{key}'
	result = rest_get(session, rest_path, HTTPStatus.OK, retries, timeout)
	if len(result) > 0:
		project_id = result.get('id')
	return project_id


def create_board(session: requests.Session, base_url: str, key: str, 
	filter_id: int, retries: int, timeout: int) -> int:
	"""
	Boards are created but the column config is not imported since the fields do not necessarily
	map in the new instance. Swim lanes will have to be configured manually by the program.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.
		filter_id(int): Jira id for a board's filter.

	Returns:
		(int): Id of created board or None if create fails.
	"""

	# Output variable
	board_id = None

	# Get existing boards
	boards = get_boards(session, base_url, key, retries, timeout)

	# Create a scrum board if necessary
	result = False
	if len(boards) == 0:
		payload = {
				'name': '{} Scrum Board'.format(key),
				'type': 'scrum',
						'filterId': filter_id
			}
		rest_path = '{}/rest/agile/1.0/board'.format(base_url)
		result = rest_post(session, rest_path, payload, 
			HTTPStatus.CREATED)
		if result:
			board_id = result.get('id')
	elif len(boards) == 1:  # One board = Use this board
		board_index = 0
		board_id = boards[board_index].get('id')
	else:  # More than one board = User has to choose
		display_sprints(session, base_url, boards, key)
		choice = -1
		while choice not in range(len(boards)):
			choice_str = input('Enter number for board to add sprints to '
				'(0 to exit): ')
			if choice_str.isnumeric():
				choice = int(choice_str) - 1
				if choice == 0:
					quit()
		board_id = boards[choice].get('id')

	return board_id


def import_sprints(namespace:SimpleNamespace, session: requests.Session, 
	base_url: str, files: str, board_id: int, csv_dataset: list, retries: int, 
	timeout: int, page_step: int) -> bool:
	"""
	Sprint import uses a different time format,

	Returns:
		(bool): Were sprints created.
	"""

	# Get existing sprints from Jira
	existing_sprints = get_sprints_from_board_id(session, base_url, board_id, 
		retries, timeout, page_step)
	existing_sprints_names = [sprint.get('name') for sprint in 
		existing_sprints]

	# Get sprints from script export if any (No merge necessary as all sprint
	# exports should have identical rows)	
	sprints = []
	exported_sprint_names = []
	exported_sprint_headers = []
	for file in files:
		data = io_module.read_csv(file)
		if not sprints:
			sprints.append(data[0])
		[sprints.append(row) for row in data if data.index(row) != 0]
	if sprints:
		exported_sprint_headers = sprints[0]
		exported_sprint_names = [sprint[exported_sprint_headers.index('name')] 
			for sprint in sprints if sprints.index(sprint) != 0]

	# Add sprints from csv file if they don't exist in Jira or sprint exports
	sprints_from_csv = []
	columns = core.get_columns(csv_dataset[0], 'sprint')
	csv_rows = [row for row in csv_dataset if csv_dataset.index(row) != 0]
	for row in csv_rows:
		for col in columns:
			value = row[col]
			is_sprint_from_jira = value in existing_sprints_names
			is_number = value.isnumeric()
			is_sprint_from_export = value in exported_sprint_names
			if value and not all(is_sprint_from_jira, is_number, 
				is_sprint_from_export):
				sprints_from_csv.append(value)
	for sprint in sprints_from_csv:
		new_row = ['' for header in exported_sprint_headers]
		new_row[exported_sprint_headers.index('name')] = sprint
		sprints.append(new_row)

	# Fields allowed for initial sprint creation
	sprint_schema = [
		'startDate',
		'endDate',
		'goal',
		'name'
	]

	sprints_created_count = 0
	if len(sprints) > 0:
		sprint_headers = sprints[0]
		sprint_rows = [sprint for sprint in sprints if 
			sprints.index(sprint) != 0]
		sprint_total = len(sprint_rows)
		for sprint in tqdm(sprint_rows, desc='Creating sprints'):
			if (not sprint[sprint_headers.index('name')] in 
				existing_sprints_names):
				# Build payload
				payload = {'originBoardId': board_id}
				for field in sprint_headers:
					if field in sprint_schema:
						sprint_header_index = sprint_headers.index(field)
						field_value = sprint[sprint_header_index]
						if field_value != '':
							if 'date' in field.lower():
								payload_value = core.datetime_to_dateobject(
									field_value)
								payload_value = payload_value.strftime(
									namespace.DateFormats.get('sprint'))
								payload[field] = payload_value
							else:
								payload[field] = field_value
				rest_path = f'{base_url}/rest/agile/1.0/sprint'
				result = rest_post(session, rest_path, payload, 
					HTTPStatus.CREATED)
				if result.get('id'):
					sprints_created_count += 1
		cli.output_message('info', f'Created {sprints_created_count}/'
			f'{sprint_total} sprints. Sprint import Complete.')
	else:
		cli.output_message('info', 'No sprints in source file. Continuing.')

	if sprints_created_count > 0:
		return True
	else:
		return False


def find_and_replace_sprints(session: requests.Session, base_url: str, 
	key: str, csv_data: list, retries: int, timeout: int, 
	page_step: int, namespace: SimpleNamespace) -> list:
	"""
	Search for sprint names and replace with sprint id.

	Args:

	Returns:

	"""

	# Get csv data and find sprint columns
	headers = csv_data[0]
	sprint_columns = core.get_columns(headers, 'Sprint')

	# Get sprints, create dictionary of name:id, find and replace values in sprint columns
	# Determine board for sprints
	boards = get_boards(session, base_url, key, retries, timeout)
	board_list = [{'name': board.get('name'), 'id': board.get('id')} for board in boards]

	# Get existing sprints from project
	modified = False
	for board in board_list:
		existing_sprints = _get_sprints(session, base_url, board.get('id'), 
			retries, timeout, page_step)
		existing_sprints_dict = {sprint.get('name'): sprint.get('id') for 
			sprint in existing_sprints}
		# csv_headers = csv_data[0]
		csv_working_set = [row for row in csv_data if csv_data.index(row) != 0]
		for row in tqdm(csv_working_set, desc='Replace sprint names with id, in CSV data'):
			for col in sprint_columns:
				if row[col] != '':
					sprint_index = existing_sprints_dict.get(row[col])
					if not sprint_index is None:
						csv_data[csv_data.index(row)][col] = sprint_index
						if not modified:
							modified = True
	if modified:
		namespace.Flags['modified'] = True
	return csv_data


def _get_sprints(session: requests.Session, base_url: str, board_id: int, 
	retries: int, timeout: int, page_step: int) -> list:
	"""
	Get all sprints associated with a given board id.

	Args:
		session: Requests.Session object (Contains headers including authentication).
		base_url: URL of Jira server..
		board_id: Jira id number of board.

	Returns:
		(list): [{name:{id, self, state, startDate, endDate, originBoardId, goal}}]
	"""

	sprints = []
	last_page = False
	start_at = 0
	desc= f'Getting all sprints for board id = {board_id}'
	progress_bar = tqdm(desc=desc, total=0)
	while not last_page:
		rest_path = (f'{base_url}/rest/agile/1.0/board/{board_id}/sprint/?'
			f'startAt={start_at}&maxResults={page_step}')
		results = rest_get(session, rest_path, HTTPStatus.OK, retries, 
			timeout)
		if len(results) == 0:
			break
		progress_bar.total += len(results.get('values'))
		# Set up url for next page if exists
		if results.get('isLast') is not None:  # In case no sprints returned
			if results.get('isLast'):
				last_page = True
			else:
				start_at += page_step
		# Add page to results
		for sprint in results['values']:
			sprints.append(sprint)
			progress_bar.update()
	progress_bar.close()
	return sprints


def validate_epic_status(session: requests.Session, base_url: str, key: str,
	csv_dataset: list, retries: int, timeout: int, username: str, 
	epic_status_url: str) -> bool:
	"""
	This does not work in it's current state. On Pre-prod it goes through
	the entire list of projects and doesn't get the epic statuses.

	Validate that no new statuses are present in the epic status field. This will require an
	issue to be created in the target project, then metadata extracted from the issue, followed
	by deletion of the issue. If project does not contain epics, return empty list.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.
		csv_dataset(list): Dictionary of attachments to upload.
	
	Returns:
		(bool): True if CSV dataset was modified.
	"""

	epic_status_field= 'Custom field (Epic Status)'
	# Get valid Statuses
	rest_path = f"{base_url}{epic_status_url}"
	payload = {'username': username}
	valid_statuses = rest_post(session, rest_path, payload, HTTPStatus.OK)

	# Get statuses from CSV
	csv_headers = csv_dataset[0]
	csv_rows = [row for row in csv_dataset if csv_dataset.index(row) != 0]
	epic_status_column = core.get_columns(csv_dataset[0],epic_status_field)
	csv_epic_status_list = []
	for column in epic_status_column:
		for row in csv_rows:
			field_value = row[column]
			if field_value != '' and field_value not in csv_epic_status_list:
				csv_epic_status_list.append(field_value)

	# Map CSV status to valid status
	replacement_dict = {}
	for status in csv_epic_status_list:
		if status not in valid_statuses:
			# Build table
			table_title = 'Map Epic Status \"{}\"'.format(status)
			table_columns = ['#', 'Status']
			table_dataset = [(count, value) for count, value in 
				enumerate(valid_statuses, 1)]
			cli.print_table(table_title, table_columns, table_dataset)
			# Get user to map to valid values
			user_selection_int = -1
			while user_selection_int not in range(len(valid_statuses)):
				user_selection = input('Select a status to replace \"{}\": '.format(status))
				if user_selection.isnumeric():
					user_selection_int = int(user_selection) - 1
			replacement_dict[status] = valid_statuses[user_selection_int]

	# Replace values in csv_dataset, If replacements is True data was modified.
	replacements = core.find_and_replace_in_column(csv_dataset, 
		epic_status_field, replacement_dict)
	return replacements


def set_sprint_status(session: requests.Session, base_url: str, key: str, 
	csv_file: str, sprint_tz_format: str, retries: int, timeout: int, 
	page_step: int):
	"""
	Set final sprint status after CSV import. This function will perform a 
	partial update, only submitting fields that are being changed. Completed 
	data, cannot be set. A state of "future" doesn't require any change. The 
	"closed" state requires a sprint to be in the active state in order to 
	close. There can only be one sprint in the active state at a time. So a 
	sprint with a target state of "active" will have to be processed last.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.
		csv_file(str): Input CSV file.
	"""

	# Get boards
	boards = get_boards(session, base_url, key, retries, timeout)

	# Get sprint files
	sprint_count = 0
	sprint_state_dict = {'future': [], 'closed': [], 'active': []}
	csv_sprint_list = []
	jira_sprint_list = []
	sprint_headers = []
	sprint_name_index = None
	sprint_start_date_index = None
	sprint_end_date_index = None
	sprint_complete_date_index = None
	sprint_rows = []
	search_string = '_Sprints'
	files = io_module.find_files(search_string, csv_file, 'csv')
	if len(files) > 0:
		for file in files:
			if '.bak' in file:
				log.info('Skipping backup file, %s.', file)
			else:
				board_index = None
				if len(boards) > 1:
					display_sprints(session, base_url, boards, key, retries, 
						timeout)
					choice = -1
					while choice not in range(len(boards)):
						choice_str = input('Enter number for board to add '
							'sprints to (0 to exit): ')
						if choice_str.isnumeric():
							choice = int(choice_str) - 1
							if choice == 0:
								quit()
					board_index = choice
				elif len(boards) == 1:
					board_index = 0
				else:
					cli.output_message('ERROR', "No boards found.")
					sys.exit()

				# board = boards[board_index].get('board')
				board_id = boards[board_index].get('id')
				# Get sprints from board
				jira_sprint_list = get_sprints_from_board_id(session, 
					base_url, board_id, retries, timeout, page_step)
				jira_sprint_dict = {sprint.get('name'): sprint.get('id') for 
					sprint in jira_sprint_list}
				# Get sprints from CSV (this will determine target state)
				csv_sprint_file_content = io_module.read_csv(file)
				sprint_headers = csv_sprint_file_content[0]
				csv_sprint_rows = [row for row in csv_sprint_file_content if 
					csv_sprint_file_content.index(row) != 0]
				sprint_count = len(csv_sprint_rows)
				# Set sprint indices
				sprint_name_index = sprint_headers.index('name')
				try:
					sprint_start_date_index = sprint_headers.index('startDate')
					sprint_end_date_index = sprint_headers.index('endDate')
					sprint_complete_date_index = sprint_headers.index(
						'completeDate')
				except ValueError as exception_message:
					cli.output_message( 'ERROR', 'Non-fatal Error: Unable to '
						f'get sprint date column indices. {exception_message}')
				# Add id to corresponding state in sprint_dict
				for sprint in csv_sprint_rows:
					try:
						sprint_state_index = sprint_headers.index('state')
						sprint_state_value = sprint[sprint_state_index]
						sprint_state_value = sprint_state_value.lower()

						sprint_name_value = sprint[sprint_name_index]
						sprint_id = jira_sprint_dict.get(sprint_name_value)

						if sprint_id not in sprint_state_dict[sprint_state_value]:
							sprint_state_dict[sprint_state_value].append(
								sprint_id)
						if sprint not in csv_sprint_list:
							csv_sprint_list.append(sprint)
					except ValueError as exception_message:
						cli.output_message('ERROR', 'Non-fatal error: No '
							'sprint state, cannot set status.')

	for state in tqdm(sprint_state_dict, desc='Updating sprint statuses'):
		state = state.lower()
		for sprint_id in sprint_state_dict.get(state):
			# Get sprint name
			sprint_name = ''
			for key, value in jira_sprint_dict.items():
				if value == sprint_id:
					sprint_name = key
					break
			sprint_matches = [row for row in csv_sprint_list if 
				sprint_name == row[sprint_name_index]]
			if len(sprint_matches) == 1:
				sprint = sprint_matches[0]
			elif len(sprint_matches) == 0:
				continue
			else:
				cli.output_message('WARNING', 'More than one sprint matched '
					f'sprint_name. Results: sprint_matches = {sprint_matches}'
					f', sprint = {sprint}, sprint_id = {sprint_id}, '
					f'state = {state}, sprint_name = {sprint_name}')
			# If date is provided use it, otherwise get current date
			try:
				sprint_start_date = ''
				sprint_end_date = ''
				sprint_close_date = ''
				if (sprint[sprint_start_date_index] == '' or 
					sprint_start_date_index is None):
					sprint_start_date = \
						core.get_formatted_current_datetime(sprint_tz_format)
					time.sleep(5)
				else:
					sprint_start_date = sprint[sprint_start_date_index]

				if (sprint[sprint_end_date_index] == '' or 
					sprint_end_date_index is None):
					sprint_end_date = \
						core.get_formatted_current_datetime(sprint_tz_format)
					time.sleep(5)
				else:
					sprint_end_date = sprint[sprint_end_date_index]

				if (sprint[sprint_complete_date_index] == '' or 
					sprint_complete_date_index is None):
					sprint_close_date = \
						core.get_formatted_current_datetime(sprint_tz_format)
				else:
					sprint_close_date = sprint[sprint_complete_date_index]
			except ValueError as exception_message:
				cli.output_message('ERROR', 'Non-fatal Error: Sprint CSV '
					'date/time missing. Current date/time will be used.')
			except IndexError as exception_message:
				cli.output_message('ERROR','Error: Index missing. '
					f'{exception_message}')
			# In order to status a sprint the dates must exist.
			result = status_sprint(session, base_url, sprint_id, state, 
				retries, timeout, sprint_start_date, sprint_end_date, 
				sprint_close_date)
			if not result:
				cli.output_message('ERROR', f'Unable to set sprint {sprint_id}'
					f' = {state}')


def status_sprint(session: requests.Session, base_url: str, sprint_id: int,
	sprint_target_state: str, retries: int, timeout: int, 
	start_date: str = None, end_date: str = None, close_date: str = None
	) -> bool:
	"""
	Apply a status to a Jira sprint.

	Args:
		session(requests.session):
		base_url: URL of target server.
		sprint_id: id of target sprint.
		sprint_target_state(str):
		start_date(str):
		end_date(str):
		close_date(str):

	Returns:
		True if sprint is correctly statused according to the CSV input.
	"""

	rest_path = f'{base_url}/rest/agile/1.0/sprint/{sprint_id}'
	# Sprint can only be closed from "active"
	result_list = rest_get(session, rest_path, HTTPStatus.OK, retries, 
		timeout)
	sprint_status = result_list.get('state')
	sprint_name = result_list.get('name')
	if sprint_target_state == sprint_status:
		# Nothing to do
		log.info('Sprint: \"%s\", is correctly statused as \"%s\".', 
			sprint_name, sprint_status)
		return True
	elif (sprint_target_state in ['active', 'closed'] and 
		sprint_status == 'future'):
		# Activation requires a start and end date
		payload = {'state': 'active', 'startDate': start_date, 
			'endDate': end_date}
		result = rest_post(session, rest_path, payload, HTTPStatus.OK)
		if result:
			result = status_sprint(session, base_url, sprint_id, 
				sprint_target_state, retries, timeout, start_date, end_date, 
				close_date)
		return True
	elif sprint_target_state == 'closed' and sprint_status == 'active':
		# Closure requires a completion date
		payload = {'state': 'closed', 'completeDate': close_date}
		result = rest_post(session, rest_path, payload, HTTPStatus.OK)
		if result:
			result = status_sprint(session, base_url, sprint_id, 
				sprint_target_state, retries, timeout, start_date, end_date,
				close_date)
		return True
	else:
		return False


def import_checklists(session: requests.Session, base_url: str, 
	rest_endpoint: str, key: str, filename: str, exclusions: list, 
	retries: int, timeout: int):
	"""
	Import checklist data to Jira.

	Args:
		sessions(requests.Session): Jira_session
		base_url(str): base URL of the connected Jira instance.
		rest_endpoint(str): URL of ScriptRunner REST endpoint.
		key(str): project key to import to.
		filename(str): FQDN of the checlist json file to import.
		exclusions(list): List of custom field ids excluded from import
		retries(int): Number of retries in case of error or timeout.
		timeout(int): Number of seconds to wait before failing.
	"""

	json_string = open(filename, encoding='utf8').read()
	json_dict = json.loads(json_string)
	fields_file = ''
	while not os.path.exists(fields_file):
		fields_file_list = io_module.find_files('_Fields', filename, 'csv')
		if len(fields_file_list) == 1:
			fields_file = fields_file_list[0]
		else:
			menu_title = 'Unable to identify fields file'
			menu_columns = ['#', 'Location']
			menu_dataset = [[fields_file_list.index(file) + 1, 
				file] for file in fields_file_list]
			cli.print_table(menu_title, menu_columns, menu_dataset)
			user_selection = input('Select the fields file to use (0 to skip): ')
			if int(user_selection) == 0:
				break
			fields_file = fields_file_list[int(user_selection) - 1]
		log.info('Fields file: %s', fields_file)
	field_list = io_module.read_csv(fields_file)
	json_dict = sanitize_checklist_json(json_dict, key, field_list, exclusions, 
		session, base_url, retries, timeout)
	url = f'{base_url}{rest_endpoint}'
	session.post(url, json.dumps(json_dict))


def sanitize_checklist_json(json_input: dict, key: str, 
	source_field_list: list, exclusion_list: list, session: requests.Session, 
	base_url: str,retries: int, timeout: int) -> dict:
	"""
	Prepare checklist json data for import.
	1. Re-key issues.
	2. Remove escaped characters from input (unless we can fix the handling 
		of these so the work).
	3. update custom field ids.
		https://jira-sdteob.web.boeing.com/rest/api/2/customFields?types=com.okapya.jira.checklist:checklist

	Args:
		json_input(dict): Input read from json file.
		key(str): Project key to use in target instance.
		source_field_list(list): List of fields from source instance.
		exclusion_list(list): List of checklist ids to skip.
		session(requests.Session): HTTP session to Jira.
		base_url(str): Server's URL.
		retries(int): retry count.
		timeout(int): Seconds to wait before aborting connection.

	Returns:
		(dict): Dictionary for import to Jira's Scriptrunner Rest endpoint.
	"""

	# Create reference dictionary for field update
	field_map = {}  # {source_id:target_id}

	source_headers = source_field_list[0]
	# Filter source rows for checklists
	filtered_rows = []
	source_rows = [row for row in source_field_list if 
		source_field_list.index(row) != 0]
	for row in source_rows:
		schema_value = row[source_headers.index('schema')]
		schema_value = schema_value.replace('\'', '\"')
		if not schema_value:
			continue
		schema_dict = json.loads(schema_value)
		custom_field_type = schema_dict.get('custom')
		if custom_field_type == 'com.okapya.jira.checklist:checklist':
			filtered_rows.append(row)
	source_header_map = {header: source_headers.index(header) for header in 
		source_headers}

	target_field_list = get_fields(session, base_url, retries, timeout)

	for filtered_row in filtered_rows:
		source_id = filtered_row[source_header_map.get('id')]
		source_name = filtered_row[source_header_map.get('name')]
		source_schema = filtered_row[source_header_map.get('schema')]
		source_schema = source_schema.replace("'", '"')
		source_schema = json.loads(source_schema)
		match_count = 0
		match_list = []
		# Build match list for this row
		for target_row in target_field_list:
			target_id = target_row.get('id')
			target_name = target_row.get('name')
			target_schema = target_row.get('schema')
			if source_name.lower() != target_name.lower():
				continue
			if source_schema.get('type') != target_schema.get('type'):
				continue
			if source_schema.get('custom') and \
				source_schema.get('custom') != target_schema.get('custom'):
					match_count += 1
					match_list.append([match_count, target_id, target_name, target_schema])
			if source_schema.get('system') and \
					(source_schema.get('system') == target_schema.get('system')):
					match_count += 1
					match_list.append([match_count, target_id, target_name, target_schema])
		# Unable to identify unique match, user decision necessary.
		if len(match_list) > 1: 
			table_title = 'User input required: Unable to match source field to target field'
			table_columns = ['#', 'id', 'name', 'schema']
			table_dataset = [[0, source_id, source_name, source_schema]]
			for match in match_list:
				table_dataset.append(match)
			cli.print_table(table_title, table_columns, table_dataset)
			selection = ''
			while selection not in range(len(table_dataset)):
				selection = int(input('Select the correct match for row 0 (the source field): ') - 1)
			field_map[source_id] = match_list[selection][table_columns.index('id')]
		# Single match, one row = index 0, match_list 1 is the id
		if len(match_list) == 1: 
			field_map[source_id] = match_list[0][1]  
		# Offer to create a matching field if none is found?
		if len(match_list) < 1: 
			cli.output_message('ERROR', f'Source field = \"{source_name}\". '
				'No matching field on target server.')

	# Update field id's
	new_dataset = {}
	for issue in json_input:
		new_dataset[issue] = {}
		for field in json_input.get(issue):
			new_field_id = field_map.get(field)
			if new_field_id and new_field_id not in exclusion_list:
				new_dataset[issue][new_field_id] = json_input.get(issue).get(field)

	# rekey issues
	new_dataset = core.rekey_checklist(new_dataset, key)
	
	# remove invalid entries
	new_dataset = core.remove_invalid_checklist(new_dataset)

	# remove special characters
	new_dataset = core.remove_special_chars_from_checklist(new_dataset)

	return new_dataset





#region de-spaghettification
def import_screens(session: requests.Session, base_url: str, 
	rest_endpoint: str, csv_file: str, project_key: str, retries: int, 
	timeout: int):
	"""
	Import screens using the Scriptrunnter custom endpoint from screens.groovy
	This includes field id matching and screen file re-key prior to import.

	Args:
		sessions(requests.Session): Jira_session
		base_url(str): base URL of the connected Jira instance.
		rest_endpoint(str): URL of ScriptRunner REST endpoint.
		csv_file(str): FQDN of the checlist json file to import.
		project_key(str): project key to import to.
		retries(int): Number of retries in case of error or timeout.
		timeout(int): Number of seconds to wait before failing.
	"""

	screen_file_list = io_module.find_files('_Screens', csv_file, 'json')
	if len(screen_file_list) == 0:
		cli.output_message('error', 'Unable to locate *_Screens.csv file.')
		quit()

	screen_config_filename = ''
	while not screen_config_filename:
		menu_title = 'Screen configuration file(s) found'
		menu_columns = ['#', 'Location']
		menu_dataset = [[screen_file_list.index(file) + 1, file] for file 
			in screen_file_list]
		cli.print_table(menu_title, menu_columns, menu_dataset)
		user_selection = input('Enter number of screen configuration to '
			'import (0 to skip): ')
		if int(user_selection) == 0:
			return
		if (int(user_selection) - 1) in range(len(screen_file_list)):
			screen_config_filename = screen_file_list[int(user_selection) - 1]
			break

	fields_file = ''
	while not fields_file:
		fields_file_list = io_module.find_files('_Fields', csv_file, 'csv')
		if len(fields_file_list) == 1:
			fields_file = fields_file_list[0]
		else:
			menu_title = 'Multiple field files found'
			menu_columns = ['#', 'Location']
			menu_dataset = [[fields_file_list.index(file) + 1, 
				file] for file in fields_file_list]
			cli.print_table(menu_title, menu_columns, menu_dataset)
			user_selection = input('Select the fields file to use (0 to skip): ')
			if int(user_selection) == 0:
				break
			fields_file = fields_file_list[int(user_selection) - 1]

	while not os.path.exists(fields_file):
		print('Select your Jira fields CSV file: ', end = '')
		fields_file = io_module.get_filename('Select your fields CSV file',
			[['CSV files', '*.csv']])
		print(fields_file)
	field_list = io_module.read_csv(fields_file)

	screen_config_json = None
	with open(screen_config_filename, 'r') as json_file:
		screen_config_text = json_file.read()
		screen_config_json = json.loads(screen_config_text)
		# re-key screen data
		screen_config_json['project']['key'] = project_key

	screens_data = None
	if screen_config_json:
		screens_data = update_field_ids(session, base_url, 
			screen_config_json, field_list, retries, timeout)

	rest_path = f'{base_url}{rest_endpoint}'
	response = session.post(rest_path, screens_data)

	rest_path = f'{base_url}{rest_endpoint}'
	response = rest_post(session, rest_path, screens_data, HTTPStatus.CREATED)
	return response


def update_field_ids(session: requests.Session, base_url: str, 
	json_dict: dict, source_field_list: list, retries: int, 
	timeout: int) -> dict:
	"""
	Map screen fields from one instance to another.

	Args:
		sessions(requests.Session): Jira_session
		base_url(str): base URL of the connected Jira instance.
		json_dict(dict): JSON data to modify.
		source_field_list(list): List of fields from source server.
		retries(int): Number of retries in case of error or timeout.
		timeout(int): Number of seconds to wait before failing.
	
	Returns:
		(dict): Updated JSON data.
	"""

	# Get fields from target Jira. List of dicts.
	target_field_list = get_fields(session, base_url, retries, timeout)

	# Create reference dictionary for field update
	field_map = {} # {source_id:target_id}

	# Determine which fields from the source we need to map
	field_list = []
	required_fields = core.find_leaves(json_dict, field_list)
	required_fields = set(required_fields)

	# Match required fields to source records
	source_headers = source_field_list[0]
	source_rows = [row for row in source_field_list if source_field_list.index(row) != 0]
	source_header_map = {header: source_headers.index(header) for header in source_headers}
	for source_row in source_rows:
		source_id = source_row[source_header_map.get('id')]
		if source_id not in required_fields:
			continue
		source_name = source_row[source_header_map.get('name')]
		source_schema = source_row[source_header_map.get('schema')]
		source_schema = source_schema.replace("'", '"')
		source_schema = json.loads(source_schema) if source_schema else source_schema

		match_count = 0
		match_list = []
		for target_row in target_field_list:
			target_id = target_row.get('id')
			target_name = target_row.get('name')
			target_schema = target_row.get('schema')
			if source_name.lower() == target_name.lower():
				if not source_schema and not target_schema:
					# issueKey and thumbnails don't have a schema but still need to be mapped.
					match_list.append([match_count, target_id, target_name, {}])
					break
				if source_schema.get('type') == target_schema.get('type'):
					if (source_schema.get('custom') == target_schema.get('custom')) and source_schema.get('custom'):
						match_count += 1
						match_list.append([match_count, target_id, target_name, target_schema])
						break
					if source_schema.get('system') == target_schema.get('system') and source_schema.get('system'):
						match_count += 1
						match_list.append([match_count, target_id, target_name, target_schema])
						break

		if len(match_list) > 1: # Unable to identify unique match, user decision necessary.
			table_title = 'User input required: Unable to match source field to target field'
			table_columns = ['#', 'id', 'name', 'schema']
			table_dataset = [[0, source_id, source_name, source_schema]]
			for match in match_list:
				table_dataset.append(match)
			cli.print_table(table_title, table_columns, table_dataset)
			selection = ''
			while selection not in range(len(table_dataset)):
				selection = int(input('Select the correct match for row 0 (the source field): ')) - 1
			field_map[source_id] = match_list[selection][table_columns.index('id')]

		if len(match_list) == 1: # Unique match
			field_map[source_id] = match_list[0][1] # one row = index 0, match_list 1 is the id

		if len(match_list) < 1: # No match, look into creating the field in target.
			if cli.ask_yes_no(
				'Source Field, \"{}\", not found in target. Would you like to create it? (Y/N): ' \
				.format(source_name)
				):
				new_field_id = create_custom_field(session, base_url, source_row)
				field_map[source_id] = new_field_id

	# Update field id's
	core.update_leaves(json_dict, field_map)
	return json_dict


def upload_attachments(session: requests.Session, base_url: str, 
	csv_dataset: list, csv_filename: str):
	"""
	Restore downloaded attachments to new instance.
	attachments:dict = {url from csv:{original filename, Jira issue key}}
	Note: The RestAPI doesn't have any facility to set the name or date
		for uploading these attachments. The uploader will be the user running
		the script and the date will be the time of upload.
	Note: attachments are expected to be in subdirectory of the CSV's location.
	Note: CSV file will have %20 in place of spaces in the link, but not the 
	filename.

	Args:
		session(requests.Session): HTTP session object.
		base_url(str): URL of target server to upload attachments to.
		csv_dataset(list): Dictionary of attachments to upload.
		csv_filename(str): Path and filename of csv file.
	"""

	# Find attachment directory
	attachment_dir = ''
	project_dir = os.path.dirname(csv_filename)
	for root, dirs, files in os.walk(project_dir):
		if 'secure' in dirs:
			attachment_dir = os.path.normpath(root)

	# Get attachments from CSV
	csv_headers = csv_dataset[0]
	csv_rows = [row for row in csv_dataset if csv_dataset.index(row) != 0]
	issue_key_column = csv_headers.index('Issue key')
	attachment_columns = core.get_columns(csv_headers, 'Attachment')
	attachment_dict = {}
	for row in csv_rows:
		issue_key = row[issue_key_column]
		row_attachments = []
		for col in attachment_columns:
			field_value = row[col]
			if field_value:
				row_attachments.append(field_value)
		if len(row_attachments) > 0:
			attachment_dict[issue_key] = row_attachments

	# Add temporary header
	headers = {"X-Atlassian-Token": "no-check"}
	for header in headers:
		if not header in session.headers:
			session.headers[header] = headers.get(header)

	# Remove Content-Type header because it causes trouble for upload 
	# (replace at end of function)
	headers = ['Content-Type']
	for header in headers:
		if header in session.headers:
			del session.headers[header]

	upload_count = 0
	description = f'Validating file attachments for {len(attachment_dict)} issues'
	for issue_key in tqdm(attachment_dict, desc=description):
		# Get attachment data for issue (from Jira)
		jira_data = get_issue(session, base_url, issue_key)
		if not jira_data:
			cli.output_message('error', f'Could not get issue {issue_key}.')
			continue
		jira_data_fields = jira_data.get('fields')
		if not jira_data_fields:
			cli.output_message('error', f'Could not get fields for {issue_key}.')
			continue
		jira_fields_attachments = jira_data_fields.get('attachment')
		if not jira_fields_attachments:
			cli.output_message('warning', f'Attachments missing for {issue_key}. Will attempt to upload directly.')

		jira_filenames = [attachment.get('filename') for attachment in 
			jira_fields_attachments]

		# Get filenames from attachment_dict
		csv_filename_dict = core.get_attachment_data(attachment_dict[issue_key])

		# Check if any attachments are missing
		# csv_filename_dict = {filename:[date/time, filename, url]}
		for filename in csv_filename_dict:
			if filename not in jira_filenames:
				# Convert HTML space to ASCII space
				filename = filename.replace('%20', ' ')
				# Locate file in local storage
				# jira_filenames[filename] indices: 0:datetime,1:uploader,2:url
				filename_parsed_url = urlparse.urlparse(csv_filename_dict.get(filename)[2])
				filename_path = filename_parsed_url.path
				filename_normalized= os.path.normpath(filename_path)
				upload_filename = os.path.join(attachment_dir, filename_normalized[1:])

				if os.path.exists(upload_filename):
					rest_path = f'/rest/api/2/issue/{issue_key}/attachments'
					query_url = f'{base_url}{rest_path}'
					attachment_data = open(upload_filename, 'rb')
					http_response = session.post(url=query_url,
						files={'file': attachment_data})
					http_status = http_response.status_code
					attachment_data.close()
					if http_status == HTTPStatus.OK:
						upload_count += 1
						log.info('%s: attached, %s', issue_key, filename)
						break
					else:
						log.error('HTTP %d - %s: failed to attach, %s. %d retries remain. %s',
							http_status, issue_key, filename, http_response._content)
	cli.output_message('INFO', f'Uploaded {upload_count}/{len(attachment_dict)} attachments.')

	# Remove session headers
	headers = ['X-Atlassian-Token']
	for header in headers:
		if header in session.headers:
			del session.headers[header]

	# Add Content-type header we deleted above
	headers = {"Content-Type": "application/json"}
	for header in headers:
		if not header in session.headers:
			session.headers[header] = headers.get(header)
#endregion
