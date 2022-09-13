#!/usr/bin/env python3
"""
License request jira module
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports - standard library
from http import HTTPStatus
import json
import logging
import requests
from types import SimpleNamespace

# Imports - 3rd party

# Imports - Local
import common_functions


# Get logger
log = logging.getLogger(__name__)


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
	headers = {
		"Accept": "application/json",
		"Authorization": f'Basic {namespace.b64}',
		"Content-Type": "application/json"
		}
	for header in headers:
		session.headers[header] = headers.get(header)
	session.verify = False
	namespace.session = session
	return namespace


def query_issues(jira_session: requests.Session, url: str, project_key: str,
	issue_status: str, component_name: str) -> list:
	"""
	Get all Jira issues matching project key, issue status, and component name

	Args:
		jira_session: jira session
		project_key: project key
		issue_status: issue status (e.g. "To Do")
		component_name: component name (e.g. "License Request")

	Returns:
		List: List of jira.issue objects containing all the issue found.
	"""


	common_functions.output_log_and_console('info', 
		'Querying Jira for {} requests.'.format(component_name))
	rest_path = f'{url}/rest/api/2/search'
	query_jql = (f"?jql=project='{project_key}' AND status='{issue_status}' "
		f"AND component='{component_name}'&fields=key")
	response = jira_session.get(f'{rest_path}{query_jql}')
	json_response = json.loads(response.content)
	issue_keys = [issue.get('key') for issue in json_response.get('issues')]
	issues_count = len(issue_keys)
	common_functions.output_log_and_console(
		'info',
		'Found {} {} requests'.format(component_name, issues_count)
	)
	return issue_keys


def get_issue(session: requests.Session, base_url: str, issue_key: str, 
	fields: list = []) -> dict:
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
	response = session.get(rest_path)
	json_response = json.loads(response.content)
	return json_response


def get_epic_name(jira_session: requests.Session, jira_url: str, 
	jira_issue: dict) -> str:
	"""
	Get the issue listed in the Epic Link field and return the name of the 
		epic.

	Args:
		jira_session: jira session
		jira_issue: JIRA.issue

	Returns:
		String containing Epic name
	"""

	epic_key = jira_issue.get('fields').get('customfield_10100')
	epic_issue = get_issue(jira_session, jira_url, epic_key, 
		fields = [common_functions.JIRA_EPIC_NAME])
	epic_name = epic_issue.get('fields').get('customfield_10102')
	return epic_name


def check_service_account(issue_data: dict) -> bool:
	"""
	Check if request is for a service account. This is just a string check
	for the words 'service' or 'svc'. Maybe a better method or a modification
	to the work instructions and request url would yield better results.

	Args:
		issue: Single Jira issue.

	Returns:
		bool: True if service account.
	"""

	search_terms = ['service', 'svc']
	issue_summary = issue_data.get('fields').get('summary')
	issue_description = issue_data.get('fields').get('description')
	is_service = False
	for term in search_terms:
		if term.lower() in [issue_summary.lower(), issue_description.lower()]:
			is_service = True
	return is_service


def fix_description(description: str) -> str:
	"""
	1. Remove spaces around equal sign in description.
	2. Remove asterisks.
	"""

	# Remove spaces around "=".
	result = description.replace(' = ', '=')
	result = result.replace('*', '')
	return result


def parse_request(jira_issue: dict, epic_name: str) -> dict:
	"""
	Parse a request delimited by "Name=" (NOTE: no spaces) for multiple users 
		in one request.

	Args:
		description: jira.issue.fields.description - the content of an issue's 
			description field.
		epic_name: String from issue's "Epic Link" field.

	Returns:
		Dict: all parsed records from request
		{0:{
			'Name':'',
			'Email':'',
			'Windows Userid':'',
			'BEMSID':'',
			'Needed Applications':'',
			'Program':''
			},
		 1:{},
		 ...
		}
	"""


	common_functions.output_log_and_console('info',
		 f"\nParsing request {jira_issue.get('key')}")
	description = jira_issue.get('fields').get('description')
	description = fix_description(description)
	name_count = description.count('Name=')
	request_start = 0
	request_end = 0
	requests = {}

	for name in range(name_count):
		request_start = description.find('Name=', request_start)
		next_request = description.find('Name=', request_start + 1)
		if next_request >= 0:
			request_end = next_request
		else:
			request_end = len(description)
		parsed_description = description[request_start:request_end]
		parsed_record = parse_record(parsed_description, epic_name)
		requests[name] = parsed_record
		request_start = request_end
	return requests


def parse_record(record: str, epic_name: dict) -> dict:
	"""
	Parse individual fields from a request
	"Needed Applications=All" -> {'Needed Applications':'All'}

	Args:
		record: input line
		epic name: add string as Program

	Returns:
		Dict: containing parsed a record
		{
			'Name':'',
			'Email':'',
			'Windows Userid':'',
			'BEMSID':'',
			'Needed Applications':'',
			'Program':''
		}
	"""

	row = {}
	for line in record.split('\n'):
		if line.find('=') >= 0:
			line_split = line.split('=')
			line_name = line_split[0].strip()
			line_value = line_split[1].strip()
			line_value = line_value.replace('*','') # Remove any bold(*) markup
			row[line_name] = line_value
	row['Program'] = epic_name
	return row


def add_comment(
	jira_session: requests.Session,
	base_url: str,
	issue_key: str,
	comment: str
	) -> bool:
	"""
	Add comment to Jira issue.

	Args:
		jira_session: jira session
		issue_key: jira.issue
		comment: String to add to comment field

	Returns:
		Bool: True if comment was accepted.
	"""

	result = False
	rest_path = f'{base_url}/rest/api/2/issue/{issue_key}/comment'
	payload = json.dumps({'body':f'{comment}'})
	response = jira_session.post(rest_path, payload)
	result = True
	return result


def transition_issue_closed(
	jira_session: requests.Session,
	jira_url: str,
	jira_issue: str,
	transition_name: str,
	assigned_user: str,
	time_spent: str,
	resolution_name: str = 'Done'
	):
	"""
	Transition an issue to closed.

	Args:
		jira_session: JIRA session object
		jira_issue: jira.issue object
		transition_id: String Id of transition (can be found with jira.transitions(issue))
		assigned_user: username of script runner,
		time_spent: elapsed time to process the issue,
		resolution_name: "Done" to close an issue.

	Returns:
		Bool: True if transition was performed.
	"""

	result = False
	# Assign issue
	rest_path = f"{jira_url}/rest/api/2/issue/{jira_issue.get('key')}/assignee"
	payload = {'name':assigned_user}
	response = jira_session.put(rest_path, json.dumps(payload))
	if response.status_code == HTTPStatus.NO_CONTENT:
		# Add worklog
		rest_path = f"{jira_url}/rest/api/2/issue/{jira_issue.get('key')}/worklog"
		payload = {'comment':'Automated Script Processing',
			'timeSpentSeconds':time_spent}
		response = jira_session.post(rest_path, json.dumps(payload))
		if response.status_code != HTTPStatus.CREATED:
			common_functions.output_log_and_console('error', 
				f"Could not add Worklog entry for {jira_issue.get('key')}")
		# Transition issue
		rest_path = f"{jira_url}/rest/api/2/issue/{jira_issue.get('key')}/transitions"
		payload = {'transition':{'id':int(transition_name)},
			'fields':{'resolution':{'name':resolution_name}}}
		response = jira_session.post(rest_path, json.dumps(payload))
		if response.status_code == HTTPStatus.NO_CONTENT:
			result = True
	return result


def transition_issue_blocked(
	jira_session: requests.Session,
	jira_url: str,
	jira_issue: str,
	transition_name: str,
	assigned_user: str,
	time_spent: str,
	blocked_reason: str = 'Help_Needed',
	):
	"""
	Transition an issue to blocked.

	Args:
		jira_session: JIRA session object
		jira_issue: jira.issue object
		transition_id: String Id of transition
		assigned_user: username of script runner,
		time_spent: elapsed time to process the issue,
		blocked_reason: Explanation why issue is blocked.

	Returns:
		Bool: True if transition was performed.
	"""

	result = False
	# Assign issue
	rest_path = f"{jira_url}/rest/api/2/issue/{jira_issue.get('key')}/assignee"
	payload = {'name':assigned_user}
	response = jira_session.put(rest_path, json.dumps(payload))
	if response.status_code == HTTPStatus.NO_CONTENT:
		# Add worklog
		rest_path = f"{jira_url}/rest/api/2/issue/{jira_issue.get('key')}/worklog"
		payload = {'comment':'Automated Script Processing',
			'timeSpentSeconds':time_spent}
		response = jira_session.post(rest_path, json.dumps(payload))
		if response.status_code != HTTPStatus.CREATED:
			common_functions.output_log_and_console('error', 
				f"Could not add Worklog entry for {jira_issue.get('key')}")
		# Transition issue
		rest_path = f"{jira_url}/rest/api/2/issue/{jira_issue.get('key')}/transitions"
		payload = {'transition':{'id':int(transition_name)},
			'fields':{'customfield_13102':blocked_reason}}
		response = jira_session.post(rest_path, json.dumps(payload))
		if response.status_code == HTTPStatus.NO_CONTENT:
			result = True
	return result
