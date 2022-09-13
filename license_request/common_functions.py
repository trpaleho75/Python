#!/usr/bin/env python3
"""
Common functions
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports
import base64
import csv
import getpass
import http
import logging
import os
import sys
import time
import tkinter
from tkinter.filedialog import askopenfilename

# Imports - 3rd party
import requests
from requests.exceptions import ConnectionError
# Supress errors when certificate is not provided
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning


# Get logger
log = logging.getLogger(__name__)


# Global constants
INSITE_URI = 'https://insite.web.boeing.com'
JIRA_URI = 'https://jira-sdteob.web.boeing.com'
# JIRA_URI = 'https://jira-sdteob-pp.web.boeing.com'
# CONFLUENCE_URI = 'https://confluence-sdteob.web.boeing.com'

# JIRA_URI = 'https://jira-sdteob-pp.web.boeing.com/'
GLOBAL_CATALOG = 'PhoenixGC.nos.boeing.com'
BASE_DN = 'dc=boeing,dc=com'


JIRA_PROJECT_KEY = 'SDTEPROG'
JIRA_ISSUE_STATUS = 'To Do'

JIRA_LICENSE_REQUEST_COMPONENT = 'License-Request'
JIRA_CONFLUENCE_COMPONENT = 'Confluence'

JIRA_REVOKE_REQUEST = 'Revoke License'
JIRA_GRANT_REQUEST = 'License Request'


# Jira issue description fields
NAME = 'Name'
EMAIL = 'Email'
WINDOWS_USERID = 'Windows Userid'
BEMSID = 'BEMSID'
NEEDED_APPLICATIONS = 'Needed Applications'

# Jira prod insance specific
# Note: The Jira customfield numbers should be changed if the script targets
# at a different instance of Jira.
JIRA_EPIC_LINK = 'customfield_10100'
JIRA_EPIC_NAME = 'customfield_10102'
JIRA_STORY_POINTS = 'customfield_10106'
JIRA_BLOCKED_REASON = 'customfield_13102'
TRANSITION_ID_CLOSED = '51'
TRANSITION_ID_BLOCKED = '61'

AD_PREFIX = 'SDTEOB_LIC'
AD_SUFFIX = '_USERS'
AD_GEN = '_GEN'
AD_DEV = '_DEV'
AD_EXT = '_EXT'

VALID_CED_DATA_SOURCES = ['bps', 'eclascon', 'eclasnew', 'hrnewhire', 'mss', 'aurora', 'insitu']
EXTERNAL_CED_SOURCE = 'non-boeing'
DN_SUFFIX = 'OU=SDTEOB,OU=Groups,OU=NOSGRPS,DC=nos,DC=boeing,DC=com'

RETRIES = 3
SLEEP_SECONDS = 5

TRANSLATIONS = {
	42: None, # Asterisk (Jira Bold)
	60: None, # Less Than
	62: None # Greater Than
}

GENERAL_EMAIL_TEMPLATE = 'general_email_template.html'
DEVELOPER_EMAIL_TEMPLATE = 'developer_email_template.html'

GENERAL_ROLE = 'general'
DEVELOPER_ROLE = 'developer'
EXPECTED_ROLES = [GENERAL_ROLE, DEVELOPER_ROLE]
ALTERNATE_GENERAL_NEEDED_APPLICATIONS = ['jira', 'confluence', 'gen', 'general']
ALTERNATE_DEVELOPER_NEEDED_APPLICATIONS = ['bitbucket', 'artifactory', 'dev', 'develop', 'developer']
SUMMARY_EXCLUSIONS = ['monarch', 'revoke']

def get_credentials() -> dict:
	"""
	Get credentails for HTTP authentication.

	Returns:
		dict: credential dictionary {b64, username, password}
	"""

	credentials = {}

	if not sys.stdin.isatty():
		# git bash has some issues with std input and getpass,
		# if not in a terminal call with winpty then terminate on return.
		os.system('winpty python ' + ' '.join(sys.argv))
		sys.exit()
	else:
		domain = os.getenv('SDTEOB_USER_DOMAIN')
		user = os.getenv('SDTEOB_USER_NAME')
		passwd = os.getenv('SDTEOB_PASSWORD')

		if not domain:
			domain = input('Enter domain (e.g. "nw"): ')

		if not user:
			user = input('Enter login: ')

		if not passwd:
			passwd = getpass.getpass()

		b64_credential = base64.b64encode(
			('{}:{}'.format(user, passwd)).encode('ascii')
		).decode('utf-8')

		credentials['b64'] = b64_credential
		credentials['username'] = user
		credentials['password'] = passwd
		credentials['domain'] = domain
	return credentials


def validate_url(url: str, certificate: str):
	"""
	Check URL for a valid response. If response isn't OK (HTTP 200) then exit.

	Args:
		url: URL to check
		certificate: Cert bundle for SSL/TLS
	"""

	if not certificate:
		disable_warnings(InsecureRequestWarning)
	try:
		log.info('Attempting to validate {}.'.format(url))
		rest_response = requests.get(url, verify=certificate)
		log.info('HTTP response: {}'.format(rest_response))
	except ConnectionError as error_message:
		log.error('Fatal error: Connection Error ={}'
				  .format(error_message.strerror)
				  )
		sys.exit()
	url_ok = bool(rest_response.status_code == http.HTTPStatus.OK)
	if not url_ok:
		output_log_and_console('error', 'Unable to contact {}.'.format(url))
		sys.exit()


def output_log_and_console(
	severity: str,
	message: str
	):
	"""
	Write message to log and console.

	Args:
		severity: log level [info, error]
		message: string to output.
	"""

	if severity == 'info':
		log.info(message)
	elif severity == 'error':
		log.error(message)

	print('{}'.format(message))


def ask_yes_no(
	question: str
	) -> bool:
	"""
	Ask a yes/no question and return a boolean value true/false.

	Args:
		question: Yes/No question.

	Returns:
		Bool: True for yes and False for no.
	"""

	answer = False
	ask = ''
	while ('y' not in ask) and (not 'n' in ask):
		ask = (input(question)).lower()
	if 'y' in ask.lower():
		answer = True
	return answer


def validate_file(files: list) -> bool:
	"""
	Check to see if files exists.

	Args:
		files: List of filenames to check.

	Returns:
		bool: True if all files exist
	"""

	validated = False
	for path in files:
		if path is None or (not os.path.exists(path)):
			output_log_and_console('error', '{} not found, aborting.'.format(path))
			sys.exit
		else:
			validated = True
	return validated


def fix_path(filename: str) -> str:
	"""
	If the file exists, returns a normalized absolute path whether provided a relative filename.
	If provided a relative path it would be relative to the CWD.

	Args:
		filename: filename string.

	Returns:
		str: String containing the normalized absolute path to the input file. Returns None if
		file does not exist.
	"""

	script_path = os.path.dirname(__file__)
	filename_only = os.path.basename(filename)
	path = os.path.join(script_path, filename_only)
	if os.path.exists(path):
		return path
	else:
		return None


def read_csv(csv_file: str) -> list:
	"""
	Read csv into list

	Args:
		csv_file: Path to Jira exported CSV file.

	Returns:
		list: Each entry is a row from the CSV file.
	"""

	data = []
	with open(csv_file, encoding='utf8') as csv_raw:
		# Set max field size (used for very large csv fields)
		max_int = sys.maxsize
		while True:
			try:
				csv.field_size_limit(max_int)
				break
			except OverflowError:
				max_int = int(max_int/10)
		csv.field_size_limit(max_int)

		# Read data from CSV file
		csv_reader = csv.reader(csv_raw, delimiter=',')
		row_count = 1
		# May throw UnicodeDecodeError if non UTF-8 chars detected.
		for row in csv_reader:
			data.append(row)
			row_count += 1
	log.info('Finished reading {}. {} rows added to list.'
			 .format(csv_file, row_count))
	return data


def elapsed_time(input_time: time.time) -> str:
	"""
	Calculate elapsed time since input_time.

	Args:
		input_time(time.time): Time.

	Returns:
		(str): Elapsed time as string.
	"""

	time_passed = time.time() - input_time
	hours = divmod(time_passed, 3600)
	minutes = divmod(hours[1], 60)
	seconds = minutes[1]
	return f'Elapsed time (h:m:s): {int(hours[0]):0>2}:{int(minutes[0]):0>2}:{int(seconds):0>2}'


def elapsed_seconds(start_time: time.time) -> str:
	"""
	Calculate elapsed time since input_time in seconds.


	Args:
		start_time(time.time): Time.

	Returns:
		(int): elapsed time in seconds.
	"""

	time_passed = time.time() - start_time
	billable_units = (int)(time_passed / (6 * 60))
	if billable_units < 1:
		return 360 # Minimum 1/10 of an hour
	else:
		return billable_units * 360


def mark_time(start_time: time):
	"""
	Return time since start_time.

	Args:
		start_time: begining timestamp.

	Return:
		time: Time since start_time.
	"""

	elapsed_time = '{}'.format(time.time() - start_time)
	print(elapsed_time)


def get_file(window_title: str, search_filter: list) -> str:
	"""
	Display a file dialog and ask the user the select their desired file.

	Args:
		window_title(str): Title for the file dialog window.
		search_filter(list): list of lists to filter for. [['filter name','*.extentsion'],...]
			Single filter: [['CSV files','*.csv']]
			Multiple selectable filters: [['CSV files','*.csv'],['Excel files','*.xls *.xlsx']]

	Returns:
		(str): Absolute path to file.
	"""

	filename = ''
	while not os.path.exists(filename):
		root = tkinter.Tk()
		root.attributes('-topmost', True)
		root.withdraw()
		filename = askopenfilename(parent=root, title=window_title, filetypes=search_filter)
		if filename == '':
			if ask_yes_no('No file selected. Do you want to quit? (Y/N): '):
				quit()
	return filename
