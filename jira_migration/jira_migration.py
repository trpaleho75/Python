#!/usr/bin/env python
# Coding = UTF-8

"""
	Main logic for Export/Import script
"""


# Imports - built in
import base64
from getpass import getpass
import logging
import os
import sys
import time
from types import SimpleNamespace

# Imports - 3rd party

# Imports - Local
from migration import clean, cli, core, export, import_post, import_pre
from migration import io_module, offline, web


# Configure logging
LOG_FORMAT = ("%(asctime)s - %(levelname)s - %(module)s:%(funcName)s:"
	"%(lineno)d - %(message)s")
LOG_FILENAME = (__file__.split('\\')[-1]).split('.')[0] + '.log'
logging.basicConfig(
	handlers=[logging.FileHandler(LOG_FILENAME, 'w', 'utf-8')],
	level=logging.INFO,
	format=LOG_FORMAT
)
log = logging.getLogger(__name__)


# Main
if __name__ == '__main__':
	# git bash has some issues with std input and getpass,
	# if not in a terminal call with winpty then terminate on return.
	if not sys.stdin.isatty():
		log.warning('Not a terminal(tty), restarting with winpty.')
		os.system('winpty python ' + ' '.join(sys.argv))
		sys.exit()

	# Welcome
	print('Welcome to the Jira migration script.')

	# Create namespace and import configuration
	vars = SimpleNamespace()
	vars.start = time.time() # Metrics - Start time
	config_file = os.path.join(os.path.dirname(__file__), 'config.ini')
	if os.path.exists(config_file):
		io_module.read_config_ini(vars, config_file)

	# Get user input
	core.select_server(vars)
	web.use_ssl(vars)

	# If using script offline, this is the last step.
	if vars.offline:
		offline.offline_only(vars)
		quit()

	# Get Personal Access Token(PAT) if enabled, otherwise get credentials
	validated = False
	if vars.Flags.get('pat'):
		vars.__setattr__('token', '')
		while len(vars.token) <= 4:
			vars.token = input('Personal Access Token(PAT): ')
			if len(vars.token) <= 4:
				cli.output_message('error', 
					f'Invalid token, retry.')
		web.connect_token(vars)
	else:
		vars.username = input('Enter login: ')
		vars.password = ''
		password_min_len = 8
		while len(vars.password) < password_min_len:
			vars.password = getpass()
			if len(vars.password) < password_min_len:
				cli.output_message('error', 
					f'Password less than {password_min_len} '
					'characters, retry.')
		credentials_ascii = f"{vars.username}:{vars.password}".encode('ascii')
		b64_credentials = base64.b64encode(credentials_ascii)
		vars.b64 = b64_credentials.decode('utf-8')
		web.connect_http(vars)
	validated = web.validate_and_authorize_url(vars)
	if not validated:
		quit()

	# What operation are your performing
	# Build menu
	menu_title = 'Select Operation'
	menu_columns = ['#', 'name', 'Description']
	menu_dataset = [
		[0, 'Exit', 'Exit'],
		[1, 'Export', 'Export data from a Jira project.'],
		[2, 'Pre-Import', 'Prepare project and CSV file for data import.'],
		[3, 'Post-Import', 'Update sprints and checklists after CSV import.'],
		[4, 'Delete Data', 'Delete data from project to prepare for import.']
        ]

	# Present menu
	while True:
		try:
			cli.print_table(menu_title, menu_columns, menu_dataset)
			selection = int(input('Select Operation: '))
			if selection in range(len(menu_dataset)):
				if selection == 0:
					quit()
				elif selection == 1:
					export.export(vars)
				elif selection == 2:
					import_pre.import_pre(vars)
				elif selection == 3:
					import_post.import_post(vars)
				elif selection == 4:
					clean.clean(vars)
		except ValueError as exception_message:
			print('Invalid input: {}'.format(exception_message))
			continue
