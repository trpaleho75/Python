#!/usr/bin/env python
# Coding = UTF-8

"""
	This module provides the ability to delete data from a Jira project.
"""

# Imports - built in
import http
import logging
from tqdm import tqdm
from types import SimpleNamespace

# Imports - 3rd party
import requests

# Imports - Local
from migration import cli, web


# Logging
log = logging.getLogger(__name__)


def clean(namespace: SimpleNamespace):
	"""
	Perform steps to clean up a test import.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
	"""

	# Common variables from namespace
	session = namespace.session
	base_url = namespace.url
	retries = namespace.General.get('retries')
	timeout = namespace.General.get('timeout')
	page_step = namespace.General.get('page_step')

	# Greeting
	if not cli.ask_yes_no('CAUTION: These operations destroy data. '
		'There is no undo. Do you still want to continue? (Y/N): '):
		return

	# Get and validate project key
	key = input('Enter project key: ').upper()
	if not web.project_exists(session, base_url, key, http.HTTPStatus.OK, 
		retries, timeout):
		cli.output_message('ERROR', f'Project not found with key = {key}.')
		return

	# Get project data
	cli.output_message('INFO', 'Inspecting project. Please be paitent.')
	all_issues = web.get_all_issues_online(session, base_url, key, retries, 
		timeout, page_step)
	all_components = web.get_project_components(session, base_url, key, 
		retries, timeout)
	all_versions = web.get_version_info(session, base_url, key, retries, 
		timeout)
	all_boards = web.get_boards(session, base_url, key, retries, timeout)
	all_sprints = web.get_sprints_from_board_list(session, base_url, 
		all_boards, retries, timeout, page_step)

	while True:
		table_title = 'Clear Data'
		table_columns = ['#', 'Data', 'Count']
		table_dataset = [
			[0, 'Exit', '-'],
			[1, 'Components', len(all_components)],
			[2, 'Issues', len(all_issues)],
			[3, 'Sprints', len(all_sprints)],
			[4, 'Versions', len(all_versions)]
			]

		user_selection = None
		if user_selection not in range(0,len(table_dataset)):
			cli.print_table(table_title, table_columns, table_dataset)
			user_selection = input('Selection: ')
			try:
				user_selection = int(user_selection)
			except ValueError as exception_message:
				cli.output_message('ERROR', 
					f'Invalid input. {exception_message}')

		if not user_selection is None:
			if user_selection == 0:
				return
			elif user_selection == 1:
				delete_components(session, base_url, key, all_components)
				all_components = web.get_project_components(session, base_url, 
					key, retries, timeout)
			elif user_selection == 2:
				delete_issues(session, base_url, key, all_issues)
				all_issues = web.get_all_issues_online(session, base_url, key, 
					retries, timeout, page_step)
			elif user_selection == 3:
				delete_sprints(session, base_url, key, all_sprints, 
					retries, timeout)
				all_sprints = web.get_sprints_from_board_list(session, 
					base_url, all_boards, retries, timeout, page_step)
			elif user_selection == 4:
				if delete_versions(session, base_url, key, all_versions):
					all_versions = web.get_version_info(session, base_url, key, 
						retries, timeout)
			else:
				continue


def delete_components(session: requests.Session, base_url: str, key: str,
	component_list: list) -> bool:
	"""
	Delete all components in the target project.

	Args:
		session(JIRA): Jira connection using the python-jira library.
		base_url: URL of Jira server.
		key(str): Project key for target Jira instance.
		component_list(list): List of components to delete.

	Returns:
		(bool): True if all deletes successfull.
	"""

	# Confirm user intent
	component_count = len(component_list)
	if not cli.ask_yes_no(f'You have requested to delete {component_count} '
		f'components in {key}. Are you sure? (Y/N): '):
		return

	# Delete components
	delete_results = [False for _ in component_list]
	if component_count > 0:
		component_ids = [component.get('id') for component in component_list]
		for component_id in tqdm(component_ids, desc='Deleting components'):
			index = component_ids.index(component_id)
			rest_path = '{}/rest/api/2/component/{}'.format(base_url, component_id)
			result = web.rest_delete(session, rest_path)
			if result:
				delete_results[index] = True

	# Return results
	if all(delete_results):
		cli.output_message('INFO', 'All components deleted successfully.')
		return True
	else:
		cli.output_message('INFO', 'One or more components failed to delete.')
		return False


