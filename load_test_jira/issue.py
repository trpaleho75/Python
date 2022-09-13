# Imports - Built-in
import copy
from http import HTTPStatus
from itertools import count
import json
import logging
import os
from random import choice
from types import SimpleNamespace
# Imports - 3rd Party
# Imports - Local
import functions
from timer import Timer

# Logging
log = logging.getLogger(__name__)


class IssueError(Exception):
	"""A custom exception used to report errors in use of Issue class"""


class Issue:
	_ids = count(0) 

	def __init__(self):
		self.id = next(self._ids) # Instantiation counter
		self.project_key: str = ''
		self.issue_type: str = ''
		self.issue_key: str = ''
		self.issue_id: str = ''
		self.payload: str = ''
		self.attachment: str = ''
		self.transition: str = ''
		self.link_target: Issue = None
		self.timer = Timer()


	# Getters
	def get_counter(self):
		return str(self._ids)
	

	def get_project_key(self):
		return self.project_key
	

	def get_issue_type(self):
		return self.issue_type
	

	def get_issue_key(self):
		return self.issue_key
	

	def get_issue_id(self):
		return self.issue_id	
	

	def get_payload(self):
		return self.payload


	def get_attachment(self):
		return self.attachment
	

	def get_transition(self):
		return self.transition	

	def get_link_target(self):
		return self.link_target

	# Setters
	def set_project_key(self, value: str):
		self.project_key = value
	

	def set_issue_type(self, value: str):
		self.issue_type = value
	

	def set_issue_key(self, value: str):
		self.issue_key = value


	def set_issue_id(self, value: str):
		self.issue_id = value


	def set_payload(self, value: str):
		self.payload = value
	

	def set_attachment(self, value: str):
		self.attachment = value


	def set_transition(self, value: str):
		self.transition= value


	def set_link_target(self, issue_object): # Set type hint when you figure it out for referencing the class inside the class.
		self.link_target= issue_object


	def build_payload(self, namespace: SimpleNamespace, fields: dict):
		"""
		Build the payload for this issue.

		Args:
			self: This issue.
			namespace: Namespace containing configuration.
			fields: Dictionary of field names and ids.
		"""

		self.set_project_key(choice(namespace.Projects.get('key_list')))
		self.set_issue_type(choice(namespace.Projects.get('issue_types_list')))
		self.set_payload(getattr(namespace, self.issue_type).get('payload'))
		replacement_dict = {
			'{project_key}': self.project_key,
			'{issue_type}': self.issue_type,
			'{field_name}': fields.get('Epic Name'),
			'{username}': namespace.username,
			'{counter}': str(self.id)
		}
		for entry in replacement_dict:
			self.set_payload((self.payload).replace(entry, replacement_dict.get(entry)))


	def create_issue(self, namespace: SimpleNamespace):
		"""
		Create a single issue of random type in the given
		project.

		Args:
			self: This issue.
			namespace: Namespace containing configuration.
		"""

		self.timer.start()
		url = f"{namespace.Server.get('url')}/rest/api/2/issue"
		response = namespace.session.post(url, self.payload)
		if response.status_code == HTTPStatus.CREATED:
			response_json = json.loads(response.text)
			self.set_issue_key(response_json.get('key'))
			self.set_issue_id(response_json.get('id'))
			message = f'{self.project_key}: Created {self.issue_type} {self.issue_key}'
			log.info(message)
		else:
			message = f'{self.project_key}: Failed to create {self.issue_type}: {response.text}: {response.content}'
			log.error(message)
		namespace.issue_create.append(self.timer.stop())


	def upload_attachment(self, namespace: SimpleNamespace):
		"""
		Add random attachment to this issue.

		Args:
			namespace: configuration data.
		"""

		# Safety check
		if not self.issue_key:
			log.error(f"Invalid job: No issue key set for issue.")
			return

		# Copy session object (extra header caused errors while other threads
		# used the namespace with the header in place. Could possibly block
		# and wait, but this was easy at the time, until a better solution
		# is thought of.)
		temp_session = copy.deepcopy(namespace.session)

		#region Configure temporary request headers
		# Add temporary headers
		headers = {"X-Atlassian-Token": "no-check"}
		for header in headers:
			if not header in temp_session.headers:
				temp_session.headers[header] = headers.get(header)
		# Remove Content-Type header because it causes trouble for upload 
		headers = ['Content-Type']
		for header in headers:
			if header in temp_session.headers:
				del temp_session.headers[header]
		#endregion
		
		#region Upload attachment
		self.timer.start()
		random_attachment = choice([file_type for file_type in namespace.Attachments.keys()])
		self.set_attachment(namespace.Attachments.get(random_attachment))
		if os.path.exists(self.attachment):
			url = f"{namespace.Server.get('url')}/rest/api/2/issue/{self.issue_key}/attachments"
			attachment_data = open(self.attachment, 'rb')
			response = temp_session.post(url, files={'file': attachment_data})
			if response.status_code == HTTPStatus.OK:
				message = f"{self.issue_key}: Successfully uploaded attachment \"{self.attachment}\""
				log.info(message)
			else:
				message = f"{self.issue_key}: Uploaded attachment Failed \"{self.attachment}\": {response.status_code}: {response.content}"
				log.error(message)
		namespace.issue_add_attachment.append(self.timer.stop())
		#endregion
		

	def transition_issue(self, namespace: SimpleNamespace):
		"""
		Transition this issue to a random state.

		Args:
			namespace: Configuration data.
		"""
		
		# Safety check
		if not self.issue_key:
			log.error(f"Invalid job: No issue key set for issue.")
			return

		# Get id for desired transition
		if not namespace.transitions.get(self.project_key):
			namespace.transitions[self.project_key] = {}
		if not namespace.transitions[self.project_key].get(self.issue_type):
			namespace.transitions[self.project_key][self.issue_type] = functions.get_transitions(namespace, self.issue_key)
		self.set_transition(choice([transition for transition in namespace.transitions[self.project_key][self.issue_type].keys()]))
		new_transition_id = namespace.transitions[self.project_key][self.issue_type].get(self.transition)

		# Transition issue
		self.timer.start()
		url = f"{namespace.Server.get('url')}/rest/api/2/issue/{self.issue_key}/transitions"
		payload = {"transition":{"id":new_transition_id}}
		response = namespace.session.post(url, json.dumps(payload))
		if response.status_code == HTTPStatus.NO_CONTENT:
			message = f"{self.project_key}: {self.issue_key} transitioned to \"{self.transition}\""
			log.info(message)
		else:
			message = f"{self.project_key}: {self.issue_key} failed to transition to \"{self.transition}\": {response.status_code}: {response.content}"
			log.error(message)
		namespace.issue_transition.append(self.timer.stop())


	def add_comment(self, namespace: SimpleNamespace):
		"""
		Add a comment to this issue
		"""
		
		# Safety check
		if not self.issue_key:
			log.error(f"Invalid job: No issue key set for issue.")
			return

		self.timer.start()
		url = f"{namespace.Server.get('url')}/rest/api/2/issue/{self.issue_key}/comment"
		payload = {"body":"This is a load tester comment"}
		response = namespace.session.post(url, json.dumps(payload))
		if response.status_code == HTTPStatus.CREATED:
			message = f"{self.project_key}: {self.issue_key}, Comment added."
			log.info(message)
		else:
			message = f"{self.project_key}: {self.issue_key}: Unable to add comment: {response.status_code}: {response.content}"
			log.error(message)
		namespace.issue_add_comment.append(self.timer.stop())


	def link_issue(self, namespace: SimpleNamespace):
		"""
		Creates an outward issue link. Link this issue to that issue 
		(i.e. this_issue_key blocks that_issue_key).

		Args:
			namespace: Configuration data.
			target_issue: Outward issue object. (Part of object creation)
			link_types: Dictionary of link types. (Part of namespace now)
		"""
		
		# Safety check
		if not self.issue_key:
			log.error(f"Invalid job: No issue key set for issue.")
			return

		# choose link type
		link_type_name = choice([link for link in namespace.link_types.keys()])
		link_type_id = namespace.link_types.get(link_type_name)
		
		# Link issues
		self.timer.start()
		url = f"{namespace.Server.get('url')}/rest/api/2/issueLink"
		payload = {"type":{"id":link_type_id},"inwardIssue":{"key":self.issue_key},"outwardIssue":{"key":self.link_target.get_issue_key()},"comment":{"body":"Established issue link"}}
		response = namespace.session.post(url, json.dumps(payload))
		if response.status_code == HTTPStatus.CREATED:
			message = f"{self.project_key}: Link established, {self.issue_key} {link_type_name} {self.link_target.get_issue_key()}."
			log.info(message)
		else:
			message = f"Unable to establish link: {self.issue_key} {link_type_name} {self.link_target.get_issue_key()}: {response.status_code}: {response.content}"
			log.error(message)
		namespace.issue_add_link.append(self.timer.stop())


	def delete_issue(self, namespace: SimpleNamespace):
		"""
		Delete this issue.

		Args:
			namespace: Configuration data.
		"""

		# Safety check
		if not self.issue_key:
			log.error(f"Invalid job: No issue key set for issue.")
			return

		self.timer.start()
		url = f"{namespace.Server.get('url')}/rest/api/2/issue/{self.issue_key}?Subtasks=true"
		response = namespace.session.delete(url)
		if response.status_code == HTTPStatus.NO_CONTENT:
			message = f"{self.issue_key}: Deleted."
			log.info(message)
		else:
			message = f"{self.issue_key}: Unable to delete: {response.text}: {response.content}"
			log.error(message)
		namespace.issue_delete.append(self.timer.stop())