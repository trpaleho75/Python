#!/usr/bin/env python
"""
This script will help simplify the verification of users for granting toolchain license access.
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports - standard library
import base64
import colorama
import getpass
import logging
import os
import re
import requests
import sys
import time
from tqdm import tqdm
from math import ceil
from types import SimpleNamespace

# Imports - 3rd party

# Imports - local
import ad_module
import common_functions
import insite_module
import jira_module
import ldap_module
import outlook_module


# Configure logging
log_format = "%(asctime)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
logging.basicConfig(
	level=logging.INFO,
	format=log_format,
	filename=os.path.join(os.path.dirname(__file__), 'license_request.log')
	)
log = logging.getLogger(__name__)


class Person:
	"""
	Represents all data related to a single user that is relevant to
	the license request process.

	Args:
		input_bemsid: A BEMSID is required to instantiate a person object.

	-----------------------------------------------------------------
	|    Person
	-----------------------------------------------------------------
	| +groups : dict
	| +service : bool
	| +bemsid : str
	| +project : str
	| +issue_key : str
	| +role : str
	| +company : str
	| +export_status : str
	| +ced_data_source : str
	| +name : str
	| +email : str
	| +windows_id : str
	| +windows_dn : str
	| +email_sent: bool
	-----------------------------------------------------------------
	| +set_bemsid(self, bemsid: str) : void
	| +set_project(self, project_key: str = None) : void
	| +set_issue_key(self, issue_key: str = None) : void
	| +set_role(self, role: str = None) : void
	| +set_company(self, company: str = None) : void
	| +set_export_status(self, export_status: str = None) : void
	| +set_ced_data_source(self, ced_data_source: str = None) : void
	| +set_name(self, name: str = None) : void
	| +set_email(self, email: str = None) : void
	| +set_windows_id(self, id: str = None) : void
	| +set_windows_dn(self, dn: str = None) : void
	| +set_groups(self, group: str, membership: bool=False) : void
	| +set_service(self, is_service: bool) : void
	| +set_email_sent(self, sent: bool) : void
	| +get_bemsid(self) : str
	| +get_project(self) : str
	| +get_issue_key(self) : str
	| +get_role(self) : str
	| +get_company(self) : str
	| +get_export_status(self) : str
	| +get_ced_data_source(self) : str
	| +get_name(self) : str
	| +get_email(self,) : str
	| +get_windows_id(self) : str
	| +get_windows_dn(self) : str
	| +get_groups(self) : dict
	| +get_service(self) : bool
	| +get_email_sent(self) : bool
	| +has_us_export_status(self) : bool
	| +from_ced_data_source(self, source: str) : bool
	-----------------------------------------------------------------
	"""

	# No Class Attributes

	# Constructor
	def __init__(self, input_bemsid: str):
		"""
		Constructor for Person class using BEMSID from Jira.

		Parameters:
		input_bemsid: parsed from Jira service request.
		"""

		#Instance Attributes
		self.groups = {}
		self.account_type = ''
		self.email_sent = False

		## fields from Jira
		self.set_bemsid(input_bemsid)
		self.set_project()
		self.set_issue_key()
		self.set_role()

		## fields from Insite
		self.set_company()
		self.set_export_status()
		self.set_ced_data_source()

		## fields from LDAP
		self.set_name()
		self.set_email()
		self.set_windows_id()
		self.set_windows_dn()


	# Setters
	def set_bemsid(self, bemsid: str):
		"""
		Set the BEMSID of the user.

		Parameters:
		bemsid (str): A user's BEMSID.
		"""

		self.bemsid = bemsid


	def set_project(self, project_key: str = None):
		"""
		Set the project of the user.

		Parameters:
		project_key (str): Jira project key.
		"""

		self.project = project_key


	def set_issue_key(self, issue_key: str = None):
		"""
		Set the requesting issue key of the user.

		Parameters:
		issue_key (str): Jira issue key.
		"""

		self.issue_key = issue_key


	def set_role(self, role: str = None):
		"""
		Set the user's role.

		Parameters:
		role (str): General/Developer.
		"""

		self.role = role



	def set_company(self, company: str = None):
		"""
		Set the company name of the user.

		Parameters:
		company (str): The user's company name.
		"""

		self.company = company


	def set_export_status(self, export_status: str = None):
		"""
		Set the export status of the user.

		Parameters:
		export_status(str): The user's export status.
		"""

		self.export_status = export_status


	def set_ced_data_source(self, ced_data_source: str = None):
		"""
		Set the CED data source.

		Parameters:
		ced_data_source: The Corporate Electronic Directory(CED) source
		for the user.
		"""

		self.ced_data_source = ced_data_source


	def set_name(self, name: str = None):
		"""
		Set the full name of the user.

		Parameters:
		name (str): Full name of user in format - <Last, First Middle>
		"""

		self.name = name


	def set_email(self, email: str = None):
		"""
		Set the email address of the user.

		Parameters:
		email (str): Email address of user
		"""

		self.email = email


	def set_windows_id(self, id: str = None):
		"""
		Set the Windows Id of the user.

		Parameters:
		id (str): Set the user's windows username.
		"""
		if (not id == None):
			self.windows_id = id


	def set_windows_dn(self, dn: str = None):
		"""
		Set the Windows Id of the user.

		Parameters:
		id (str): Set the user's windows username.
		"""

		self.windows_dn = dn


	def set_groups(self, group: str, membership: bool=False):
		"""
		populate dictionary of groups. Key = group, value = membership status.

		Parameters:
		group (str)
		"""

		self.groups[group] = membership

	def set_service(self, is_service: bool = None):
		"""
		Set the account type of the user (user or service)

		Parameters:
		account_type (str): Set the user's account type.
		"""

		self.service = is_service

	def set_email_sent(self, email_sent: bool = True):
		"""
		Sets the 'email sent' flag to indicate that this script sent the welcome e-mail to this user.

		Parameters:
		email_sent (bool): Boolean flag indicating if the welcome e-mail was sent
		"""

		self.email_sent = email_sent
	# End Setters


	# Getters
	def get_bemsid(self) -> str:
		"""
		Get the user's BEMSID.
		"""

		return self.bemsid


	def get_project(self) -> str:
		"""
		Get the user's project.
		"""

		return self.project


	def get_issue_key(self) -> str:
		"""
		Get the issue key for this user's request.
		"""

		return self.issue_key


	def get_role(self) -> str:
		"""
		Get the user's role.
		"""

		return self.role


	def get_company(self) -> str:
		"""
		Get the user's company name.
		"""

		return self.company


	def get_export_status(self) -> str:
		"""
		Get the user's export status.
		"""

		return self.export_status


	def get_ced_data_source(self) -> str:
		"""
		Get the user's CED data source. Useful for
		identifying contractors for group assingment.
		"""

		return self.ced_data_source


	def get_name(self) -> str:
		"""
		Get the full name of the user, (last, first middle)
		"""

		return self.name


	def get_email(self,) -> str:
		"""
		Get the user's email address.
		"""

		return self.email


	def get_windows_id(self) -> str:
		"""
		Get the windows username from the End User OU.
		"""

		return self.windows_id


	def get_windows_dn(self) -> str:
		"""
		Get the user's distinguished name.
		"""

		return self.windows_dn


	def get_groups(self) -> dict:
		"""
		Get list of groups to add user to.
		"""

		return self.groups

	def get_service(self) -> bool:
		"""
		True if service account.
		"""

		return self.service

	def get_email_sent(self,) -> bool:
		"""
		True if this script sent the welcome e-mail
		"""

		return self.email_sent
	# End Getters


	def has_us_export_status(self) -> bool:
		"""
		Checks the US export status of the person

		Returns:
		true if the Person has US export status, false otherwise
		"""

		result = None
		if self.export_status is None:
			result = False
		elif (self.export_status).upper() == 'U. S. PERSON':
			result = True
		else:
			result = False
		return result


	def from_ced_data_source(self, source: str) -> bool:
		"""
		Compares the Corporate Electronic Directory (CED) data source.

		Returns:
		true if the Person's record was retrieved from the specified data
		source, false otherwise.
		"""

		return self.ced_data_source == source


def check_certificate(arguments: dict):
	"""
	If a certificate file is not provided, or does not exist set to False. Otherwise
	attempt to use SSL/TLS verification.

	Args:
		arguments: Dictionary of command line args
	"""

	if arguments.cert is None:
		log.warning('No certificate provided. Disabling SSL verification.')
		arguments.cert = False
	else:
		if os.path.exists(arguments.cert):
			log.info('Certificate file found. Will use SSL/TLS verification.')
		else:
			log.warning('Certificate not found. Disabling SSL verification.')
			arguments.cert = False


def get_columns(
	csv_data: list,
	search_string: str
	) -> list:
	"""
	Helper: Search input data headers for matching string

	Args:
		csv_data: CSV data represented as list of rows.
		search_string: Column name to search for.

	Returns:
		List: List of column indexes
	"""

	columns = []
	column_count = 0
	csv_header = csv_data[0]
	for heading in csv_header:
		if search_string.lower() in heading.lower():
			columns.append(column_count)
		column_count += 1
	return columns


def create_person(
	insite_url: str,
	bemsid: str
	) -> Person:
	"""
	Instantiate a Person object with BEMSID and add InSite data.

	Args:
		bemsid: BEMSID of user.

	Returns:
		Person: Person object or None

	Uses:
		insite_module (Local import)
	"""

	person = Person(bemsid)

	insite_json = insite_module.get_insite_data(insite_url, bemsid)
	if not insite_json is None:
		if (insite_json['resultholder']['totalResults'] == '1'):
			try:
				person.set_company(
					insite_json['resultholder']['profiles']['profileholder']\
						['user']['company']
						)
			except KeyError as e:
				log.error('Error occured parsing insite data: {}'.format(e))

			try:
				person.set_export_status(
					insite_json['resultholder']['profiles']['profileholder']['user']\
					['usPersonStatusString']
					)
			except KeyError as e:
				log.error('Error occured parsing insite data: {}'.format(e))

			try:
				person.set_ced_data_source(
					insite_json['resultholder']['profiles']['profileholder']['user']\
					['cedDataSource']
					)
			except KeyError as e:
				log.error('Error occured parsing insite data: {}'.format(e))

			first_name = ''
			last_name = ''
			middle_name = ''
			display_name = ''
			try:
				first_name = insite_json['resultholder']['profiles']['profileholder']['user']['firstName']
			except KeyError as e:
				log.error('Error occured parsing insite data: {}'.format(e))
			try:
				last_name = insite_json['resultholder']['profiles']['profileholder']['user']['lastName']
			except KeyError as e:
				log.error('Error occured parsing insite data: {}'.format(e))
			try:
				middle_name = insite_json['resultholder']['profiles']['profileholder']['user']['middleName']
			except KeyError as e:
				log.error('Error occured parsing insite data: %s for BEMSID=%s', e, bemsid)
			if middle_name == '':
				display_name = '{}, {}'.format(last_name, first_name)
			else:
				if len(middle_name) == 1:
					display_name = '{}, {} {}.'.format(last_name, first_name, middle_name)
				else:
					display_name = '{}, {} {}'.format(last_name, first_name, middle_name)
			person.set_name(display_name)
		else:
			common_functions.output_log_and_console(
				'error', 'No data returned from InSite for BEMSID: {}, please check request.'\
				.format(bemsid)
				)
	else:
		common_functions.output_log_and_console('error', 'Insite query failed.')
	return person


def set_ad_info(person: Person, domain: str, username: str, password: str):
	# Query Active Directory (AD) for data on parsed users
	search_filters = []
	search_filters.append(f'(extensionAttribute15={person.get_bemsid()})')

	ldap_attributes = [
		'distinguishedName',
		'userPrincipalName',
		'sAMAccountName',
		'displayName',
		'extensionAttribute15'
	]

	ldap_response = ldap_module.get_ldap_data(
		domain, username, password,
		common_functions.GLOBAL_CATALOG,
		common_functions.BASE_DN,
		search_filters,
		ldap_attributes
	)

	for dn in ldap_response:
		search_string = 'OU=End Users'
		if (
			dn.extensionAttribute15.value == person.get_bemsid() and
			search_string in str(dn.distinguishedName.value).split(',')
			):
			person.set_name(dn.displayName.value)
			person.set_email(dn.userPrincipalName.value)
			person.set_windows_id(dn.sAMAccountName.value)
			person.set_windows_dn(dn.distinguishedName.value)
		else:
			if 'ADM' in person.get_windows_id():
				search_string = 'OU=Secondary Privileged Accounts'
				if (dn.extensionAttribute15.value == person.get_bemsid() and
					search_string in str(dn.distinguishedName.value).split(',')
					):
					person.set_windows_dn(dn.distinguishedName.value)


def output_console_header(license_count: int, license_requests_count: int,
		license_request: str):
	columns = {'Program':17, 'Name':25, 'Export St.':12, 'Company':18,
			'CED':8, 'Role':7, 'Group(s)':32}
	table_width = sum(columns.values()) + (len(columns) - 1)
	colorama.init(autoreset=True) # Initialize Colorama
	print(colorama.Fore.YELLOW + '{:-^{width}.{width}}'.format('', width=table_width))
	section_title = '({}/{}) {}'.format(license_count, license_requests_count,
			license_request)
	print(colorama.Fore.YELLOW + '{:^{width}.{width}}'.format(section_title,
			width=table_width))
	print(colorama.Fore.YELLOW + '{:-^{width}.{width}}'.format('', width=table_width))
	colorama.deinit()
	for key in columns:
		print('{:^{width}.{width}} '.format(key, width=columns.get(key)), end='')
	print()
	for key in columns:
		print('{:-^{width}.{width}} '.format('', width=columns.get(key)), end='')
	print()


def guess_role(person: Person, needed_applications: str) -> str:
	"""
	Alternative to [General/Developer] since many people do not read the instructions. First check will
	assign the "General" role if any one general role application is listed in Needed Applications.
	The second check will update the role to "developer" if any one of the developer role apps are
	listed. Since the developer role implies general access all situations are covered. The second
	check contains a stopgap changing "All" to "Developer" for the developer role.

	Args:
		person: Person object
		needed_applications: string parsed from description field in license request.
	"""

	# strip out any non-alpha characters that may have been included by Jira's markup
	regex = re.compile('[^a-zA-Z]')
	needed_applications = regex.sub('', needed_applications)

	role = None
	for application in common_functions.ALTERNATE_GENERAL_NEEDED_APPLICATIONS:
		if application.lower() in needed_applications.lower():
			role = common_functions.GENERAL_ROLE
			break

	for application in common_functions.ALTERNATE_DEVELOPER_NEEDED_APPLICATIONS:
		if application.lower() in needed_applications.lower() or \
				needed_applications.lower() == 'all':
			role = common_functions.DEVELOPER_ROLE
			break

	if not role is None:
		person.set_role(role)


def output_console_user_status(person: Person):
	highlight = ['Invalid_Export_Status', 'Invalid_CED_Source', 'Invalid Application Requested']
	columns = {'Program':17, 'Name':25, 'Export St.':12, 'Company':18,
			'CED':8, 'Role':7, 'Group(s)':32}
	print('{:^{width}.{width}} '\
		.format(str(person.get_project()), width=columns.get('Program')), end='')
	print('{:<{width}.{width}} '\
		.format(str(person.get_name()), width=columns.get('Name')), end='')
	print('{:^{width}.{width}} '\
		.format(str(person.get_export_status()), width=columns.get('Export St.')), end='')
	print('{:^{width}.{width}} '\
		.format(str(person.get_company()), width=columns.get('Company')), end='')
	print('{:^{width}.{width}} '\
		.format(str(person.get_ced_data_source()), width=columns.get('CED')), end='')
	print('{:^{width}.{width}} '\
		.format(str(person.get_role().capitalize()), width=columns.get('Role')), end='')
	groups = person.get_groups()
	count_group = 1
	for group in groups:
		if group in highlight:
			colorama.init(autoreset=False) # Initialize Colorama
			print(colorama.Fore.RED + '', end='')
		if count_group == 1:
			print('{:<{width}.{width}}'.format(group, width=columns.get('Group(s)')))
			count_group += 1
		else:
			len_pad = (sum(columns.values()) - columns.get('Group(s)')) + (len(columns) - 1)
			print('{pad_c:<{pad}}{group:<{width}.{width}}'.format(pad_c='', pad=len_pad,
					group=group, width=columns.get('Group(s)')))
			count_group += 1
		if group in highlight:
			print(colorama.Style.RESET_ALL + '', end='')
			colorama.deinit()


def ad_user_report(people: list):
	columns = {
		'Name': 25,
		'Group(s)': 32,
		'Is Member': 9
		}

	# Print table header
	print('{:<{width}.{width}} '
		.format(str('Name'), width=columns.get('Name')), end = '')
	print('{:^{width}.{width}} '
		.format(str('Group(s)'), width=columns.get('Group(s)')), end = '')
	print('{:^{width}.{width}} '
		.format(str('Is Member'), width = columns.get('Is Member')))
	# Get data for table
	for person in people:
		groups = person.get_groups()
		group_count = 0
		for group in groups:
			if group_count == 0:
				print('{:<{width}.{width}} '
					.format(str(person.get_name()), width=columns.get('Name')), end='')
				print('{:^{width}.{width}} '
					.format(str(group), width=columns.get('Group(s)')), end='')
				print('{:^{width}.{width}} '
					.format(str(groups[group]), width=columns.get('Is Member')))
			else:
				print('{:<{width}.{width}} '
					.format(str(''), width=columns.get('Name')), end = '')
				print('{:^{width}.{width}} '
					.format(str(group), width=columns.get('Group(s)')), end='')
				print('{:^{width}.{width}} '
					.format(str(groups[group]), width = columns.get('Is Member')))
			group_count += 1


def output_status_line(person: Person, group: str):
	log.info('Program {}: add user \"{}\", to {} = {}.'
			.format(
				person.get_project(),
				person.get_name(),
				group,
				(person.get_groups()).get(group)))
	print('Program {}: add user \"{}\", to {} = {}.'
		.format(
			person.get_project(),
			person.get_name(),
			group,
			(person.get_groups()).get(group)))


def output_jira_comment(user_list: list) -> str:
	output = ''
	header = '||Name||Export St.||Company||CED||Role||Group||Member||E-Mail Sent||\n'
	output += header
	for person in user_list:
		output += '|{}|{}|{}|{}|{}'.format(
				person.get_name(),
				person.get_export_status(),
				person.get_company(),
				person.get_ced_data_source(),
				person.get_role().capitalize())
		groups = person.get_groups()
		count_group = 1
		for group in groups:

			is_group_member = groups[group] # boolean

			if count_group == 1:
				if is_group_member:
					output += '|{}|{}|{}|\n'.format(group, is_group_member, person.get_email_sent())
				else:
					output += '|{{color:red}}{}{{color}}|{{color:red}}{}{{color}}|{}|\n'\
						.format(group, is_group_member, person.get_email_sent())
			elif count_group > 1:
				if is_group_member:
					output += '| | | | | |{}|{}| |\n'.format(group, is_group_member)
				else:
					output += '| | | | | |{{color:red}}{}{{color}}|{{color:red}}{}{{color}}| |\n'\
						.format(group, is_group_member)
			count_group += 1

	output += '~Generated by automated license request script.~'
	return output


def isolated_fix(project: str) -> str:
	"""
	Remove '(SDTE)' from project key if isolated environment.
	"""

	if '(SDTE)' in project:
		project_key= project.split(' ')
		project_key = project_key[0].strip()
		return project_key
	else:
		return project


def assign_groups(person: Person) -> Person:
	# Categorize Person based on established criteria:
	# https://confluence-sdteob.web.boeing.com/pages/viewpage.action?pageId=21676608
	project_key = isolated_fix(person.get_project())
	if person.has_us_export_status():
		if person.get_ced_data_source() in common_functions.VALID_CED_DATA_SOURCES:
			if person.get_role().lower() == common_functions.GENERAL_ROLE:
				group = '{}{}_{}{}'.format(
					common_functions.AD_PREFIX,
					common_functions.AD_GEN,
					project_key,
					common_functions.AD_SUFFIX
					)
				person.set_groups(group)
			elif person.get_role().lower() == common_functions.DEVELOPER_ROLE:
				group = '{}{}_{}{}'.format(
					common_functions.AD_PREFIX,
					common_functions.AD_DEV,
					project_key,
					common_functions.AD_SUFFIX
					)
				person.set_groups(group)
				group = '{}{}_{}{}'.format(
					common_functions.AD_PREFIX,
					common_functions.AD_GEN,
					project_key,
					common_functions.AD_SUFFIX
					)
				person.set_groups(group)
		elif person.from_ced_data_source(common_functions.EXTERNAL_CED_SOURCE):
			ext_prefix = common_functions.AD_PREFIX + common_functions.AD_EXT
			if person.get_role().lower() == common_functions.GENERAL_ROLE:
				group = '{}{}_{}{}'.format(
					ext_prefix,
					common_functions.AD_GEN,
					project_key,
					common_functions.AD_SUFFIX
					)
				person.set_groups(group)
			elif person.get_role().lower() == common_functions.DEVELOPER_ROLE:
				group = '{}{}_{}{}'.format(
					ext_prefix,
					common_functions.AD_DEV,
					project_key,
					common_functions.AD_SUFFIX
					)
				person.set_groups(group)
				group = '{}{}_{}{}'.format(
					ext_prefix,
					common_functions.AD_GEN,
					project_key,
					common_functions.AD_SUFFIX
					)
				person.set_groups(group)
		else:
			person.set_groups('Invalid_CED_Source')
	else:
		person.set_groups('Invalid_Export_Status')
	if len(person.groups) == 0:
		person.set_groups('Invalid Application Requested')
	return person


def build_revoke_request(request) -> list:
	"""
	Process license revocation.
	"""

	people = []
	return people


def build_license_request(session: requests.session, base_url: str, 
	insite_url: str, license_request: dict, domain: str, username: str, 
	password: str) -> list:
	"""
	Process license granting.
	"""

	# lists of person objects in this request.
	people = []

	# Get the epic and if SDTE(Isolated), skip it
	epic_name = jira_module.get_epic_name(session, base_url, license_request)

	# Check for Service account(look for 'Service' or 'SVC' in the windows_id or name)
	is_service = jira_module.check_service_account(license_request)
	if is_service:
		common_functions.output_log_and_console(
			'info',
			'Service account license request. Please process manually.'
			)
		return people

	# Parse users from license request
	users = {}  # Store user data prior to instantiation as Persons.
	issue_key = license_request.get('key')
	users[issue_key] = jira_module.parse_request(license_request, epic_name)
	if len(users[issue_key]) == 0:  # Possible csv process
		question = common_functions.ask_yes_no(
			'{} - No users parsed. Is there a CSV file for this request? (Y/N): '
			.format(issue_key)
			)
		if question:
			print('CSV must contain \"BEMSID\" and \"Applications\" columns.')
			csv_file = common_functions.get_file("Select license CSV", [['CSV files', '*.csv']])

			# Validate files exist
			validate = common_functions.validate_file([csv_file])

			# Read users from file
			csv_data = []
			if validate:
				csv_data = common_functions.read_csv(csv_file)
			else:
				# Abort processing
				return people


			bemsid_column = get_columns(csv_data, 'bemsid')
			applications_column = get_columns(csv_data, 'application')

			# Instantiate a person class for each BEMSID
			csv_header = csv_data[0]
			csv_rows = [row for row in csv_data if csv_data.index(row) != 0]
			for row in tqdm(csv_rows, desc='Reading rows from CSV'):
				# Expect only 1 BEMSID column.
				bemsid = row[bemsid_column[0]]
				# Remove leading zeros.
				bemsid = re.sub('^[0]+', '', bemsid)
				# Expect only 1 app column.
				role = row[applications_column[0]]
				if bemsid != '':
					person = create_person(insite_url, bemsid)
					if not person is None:
						# Add project and role to person2
						person.set_project(epic_name)
						if not role.lower() in common_functions.EXPECTED_ROLES:
							guess_role(person, role)
						else:
							person.set_role(role)
					people.append(person)
				else:
					common_functions.output_log_and_console(
						'error',
						'\nUnable to process row: {}'.format(row)
					)
		else: # No to csv
			common_functions.output_log_and_console(
				'info',
				'Cannot parse issue and no csv provided. Moving to next request.'
				)
	else:  # Normal processing
		# Instantiate a Person object for each parsed user
		for user_index in tqdm(users.get(issue_key), desc='Reading users from request'):
			try:
				bemsid = users[issue_key][user_index][common_functions.BEMSID]
			except:
				print('Unable to retrieve BEMSID for {} in {}. Please check request.'\
					.format(users.get(issue_key).get(user_index).get('Name'), issue_key)
					)
				continue
			bemsid = re.sub('^[0]+', '', bemsid)  # Remove leading zeros
			person = create_person(my_namespace.url_insite, bemsid)
			if not person is None:
				# Add project and role to person
				person.set_project(epic_name)
				try:
					role = (users[issue_key][user_index][common_functions.NEEDED_APPLICATIONS])\
						.translate(common_functions.TRANSLATIONS).lower()
				except:
					print('Unable to parse requested role. Please check request.')
					continue
				if not role.lower() in common_functions.EXPECTED_ROLES:
					guess_role(person, role)
				else:
					person.set_role(role)
				# if is_service set windows_id
				person.set_service(is_service)
				try:
					person.set_windows_id(
						users[issue_key][user_index][common_functions.WINDOWS_USERID]
						)
				except KeyError as e:
					common_functions.output_log_and_console(
						'error',
						'Error parsing request: {}'.format(e)
						)
					continue
			people.append(person)

	# Query Active Directory (AD) for data on parsed users
	for person in tqdm(people, desc='Querying Active Directory'):
		set_ad_info(person, domain, username, password)
		# Assign AD groups to each valid user
		assign_groups(person)

	return people


def finish_message(
	start_time: float
	):
	"""
	Display finish message and elapsed run time

	Args:
		start_time: Time script started

	"""

	elapsed_time = time.time() - start_time
	hours = divmod(elapsed_time, 3600)
	minutes = divmod(hours[1], 60)
	seconds = minutes[1]
	finish_message = '{} finished, elapsed time (h:m:s): {:0>2}:{:0>2}:{:0>2}\n'\
		.format(os.path.basename(__file__), int(hours[0]), int(minutes[0]), int(seconds))
	log.info(finish_message)
	print(finish_message)


if __name__ == '__main__':
	# git bash has some issues with std input and getpass,
	# if not in a terminal call with winpty then terminate on return.
	if not sys.stdin.isatty():
		log.warning('Not a terminal(tty), restarting with winpty.')
		os.system('winpty python ' + ' '.join(sys.argv))
		sys.exit()
		
	# Metrics - Start time
	start_time = time.time()

	my_namespace = SimpleNamespace()

	# Get user credentials
	my_namespace.domain = input('Enter domain (e.g. "nw"): ')
	my_namespace.username = input('Enter login: ')
	my_namespace.password = ''
	password_min_len = 8
	while len(my_namespace.password) < password_min_len:
		my_namespace.password = getpass.getpass()
		if len(my_namespace.password) < password_min_len:
			common_functions.output_log_and_console('error', 
				f'Password less than {password_min_len} '
				'characters, retry.')
	credentials_ascii = f"{my_namespace.username}:{my_namespace.password}".encode('ascii')
	b64_credentials = base64.b64encode(credentials_ascii)
	my_namespace.b64 = b64_credentials.decode('utf-8')
	jira_module.connect_http(my_namespace)

	my_namespace.url_jira = common_functions.JIRA_URI
	my_namespace.url_insite = common_functions.INSITE_URI

	# Validate URLs
	urls_to_validate = [common_functions.INSITE_URI, common_functions.JIRA_URI]
	for url in urls_to_validate:
		common_functions.validate_url(url, False)

	# Establish connection to Jira
	#jira_conn = jira_module.connect(common_functions.JIRA_URI, False, credentials)

	# Get all license requests from Jira
	# jira_license_requests = jira_module.get_all_issues(
	#     my_namespace.session,
	#     common_functions.JIRA_PROJECT_KEY,
	#     common_functions.JIRA_ISSUE_STATUS,
	#     common_functions.JIRA_LICENSE_REQUEST_COMPONENT
	#     )
	jira_license_requests = jira_module.query_issues(my_namespace.session,
		my_namespace.url_jira, 
		common_functions.JIRA_PROJECT_KEY,
		common_functions.JIRA_ISSUE_STATUS,
		common_functions.JIRA_LICENSE_REQUEST_COMPONENT)

	# Check if there are requests to process
	if len(jira_license_requests) == 0:
		common_functions.output_log_and_console('info', 'No license requests found.')
		finish_message(start_time)
		sys.exit()

	# Process requests
	license_count = 0
	for issue_key in jira_license_requests:
		# request processing start time
		request_start = time.time()

		field_list = ['summary', 'description', 'reporter', 'customfield_10100'] #customfield_10100 = Epic Link on Prod
		license_request_data = jira_module.get_issue(my_namespace.session, my_namespace.url_jira, issue_key, field_list)

		# Build request
		people = []
		is_excluded = False
		for exclusion in common_functions.SUMMARY_EXCLUSIONS:
			if exclusion.lower() in license_request_data.get('fields').get('summary').lower():
				common_functions.output_log_and_console(
					'error',
					'Issue Key {} is excluded from automated processing, continuing.'\
						.format(issue_key)
					)
				is_excluded = True
		if is_excluded:
			continue

		people = build_license_request(my_namespace.session, 
			my_namespace.url_jira, my_namespace.url_insite, 
			license_request_data, my_namespace.domain, my_namespace.username, 
			my_namespace.password)
		license_count += 1

		# Status output: which license request is currently in work?
		output_console_header(license_count, len(jira_license_requests), issue_key)
		for person in people:
			output_console_user_status(person)

		# At this point request user confirmation to continue if there are people to add.
		if len(people) > 0:
			confirmation = input(
				'\nDo you wish to make these changes? Any invalid users will be skipped! (Y/N): '
				)
			if confirmation.upper() == 'Y':
				# Read email templates
				general_template = outlook_module.parse_template(
					common_functions.fix_path(common_functions.GENERAL_EMAIL_TEMPLATE))
				developer_template = outlook_module.parse_template(
					common_functions.fix_path(common_functions.DEVELOPER_EMAIL_TEMPLATE))

				# Update email templates with requester and program
				requester = license_request_data.get('fields').get('reporter').get('displayName') #John Doe'
				requester_email = license_request_data.get('fields').get('reporter').get('emailAddress')

				# everyone on this license_request has the same program, so we'll
				# just grab it from the first person in the list
				program = people[0].get_project()  #'Enterprise'

				developer_template['body'] = developer_template['body'].replace('<REQUESTER>', requester)
				developer_template['body'] = developer_template['body'].replace('<PROGRAM>', program)

				general_template['body'] = general_template['body'].replace('<REQUESTER>', requester)
				general_template['body'] = general_template['body'].replace('<PROGRAM>', program)

				# Run the AD action and report results back to Jira
				request_status = True
				if (len(people) > 0):
					# Organize people for addition to groups
					grouped_people = {}
					for person in people:
						for group in person.get_groups():
							if 'invalid' in group.lower():
								request_status = False
								continue
							if not group in grouped_people.keys():
								grouped_people[group] = []
							grouped_people[group].append(person)
					# Add members to groups
					for group in grouped_people:
						# Build list of ADUser objects
						aduser_obj_list = []
						for person in grouped_people[group]:
							aduser_obj_list.append(
								ad_module.get_user(person.get_windows_dn()))
						# Get group AD object
						group_obj = ad_module.get_group(
							'CN={},{}'.format(group, common_functions.DN_SUFFIX))
						if group_obj is None:  # Unable to find AD group
							request_status = False
							continue
						# Add ADUsers to ADGroup
						if person.has_us_export_status():
							members = ad_module.add_members(
								group_obj,
								aduser_obj_list
								)
							for person in grouped_people[group]:
								if person.get_windows_dn() in [member.dn for member in members]:
									# Update people with their group membership status
									person.set_groups(group, True)
								else:
									# If any addition fails, resport request status false
									request_status = False
									person.set_groups(group, False)
						else:
							request_status = False


					# Send welcome email
					for person in people:
						should_send_email_to_this_user = True;
						desired_groups = person.get_groups()
						for group_name in desired_groups.keys():
							is_group_member = desired_groups[group_name]
							if not is_group_member:
								# if we did not successfully verify that user was a member
								# of the desired group, we need to skip e-mail and allow for
								# manual correction
								should_send_email_to_this_user = False

						if should_send_email_to_this_user:
							email_address = person.get_email()
							if person.get_role().lower() == common_functions.DEVELOPER_ROLE:
								outlook_module.send_email(
									developer_template.get(
										'subject'),
									'',  # no plain text body
									developer_template.get('body'),
									recipients = [email_address],
									recipients_cc = [requester_email]
								)
								log.info('Developer welcome email sent to {}'
											.format(email_address))
							else:
								outlook_module.send_email(
									general_template.get(
										'subject'),
									'',  # no plain text body
									general_template.get('body'),
									recipients=[email_address],
									recipients_cc = [requester_email]
								)
								log.info('General welcome email notice sent to {}'
											.format(email_address))

							person.set_email_sent(True)

					# Generate result table
					comment = output_jira_comment(people)
					# Add table to Jira as comment
					result = jira_module.add_comment(
						my_namespace.session,
						my_namespace.url_jira,
						issue_key,
						comment
					)

					# Close request if all users successfully added.
					if not request_status:
						result = jira_module.transition_issue_blocked(
							my_namespace.session,
							my_namespace.jira_url,
							license_request_data,
							common_functions.TRANSITION_ID_BLOCKED,
							my_namespace.username,
							common_functions.elapsed_seconds(request_start),
							'Help_Needed'
						)
						if result:
							common_functions.output_log_and_console(
								'info', 'Moved issue '
								f"{license_request_data.get('key')}"
								' to Blocked, for operator review.')
						else:
							common_functions.output_log_and_console(
								'error', 'Failed to move issue '
								f"{license_request_data.get('key')}"
								' to Blocked.')
					else:  # Everything successful
						result = jira_module.transition_issue_closed(
							my_namespace.session,
							my_namespace.url_jira,
							license_request_data,
							common_functions.TRANSITION_ID_CLOSED,
							my_namespace.username,
							common_functions.elapsed_seconds(request_start),
							'Done'
						)
						if result:
							common_functions.output_log_and_console(
								'info', 'Moved issue '
								f"{license_request_data.get('key')}"
								' to Closed.')
						else:
							common_functions.output_log_and_console(
								'error', 'Failed to move issue '
								f"{license_request_data.get('key')}"
								' to Closed.')
			else:
				print('No changes made. Continuing...\n')
		else:
			common_functions.output_log_and_console(
				'error', 'Unable to retrieve license request '
				f"{license_request_data.get('key')}"
				' from Jira.')

	# Metrics - display elapsed time
	finish_message(start_time)

	input('Script complete, press \"Enter\" to quit...')