def delete_issues(session: requests.Session, base_url: str, key:str, 
	issue_list: list) -> bool:
	"""
	Delete all issues in a project.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key(str): Jira project key.
		issue_list(list): list of issues to delete.

	Returns:
		(bool): True if all deletes are successful.
	"""

	# Confirm user intent
	issues_count = len(issue_list)
	if not cli.ask_yes_no(f'You have requested to delete {issues_count} '
		f'issues in {key}. Are you sure? (Y/N): '):
		return

	# Delete all issue in project
	delete_results = [False for issue in issue_list]
	if issues_count > 0:
		issue_ids = [issue.get('key') for issue in issue_list]
		for issue_id in tqdm(issue_ids, desc='Deleting issues'):
			index = issue_ids.index(issue_id)
			rest_path = f'{base_url}/rest/api/2/issue/{issue_id}'
			result = web.rest_delete(session, rest_path)
			if result:
				delete_results[index] = True

	# Return result of deletions
	if all(delete_results):
		cli.output_message('INFO', 'All issue deleted successfully.')
		return True
	else:
		cli.output_message('ERROR', 'One or more issues failed to delete.')
		return False


def delete_sprints(session: requests.Session, base_url: str, key: str,
	sprint_list: list, retries: int, timeout: int) -> bool:
	"""
	Delete all sprints on a board.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		key: project to remove sprints from.
		sprint_list(list): List of sprints to delete.

	Returns:
		(bool): True if all deletes successfull.
	"""

	# Confirm user intent
	sprint_count = len(sprint_list)
	if sprint_count == 0:
		cli.output_message('INFO', 'No sprints found for deletion.')
		return
	else:
		if not cli.ask_yes_no(f'You have requested to delete {sprint_count} '
			f'sprints in {key}. Are you sure? (Y/N): '):
			return

	delete_results = [False for _ in sprint_list]
	if sprint_count > 0:
		sprint_ids = [sprint.get('id') for sprint in sprint_list]
		# Sort sprints by state
		sprints_by_state = {
			'closed': [sprint.get('id') for sprint in sprint_list if 
				sprint.get('state') == 'closed'],
			'active': [sprint.get('id') for sprint in sprint_list if 
				sprint.get('state') == 'active'],
			'future': [sprint.get('id') for sprint in sprint_list if 
				sprint.get('state') == 'future']
		}
		# Future or Closed sprint can be deleted without a status change.
		combined_sprints = (sprints_by_state.get('closed') + 
			sprints_by_state.get('future'))
		combined_sprints = set(combined_sprints)
		for sprint_id in tqdm(combined_sprints, 
			desc='Deleting closed or future sprints'):
			index = sprint_ids.index(sprint_id)
			result = delete_sprint(session, base_url, sprint_id)
			if result:
				delete_results[index] = True
		# Active sprints must be closed prior to deletion.
		for sprint_id in tqdm(sprints_by_state.get('active'), 
			desc='Deleting active sprints'):
			index = sprint_ids.index(sprint_id)
			result = web.status_sprint(session, base_url, sprint_id, 'closed', 
				retries, timeout)
			if result:
				result = delete_sprint(session, base_url, sprint_id)
				if result:
					delete_results[index] = True
	else:
		cli.output_message('INFO', 'No sprints found.')

	# Return results
	if all(delete_results):
		cli.output_message('INFO', 'All sprints deleted successfully.')
		return True
	else:
		cli.output_message('INFO', 'One or more sprints failed to delete.')
		return False


def delete_sprint(session: requests.Session, base_url: str, 
	sprint_id: int) -> bool:
	"""
	Delete one sprint by id.

	Args:
		session(requests.Session): HTTP session for server interaction.
		base_url(str): Jira server URL.
		sprint_id(int): Jira id of target sprint.

	Returns:
		(bool): True if delete was successful.
	"""

	rest_path = '{}/rest/agile/1.0/sprint/{}'.format(base_url, sprint_id)
	result = web.rest_delete(session, rest_path)
	return result


def delete_versions(session: requests.Session, base_url: str, key: str,
	version_list: list) -> bool:
	"""
	Delete all versions in a project.

	Args:
		session: Requests.Session object (Contains headers including authentication).
		base_url(str): Jira server URL.
		key(str): Jira project key.

	Returns:
		(bool): True if all versions deleted successfully.
	"""

	# Confirm user intent
	version_count = len(version_list)
	if not cli.ask_yes_no(f'You have requested to delete {version_count} '
		f'versions in {key}. Are you sure? (Y/N): '):
		return

	# Delete versions
	delete_results = [False for version in version_list]
	if version_count > 0:
		version_ids = [version.get('id') for version in version_list]
		for version_id in tqdm(version_ids, desc='Deleting versions'):
			rest_path = '{}/rest/api/2/version/{}'.format(base_url, version_id)
			result = web.rest_delete(session, rest_path)
			if result:
				index = version_ids.index(version_id)
				delete_results[index] = True
	else:
		cli.output_message('INFO', 'No versions found.')

	# Return results
	if all(delete_results):
		cli.output_message('INFO', 'All versions deleted successfully.')
		return True
	else:
		cli.output_message('INFO', 'One or more versions failed to delete.')
		return False
