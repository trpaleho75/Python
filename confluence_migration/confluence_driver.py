#!python
# Coding: UTF-8

# Header
"""
    Description:
    This script's intent is to update usernames between Confluence instances.
    First step is to pull usernames out of a Confluence space's XML
    export and save them to a CSV file. Then that file can then be updated by
    the program and run through this script again to find and replace the
    old usernames with the new target instances usernames. Additionally
    you will be asked if you would like to update the space's key.
"""

__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'proprietary'
# [...]


# Imports - Standard Library
import datetime
import logging
import os
import sys
import time
from tqdm import tqdm
# Imports - 3rd Party
# Imports - Local
import confluence_interface


# Configure logging (filemode 'w'= new log, 'a' = append)
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
LOG_FILENAME = (__file__.split('\\')[-1]).split('.')[0] + '.log'
logging.basicConfig(level='INFO', format=LOG_FORMAT, filename=LOG_FILENAME, filemode='w')
log = logging.getLogger(__name__)


if __name__ == '__main__':
    # git bash has some issues with std input and getpass,
    # if not in a terminal call with winpty then terminate on return.
    if not sys.stdin.isatty():
        log.warning('Not a terminal(tty), restarting with winpty.')
        os.system('winpty python ' + ' '.join(sys.argv))
        sys.exit()

    # Metrics - Start time
    start_time = time.time()
    log.info('Begin run')

    # Welcome
    print('\nWelcome to the Confluence migration assistance script.')

    # Get starting user input and credentials
    args = confluence_interface.get_user_input()
    args = confluence_interface.get_credentials(args)

    # Establish http session
    http_session = confluence_interface.create_session(args.b64, args.cert)

    # Read XML
    # Get csv file and validate path
    filename = ''
    while not os.path.exists(filename):
        print('Select your entities.xml file: ')
        filename = confluence_interface.get_file(
            'Select your entities.xml file', [['XML files', '*.xml']]
            )
    args.xml = filename

    xml_data = None
    if not args.xml is None:
        if os.path.exists(args.xml):
            xml_data = confluence_interface.read_xml(args.xml)
        else:
            sys.exit('XML file not found, aborting.')

    # Update usernames and keys
    remap = False
    users_dict = {}
    if confluence_interface.ask_yes_no(
        '\nDo you have a user csv table? (Y/N): '
        ):
        print('Select your user table CSV file.')
        # Get file from user and add to args namespace
        args.csv = confluence_interface.get_file('Select Users.csv', [['CSV files', '*.csv']])
        # Update user entries
        users_dict = confluence_interface.read_users_from_csv(args.csv)
    else:
        users_dict = confluence_interface.read_users_from_xml(xml_data)
        # Write user dictionary to csv
        confluence_interface.user_dict_to_csv(users_dict, args.xml, 'UserTable')
        confluence_interface.output_info('User table created at: {}' \
            .format(os.path.split(args.xml)[0]))
        confluence_interface.finish_message(start_time)
        sys.exit("Please fill out the user table the re-run this script.")

    change_count = 0 # Count changes as modify flag so we don't re-write file each run.
    if len(users_dict) > 0:
        # Get user data from target Confluence and update dictionary
        count = len(users_dict)
        description = 'Reading user data from CSV'
        for user in tqdm(users_dict, desc=description):
            valid_target_username = users_dict[user].get('target_username') != ''
            valid_target_key = users_dict[user].get('target_key') != ''
            if valid_target_username and not valid_target_key:
                log.info('Updating user %s => %s', user, users_dict[user].get('target_username'))
                user_temp = confluence_interface.get_user_info(
                    http_session,
                    args.url,
                    user,
                    users_dict[user],
                    'username'
                    )
                if user_temp:
                    users_dict[user] = user_temp
                    change_count += 1

    # Write csv
    if change_count > 0:
        confluence_interface.output_message(
            confluence_interface.INFO,
            '\nPreparing XML data for writing.'
            )
        confluence_interface.user_dict_to_csv(users_dict, args.csv)
        
    # Process XML content
    # Replace users
    answer = confluence_interface.ask_yes_no(
        'If username blank, replace with remap user? '\
            'Otherwise, create users before continuing.(Y/N): '
        )
    xml_data = confluence_interface.replace_user_elements(
        xml_data,
        '//object[@class=\"ConfluenceUserImpl\"]',
        users_dict,
        answer
        )
    xml_data = confluence_interface.update_user_key_elements(
        xml_data,
        '//id[@name=\"key\"]',
        users_dict,
        answer
        )

    # @mentions
    xml_data = confluence_interface.replace_mention(
        xml_data,
        '//property[@name=\"body\"]',
        users_dict
        )

    # Links are a problem, I can't really anticipate what links need to be changed since
    # a user could potentially link to just about anything. I'll look into a sort of
    # user questionaire about known servers like Jira and Confluence, maybe git/bitbucket
    # and see if we can run an interactive replace from there.
    # xml_data = confluence_interface.replace_links(
    #     xml_data,
    #     '//property[@name=\"body\"]',
    #     server
    # )

    # Formatting cleanup
    xml_data = confluence_interface.update_cdata_elements(xml_data)
    xml_data = confluence_interface.remove_duplicate_users(xml_data)
    xml_data = confluence_interface.xml_cleanup(xml_data)

    # Rekey space
    key = confluence_interface.get_space_key(xml_data)
    rekey = confluence_interface.ask_yes_no(
        '\nFound space key \"{}\", would you like to change it? (Y/N): '.format(key)
        )
    if rekey:
        xml_data = confluence_interface.replace_space_key(xml_data)
        confluence_interface.write_descriptor_file(xml_data, args.xml)
        # Update key variable
        key = confluence_interface.get_space_key(xml_data)

    # Remove content restrictions (They cause problems applying permissions after import)
    answer = confluence_interface.ask_yes_no('\nRemove content restrictions (Recommended)? (Y/N): ')
    if answer:
        confluence_interface.output_info('Removing content restrictions.')
        xml_data = confluence_interface.remove_page_restrictions(xml_data)

    # Create new xml file for import
    confluence_interface.write_xml(xml_data, args.xml)

    # Metrics - Stop time and display elapsed
    confluence_interface.finish_message(start_time)

    # Copy log file to destination
    target_path = os.path.dirname(args.xml)
    timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    target_filename = os.path.join(target_path, key + '_' + timestamp + '.log')
    confluence_interface.copy_log(LOG_FILENAME, target_filename)
