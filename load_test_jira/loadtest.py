#!/usr/bin/env python
# Coding = UTF-8


"""
	Jira load tester
"""

# Imports - built in
from argparse import ArgumentParser
import functools
import logging
import operator
import os
from queue import Queue
from random import choice
import sys
from types import SimpleNamespace
# Imports - 3rd party
# Imports - Local
import functions
from issue import Issue
from timer import Timer


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
	message = 'Welcome to the Jira load tester'
	log.info(message)

	# Create namespace and import configuration
	vars = SimpleNamespace()
	#region Argparse
	parser = ArgumentParser()
	parser.add_argument(
		'-u', '--username',
		help='Jira username',
		action='store',
		dest='username',
		required=False
	)
	parser.add_argument(
		'-p', '--password',
		help='Jira password',
		action='store',
		dest='password',
		required=False
	)
	parser.add_argument(
		'-t', '--token',
		help='Jira Personal Access Token (PAT)',
		action='store',
		dest='token',
		required=False
	)
	args = parser.parse_args()
	#endregion
	
	config_file = os.path.join(os.path.dirname(__file__), 'config.ini')
	if os.path.exists(config_file):
		config_object = functions.get_config_ini(config_file)
	functions.config_to_namespace(vars, config_object)

	# Get credentials
	functions.get_credentials(vars, username = args.username, 
		passwd = args.password, pat = args.token)

	# Configure session
	if vars.Flags.get('token'):
		functions.connect_token(vars)
		functions.get_user(vars) # Get user's name since we're using PAT
	else:
		functions.connect_http(vars)

	# Add metrics to namespace
	vars.issue_create = []
	vars.issue_add_attachment = []
	vars.issue_transition = []
	vars.issue_add_comment = []
	vars.issue_add_link = []
	vars.issue_delete = []
	vars.queries = []
	metrics_collection = {
		'Create Issues':vars.issue_create,
		'Add Attachments':vars.issue_add_attachment,
		'Add Comments':vars.issue_add_comment,
		'Link Issues':vars.issue_add_link,
		"Transition Issues":vars.issue_transition,
		'Delete Issues':vars.issue_delete,
		'Run Queries':vars.queries
		}

	# Get issue types
	field_dict = functions.get_fields(vars)
	functions.get_link_types(vars) # Stored in vars
	vars.issue_statuses = {} # {project:{issue_type:[statuses],...}}
	vars.transitions = {} # {project:{issue_type:[transitions],...}}

	# Cleanup and existing data
	functions.clean_existing(vars)

	#region Test Loop
	test_run_timer = Timer()
	test_run_timer.start()
	while test_run_timer.elapsed() < (vars.TestParameters.get('test_duration_minutes') * 60):
		loop_timer = Timer()
		loop_timer.start()
		issue_queue = Queue(vars.TestParameters.get('max_issues'))
		cleanup_queue = Queue(vars.TestParameters.get('max_issues'))
		query_queue = Queue(vars.TestParameters.get('max_queries'))
		job_list = []
		# Create maximum issues and queries
		while not issue_queue.full():
			new_issue = Issue()
			new_issue.build_payload(vars, field_dict)
			job_list.append(new_issue.create_issue)
			issue_queue.put(new_issue)
		while not query_queue.full():
			query_queue.put(functions.jql_query)
		# Queue jobs
		while not issue_queue.empty():
			issue = issue_queue.get()
			cleanup_queue.put(issue) # Add issue to cleanup queue for later deletion
			operations = [issue.upload_attachment, issue.transition_issue, issue.add_comment, issue.link_issue]
			for _ in range(len(operations)):
				chosen_operation = choice(operations)
				job_list.append(chosen_operation)
				if chosen_operation.__name__ == 'link_issue':
					random_issue_index = choice([i for i in range(issue_queue.qsize())]) if issue_queue.qsize() > 0 else None
					random_cleanup_index = choice([i for i in range(cleanup_queue.qsize())]) if cleanup_queue.qsize() > 0 else None
					issue.set_link_target(issue_queue.queue[random_issue_index] if random_issue_index != None else cleanup_queue.queue[random_cleanup_index])
			# Queue up x number of queries based on max queries and issues.
			queue_x_queries = functions.randomize_query_execution(vars)
			for query in range(queue_x_queries):
				if not query_queue.empty():
					query = query_queue.get()
					job_list.append(functions.jql_query)
		# Round out queue with any remaining queries.
		while not query_queue.empty():
			query = query_queue.get()
			job_list.append(functions.jql_query)

		functions.execute_threads(vars, job_list)
		job_list.clear()

		# Cleanup
		while not cleanup_queue.empty():
			issue = cleanup_queue.get()
			job_list.append(issue.delete_issue)
		functions.execute_threads(vars, job_list)
		job_list.clear()
		log.info(f"Loop Complete: {loop_timer.elapsed()} seconds\n")

	#endregion
	total_test_time = test_run_timer.stop()
	
	# Quick metrics
	if vars.Flags.get('console_output'):
		table_title = "Metrics Summary (all times in seconds)"
		table_columns = ['Operation', 'Count', 'Avg', 'Min', 'Max', 'Total']
		summary_metrics = []
		for metric in metrics_collection:
			if len(metrics_collection.get(metric)) == 0:
				# It's radomly possible that a function was not executed.
				# Happens with low issue counts. Just skip it.
				summary_metrics.append([metric, 0, f'{0.0:.2f}', f'{0.0:.2f}', f'{0.0:.2f}', f'{0.0:.2f}'])
				continue
			metric_sum = functools.reduce(operator.add, metrics_collection.get(metric))
			summary_metrics.append(
				[metric,
				f'{len(metrics_collection.get(metric))}',
				f'{(metric_sum / len(metrics_collection.get(metric))):.2f}',
				f'{min(metrics_collection.get(metric)):.2f}',
				f'{max(metrics_collection.get(metric)):.2f}',
				f'{metric_sum:.2f}']
			)
		functions.print_table(table_title, table_columns, summary_metrics)
		message = f"Run Time: {functions.elapsed_time(total_test_time)}"
		print(message)
		log.info(message)

	if vars.Flags.get('csv_output'):
		functions.write_csv(metrics_collection)
	

