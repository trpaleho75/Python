#!python
"""Confluence import module for SDTEOB"""


# Imports - Standard Library
import csv
import base64
import getpass
import glob
import http
import json
import logging
import os
import shutil
import sys
import time
import tkinter
from tkinter.filedialog import askopenfilename
import types

# Imports - 3rd party
import colorama
import requests
from requests.exceptions import ConnectionError as requests_ConnectionError
from tqdm import tqdm
# Supress errors when certificate is not provided
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from lxml import etree


# Global variables
processed_target_keys = []


# Configure logging
log = logging.getLogger(__name__)

RETRIES = 3

INFO = 'INFO'
WARNING = 'WARNING'
ERROR = 'ERROR'

SERVER_NAME_INDEX = 0
SERVER_URL_INDEX = 1
JIRA_PRODUCTION = ['SDTE Production', 'https://confluence-sdteob.web.boeing.com']
JIRA_PREPRODUCTION = ['SDTE Pre-Production', 'https://confluence-sdteob-pp.web.boeing.com']
JIRA_DEVELOPMENT = ['SDTE Development', 'https://confluence-sdteob-dev.web.boeing.com']
JIRA_MONARCH = ['SDTE Monarch', 'https://confluence.monarch.altitude.cloud']
JIRA_DEVSTACK = ['DevStack', 'https://devstack.ds.boeing.com/confluence']


# Functions
def get_user_input() -> types.SimpleNamespace:
    """
    Get required information to start migration.
        * Conlfuence export
        * Source server url
        * Certificate file (Optional)

    Returns:
        dict: {'file':'', 'url':'', 'cert':''}
    """

    # Get server url and verify it is reachable
    url = None
    while not validate_url(url, None):
        # Build table of servers for menu
        table_title = 'Jira Servers'
        table_columns = ['#', 'Name', 'URL']
        option_other = ['OTHER', 'Enter your own URL']
        url_list = [
            JIRA_MONARCH,
            JIRA_PRODUCTION,
            JIRA_PREPRODUCTION,
            JIRA_DEVELOPMENT,
            JIRA_DEVSTACK,
            option_other
        ]
        count = 1
        table_dataset = []
        for server in url_list:
            table_dataset.append([count, server[SERVER_NAME_INDEX], server[SERVER_URL_INDEX]])
            count += 1
        print_table(table_title, table_columns, table_dataset)
        # Get user selection
        user_selection = ''
        while user_selection not in range(len(url_list)):
            user_selection = input('Select the destination Jira server (Enter number): ')
            try:
                user_selection = int(user_selection) - 1  # 0 offset for list indexing
            except ValueError as exception_details:
                output_message(ERROR, 'Invalid input: {}'.format(exception_details))
        if (user_selection) == url_list.index(option_other):
            url = input('Enter URL: ')
        else:
            url = url_list[user_selection][SERVER_URL_INDEX]

    # Get certificate file and validate that it exists, not that it's valid.
    cert = False
    if 'https' in url:
        if ask_yes_no('Do you have a certificate file for SSL verification? (Y/N): '):
            cert_file = get_file('Select Certificate File', [['Cert Files', '*.cer *.crt']])
            if os.path.exists(cert_file):
                cert = cert_file

    # dict = {'file': filename, 'url': url, 'cert': cert}
    args = types.SimpleNamespace(url=url, cert=cert)
    return args


def get_credentials(namespace: types.SimpleNamespace) -> types.SimpleNamespace:
    """
    Get credentails from user for authentication to the target server.

    Args:
        namespace: Namespace containing common data. [offline, url, cert]

    Returns:
        (SimpleNamespace): Adds credential data to args namespace
            namespace.b64 = base 64 encoded 'username:password' for basic auth.
            namespace.username = username
            namespace.password = password
    """

    user = input('Enter login: ')
    passwd = getpass.getpass()

    b64_credential = base64.b64encode(
        ('{}:{}'.format(user, passwd)).encode('ascii')
    ).decode('utf-8')

    namespace.b64 = b64_credential
    namespace.username = user
    namespace.password = passwd
    return namespace


def get_file(window_title: str, search_filter: list) -> str:
    """
    Display a file dialog and ask the user the select their desired file.

    Args:
        window_title(str): Title for the file dialog window.
        search_filter(list): list of lists to filter for. [['filter name','*.extentsion'],...]
            Single filter: [['CSV files','*.csv']]
            Multiple selectable filters: [['CSV files','*.csv'],['Excel files','*.xls *.xlsx']]

    Returns:
        (str): Path and filename.
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


def print_table(title: str, columns: list, dataset: list):
    """
    Print table header.
    -----------
       Title
    -----------
    col col col
    --- --- ---
    val val val
    -----------

    Args:
        columns (list): list of column headers.
        dataset (list): list of lists containing rows of data.
    """

    # Find column widths
    table_width = len(title)  # Initial table width will be title width
    column_widths = []
    for col in columns:  # Establish array
        column_widths.append(len(str(col)))
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
            table += '{:{}}'.format(col, column_widths[col_count])
            if len(row) > col_count + 1:
                table += ' '
            else:
                table += '\n'
            col_count += 1
    print(table)


def output_message(severity: str, message: str):
    """
    Write message to log and console. Messages color coded to indicate severity on console.

    Args:
        severity: log level [info, warn, error]
        message: string to output.
    """

    colorama.init(autoreset=True)
    # Output message
    if severity == INFO:
        log.info(message.replace('\n',''))
        print(colorama.Fore.WHITE + '{}'.format(message))
    elif severity == WARNING:
        log.warning(message.replace('\n',''))
        print(colorama.Fore.YELLOW + '{}: {}'.format(WARNING, message))
    elif severity == ERROR:
        log.error(message.replace('\n',''))
        print(colorama.Fore.RED + '{}: {}'.format(ERROR, message))


def create_session(b64_credentials: str, certificate: str) -> requests.Session:
    """
    Create http session using the requests library.

    Args:
        b64_credentials(str): b64 encoded credentials for basic auth.
        certificate(str): Certificate file for SSL/TLS verification.

    Returns:
        (requests.Session): HTTP Session object.
    """

    output_message(INFO, '\nEstablishing HTTP session.\n')
    session = requests.Session()
    headers = {
        "Accept": "application/json",
        "Authorization": 'Basic {}'.format(b64_credentials),
        "Content-Type": "application/json"
    }
    for header in headers:
        session.headers[header] = headers.get(header)
    session.verify = certificate
    return session


def output_info(message: str):
    """
    Write same message to log and console.

    Args:
        message: string to output.
    """

    log.info(message)
    print(message)


def ask_yes_no(question: str) -> bool:
    """
    Ask a yes/no question and return the boolean equivalent.

    Args:
        question(str): Question to pose to user.

    Returns:
        (bool) True if yes, otherwise False.
    """

    ask = ''
    answer = False
    while ask not in ['Y', 'y', 'N', 'n']:
        ask = (input('{}'.format(question))).lower()
    if 'y' in ask.lower():
        answer = True
    return answer


def validate_url(url: str, certificate: str) -> bool:
    """
    Check URL for a valid response. This only verifies that a resource is available.
    This function does not test authentication or validate that a REST path is valid.

    Args:
        url: Url for testing
        certificate: Certificate package to use for SSL/TLS verification.

    Returns:
        Bool: True if URL is accessible.
    """

    log.info('Validating URL = %s', url)

    if not certificate:
        certificate = False
        disable_warnings(InsecureRequestWarning)
        log.warning('Certificate not provided, SSL Verification disabled.')

    is_valid = False
    if url is not None:
        try:
            rest_response = requests.get(url, verify=certificate)
            log.info('URL returned status code (%s).', rest_response.status_code)
            is_valid = bool(rest_response.status_code == http.HTTPStatus.OK)
        except requests_ConnectionError as error_message:
            log.error('Cannot reach %s, Error = %s', url, error_message)
            print('Could not contact server: %s', url)
    return is_valid


def read_users_from_xml(xml: etree._Element) -> dict:
    """
    Search XML file for user entities.
    User entry begins, <object class="ConfluenceUserImpl" package="com.atlassian.confluence.user">,
    and ends with a closing </object> tag. The element contains the user's key
    as well as the username and lower case username. The lowercase name is not used here.
    By adding users to a dictionary we garantee a unique list of users.

    Args:
        xml: xml data to search in.

    Returns:
        dict: {source_username:{source_key, target_username, target_key}}
    """

    users_dict = {}
    count = 0
    target_xpath = '//object[@class=\"ConfluenceUserImpl\"]'
    result_set = xml.xpath(target_xpath)
    user_count = len(result_set)
    output_message(INFO, 'Found {} user entries, parsing user data.'.format(user_count))

    description = 'Parsing users from xml'
    for element in tqdm(xml.xpath(target_xpath), desc=description):
        key = element.find('id').text  # First child element
        name = element.find('property').text  # Second child element

        if key not in users_dict.keys():
            users_dict[name] = {'source_key':key, 'target_username':None, 'target_key':None}
            log.info('user_dict, add %s = %s', key, name)
            count += 1
    return users_dict


def read_users_from_csv(filename: str) -> dict:
    """
    Get users in CSV file.

    Args:
        filename: path and/or filename containing the user table.

    Returns:
        dict: {source_username:{source_key, target_username, target_key}}
    """

    users_dict = {}

    with open(filename) as csv_file:
        log.info('Reading CSV file: %s', filename)

        csv_data = []
        csv_reader = csv.reader(csv_file, delimiter=',')
        for row in csv_reader:
            csv_data.append(row)

        record_count = 0

        description = 'Parsing users from xml'
        for user in tqdm(csv_data, desc=description):
            if csv_data.index(user) != 0:  # Ignore header row
                user_record = {
                    'source_key': user[1],
                    'target_username':user[2],
                    'target_key': user[3]
                    }
                users_dict[user[0]] = user_record
            record_count += 1

        log.info('%d users read from csv.', record_count - 1)
    return users_dict


def user_dict_to_csv(input_dict: dict, filename: str, name: str = ''):
    """
    Writes a user dictionary to csv file.

	Args:
		input_dict: formatted dictionary data.
		filename: filename to export.
		name: string to append to filename.
    """

    # Get user table and set up backup
    input_path = os.path.split(filename)[0]
    input_file = os.path.split(filename)[1]
    if name != '':
        input_file = '{}.csv'.format(name)
    bakup_count = len(glob.glob1(input_path, '{}*.bak'.format(input_file)))
    backup_file = '{}.bak'.format(input_file)
    if bakup_count != 0:  # Add number to backup file if necessary.
        backup_file = '{}({}).bak'.format(input_file, bakup_count + 1)
    if os.path.exists(os.path.join(input_path, input_file)):
        source_file = os.path.join(input_path, input_file)
        target_file = os.path.join(input_path, backup_file)
        os.rename(source_file, target_file)
        log.info('backed up %s to %s', source_file, target_file)
    output_file = os.path.join(input_path, input_file)

    # Prepare output
    try:
        with open(output_file, 'w', newline='') as csv_file:
            log.info('Writing users to csv: %s', csv_file.name)
            csv_writer = csv.writer(
                    csv_file,
                    delimiter=',',
                    quotechar='"',
                    quoting=csv.QUOTE_MINIMAL
                )

            # Header row
            column_list = [
                    'source_username',
                    'source_key',
                    'target_username',
                    'target_key'
                ]
            csv_writer.writerow(column_list)

            # Body rows
            for key in input_dict:
                csv_writer.writerow( [
                    key, # Key = source_username
                    input_dict[key].get('source_key'),
                    input_dict[key].get('target_username'),
                    input_dict[key].get('target_key')
                    ] )

            if "remap_user" not in input_dict.keys():
                csv_writer.writerow(
                        [
                        'remap_user',
                        '',
                        '<username>',
                        ''
                        ]
                    )
        output_info('User info written to output file: {}'.format(output_file))
    except PermissionError:
        log.error('Cannot access file: %s', output_file)
        sys.exit('Cannot access file, file may be in use.')


def get_user_info(
    session: requests.Session,
    server: str,
    user: str,
    user_record: dict,
    lookup_field: str
    ) -> dict:
    """
    Get confluence user record with matching key/username.

    Args:
        session: http session object to connect with.
        server: URL to connect to.
        user: user to search for.
        user_record: user record to update.
        lookup_field: lookup using key or username.

    Returns:
        dict containing updated user record.
    """

    rest_path = '/rest/api/user'
    lookup_value = None
    query_url = None

    if lookup_field == 'key':
        lookup_value = user_record.get('source_key')
        query_url = '{}{}?key={}'.format(server, rest_path, lookup_value)

    if lookup_field == 'username':
        if user_record.get('target_key') == '':
            lookup_value = user_record.get('target_username').strip()
            if lookup_value:
                query_url = '{}{}?username={}'.format(server, rest_path, lookup_value)
            else:
                log.info(
                    'No target username. User will be remapped. Target key = {}'\
                    .format(user_record.get('target_username'))
                    )
        else:
            log.info('Skipping, \'%s\', key already acquired.', user)

    if not query_url is None:
        log.info('Submitting URL: %s', query_url)

        for i in range(RETRIES):
            rest_response = session.get(query_url)
            log.info('loop (%d), rest_response: %s', i, rest_response)
            if rest_response.status_code == 200:
                json_response = json.loads(rest_response.text)
                if lookup_field == 'key':
                    user_record.update(
                        {'full_name':json_response.get('displayName')}
                        )
                    log.info('Updated entry from key query = %s', user_record)
                if lookup_field == 'username':
                    user_record.update(
                        {'target_key':json_response.get('userKey')}
                        )
                    log.info('Updated entry from username query = %s', user_record)
                break
            elif rest_response.status_code == 404:
                log.warning(
                    '%s, %s, not found on server %s. HTTP response: %s',
                    lookup_field,
                    lookup_value,
                    server,
                    rest_response.text
                    )
            elif rest_response.status_code == 401:
                log.error(
                    '%s, %s, Invalid login, check Confluence %s. HTTP response: %s',
                    lookup_field,
                    lookup_value,
                    server,
                    rest_response.text
                    )
                sys.exit('Invalid login.')
            else:
                log.error('Error querying url: %s. HTTP response: %s', server, rest_response.text)
    return user_record


def read_xml(xml_file: str) -> etree._Element:
    """
    Read XML file

    Args:
        xml_file: input filename.

    Returns:
        lxml etree._Element containing the input xml.
    """

    xml_in_root = None
    if os.path.exists(xml_file):
        output_info('Reading XML file: {}'.format(xml_file))
        try:
            xml_parser = etree.XMLParser(huge_tree = True) # Added due to possible huge input
            xml_in_tree = etree.parse(xml_file, xml_parser)
            xml_in_root = xml_in_tree.getroot()
        except Exception as exception_message:
            output_message(ERROR, 'Error reading the xml file. {}'.format(exception_message))
    return xml_in_root


def replace_user_elements(
    xml: etree._Element,
    target_xpath: str,
    users: dict,
    remap: bool
    ) -> etree._Element:
    """
    Update the user entries in the XML file. There must be only one entry per user.

    This function must run before updating user key elements or users will not be created properly.

    Args:
        xml: input xml.
        target_xpath: search path.
        users: dict of users
        remap: perform a remap or not

    Returns:
        Updated XML
    """

    log.info('Parsing user elements')
    for element in xml.xpath(target_xpath):
        user_id = None
        for child in element.iterchildren():
            if child.get('name') == 'key': # Key is first child element
                for user_index in users:
                    if child.text == users[user_index].get('source_key'):
                        if not users[user_index].get('target_key') == '':
                            user_id = user_index
                            child.text = users[user_id].get('target_key')
                            break
            elif (child.get('name') == 'name' and not user_id is None):
                child.text = users[user_id].get('target_username')
            elif (child.get('name') == 'lowerName' and not user_id is None):
                child.text = (users[user_id].get('target_username')).lower()
        if user_id is None and not remap:
            log.warning('Removing duplicate user entry for user %s', element[2].text)
            element.getparent().remove(element)
    return xml


def update_user_key_elements(
    xml: etree._Element,
    target_xpath: str,
    users: dict,
    remap: bool
    ) -> etree._Element:
    """
    Find and replace user keys.

    Args:
        xml: input xml.
        target_xpath: search path.
        users: dict of users
        remap: perform a remap or not

    Returns:
        Updated XML.
    """

    log.info('Updating user keys.')

    description = 'Updating user keys'
    for element in tqdm(xml.xpath(target_xpath), desc=description):
        for user_index in users:
            if element.text == users[user_index].get('source_key'):
                if not users[user_index].get('target_key') == '':
                    element.text = users[user_index].get('target_key')
                elif remap:
                    remap_user_key = users['remap_user'].get('target_key')
                    if remap_user_key:
                        element.text = remap_user_key
                    else:
                        output_message(
                            ERROR,
                            'Error: No key found for remap_user. '\
                            'This user must be an existing valid user. '\
                            'Update remap_user before running script again.'
                            )
                        sys.exit('See log for details.')
                else:
                    log.warning('Remap False: element \"%s\" will not be updated', element.text)
    log.info('Finished updating user keys.')
    return xml


def update_cdata_elements(xml: etree._Element) -> etree._Element:
    """
    Tag elements in list as CDATA in XML output.

    Args:
        xml: input xml.

    Returns:
        Updated XML.
    """

    log.info('Formatting CDATA elements.')
    # Attribute names represented as CDATA
    cdata_attribute_names = [
        'allUsersSubject',
        'body',
        'code',
        'contentStatus',
        'context',
        'creator',
        'destinationPageTitle',
        'destinationSpaceKey',
        'entityName',
        'group',
        'groupName',
        'key',
        'labelableType',
        'lastModifier',
        'lowerDestinationPageTitle',
        'lowerDestinationSpaceKey',
        'lowerKey',
        'lowerName',
        'lowerTitle',
        'lowerUrl',
        'name',
        'namespace',
        'owningUser',
        'pluginModuleKey',
        'pluginVersion',
        'receiver',
        'relationName',
        'sourceContent',
        'stringVal',
        'stringValue',
        'textVal',
        'title',
        'type',
        'url',
        'user',
        'userSubject',
        'value',
        'versionComment'
        ]

    description = 'Formatting CDATA elements'
    for element in tqdm(xml.iter(), desc=description):
        if element.get('name') in cdata_attribute_names:
            if not element.text is None:
                element.text = etree.CDATA(element.text)
    log.info('Finished updating CDATA elements.')
    return xml


def replace_mention(xml: etree._Element, target_xpath: str, users: dict) -> etree._Element:
    """
    Find and replace mention links.

    Args:
        xml: input xml.
        target_xpath: search path.
        users: dict of users
        remap: perform a remap or not

    Returns:
        Updated XML.
    """

    user_entries = {user: users.get(user) for user in users if user != 'remap_user'}
    user_remap = {user: users.get(user) for user in users if user == 'remap_user'}

    log.info('Updating @mentions.')
    description = 'Updating @mentions'
    for element in tqdm(xml.xpath(target_xpath), desc=description):
        if element.text is None:
                # No text in element body, continue.
                continue
        for user in user_entries:
            if users[user].get('source_key') in element.text:
                if users[user].get('target_key') != '':
                    element.text = (element.text).replace(
                        users[user].get('source_key'),
                        users[user].get('target_key')
                        )
                elif users[user].get('target_key') == '' and not user_remap.get('target_key') is None:
                    element.text = (element.text).replace(
                        users[user].get('source_key'),
                        user_remap['remap_user'].get('target_key')
                        )
                else:
                    log.info(
                        'Line %s, keeping user %s.',
                        str(element.sourceline),
                        users[user].get('source_key')
                        )
                    # No change to element.text
    log.info('Finished updating mentions.')
    return xml


def replace_links(xml: etree._Element, target_xpath: str, target_url: str) -> etree._Element:
    """
    Find and replace links.

    Args:
        xml: input xml.
        target_xpath: search path.
        users: dict of users
        remap: perform a remap or not

    Returns:
        Updated XML.
    """

    log.info('Updating links.')
    link_count = 0

    description = 'Counting links'
    for element in tqdm(xml.xpath(target_xpath), desc=description):
        if '<a href=' in element.text:
            link_count += 1

    if link_count > 0:
        source_url = input('HTML links found. Enter source confluence URL: ')
        description = 'Updating links'
        for element in tqdm(xml.xpath(target_xpath), desc=description):
            element.text = (element.text).replace(source_url, target_url)
        log.info('Finished updating links.')
    else:
        log.info('No links found in XML.')
    return xml


def get_space_key(xml: etree._Element) -> str:
    """
    Search for and return the space key from the XML input.

    Args:
        xml(etree._Element): XML input.

    Returns:
        (str): The key for the exported space.
    """

    search_xpath = '//object[@class=\"Space\"]'
    space_key = None
    # Find existing key
    for element in xml.xpath(search_xpath):
        for child in element.iterfind('property'):
            if child.get('name') == 'key':
                space_key = child.text
    if space_key is None:
        output_message(ERROR, 'Could not isolate key from XML.')
        quit()
    return space_key


def replace_space_key(xml: etree._Element) -> etree._Element:
    """
    Replace a space's key.

    Args:
        xml: Input xml.

    Returns:
        Updated XML
    """

    search_xpath = '//object[@class=\"Space\"]'
    space_key = None
    new_key = None

    # Replace space key
    for element in xml.xpath(search_xpath):
        for child in element.iterfind('property'):  # Find existing key
            if child.get('name') == 'key':
                space_key = child.text
                new_key = (input('Enter new key: ')).upper()
                if new_key is None:
                    log.error('invalid key entered')
                    sys.exit('Invalid key entered. No changes will be made.')
                else:
                    log.info('Found space with key %s, replacing with %s', space_key, new_key)
                    child.text = new_key
            if child.get('name') == 'lowerKey':
                child.text = new_key.lower()

    # Find all "spaceKey":"<key>" references and re-key them.
    #<object class="BucketPropertySetItem" package="bucket.user.propertyset">
    search_xpath = '//object[@class=\"BucketPropertySetItem\"]'
    for element in xml.xpath(search_xpath):
        for child in element.iterfind('property'):  # Find existing key
            if child.get('name') == 'textVal':
                if not child.text is None:
                    if 'spaceKey' in child.text:
                        child.text = (child.text).replace(
                                '\"spaceKey\":\"{}\"'.format(space_key),
                                '\"spaceKey\":\"{}\"'.format(new_key)
                            )

    # Check for sidebar.nav
    search_xpath = '//object[@class=\"ConfluenceBandanaRecord\"]'
    for element in xml.xpath(search_xpath):
        for child in element.iterfind('property'):
            if child.get('name') == 'context':
                child.text = new_key

    return xml


def write_descriptor_file(xml_data: etree._Element, filename: str):
    """
    Update key in descriptor file.

    Args:
        xml_data: Content of xml file read into etree._Element.
        filename: filename of source xml file, used to locate descriptor.
    """

    # Locate space key
    search_xpath = '//object[@class=\"Space\"]'
    space_key = None
    for element in xml_data.xpath(search_xpath):
        for child in element.iterfind('property'):  # Find existing key
            if child.get('name') == 'key':
                space_key = child.text

    # Get exportDescriptor.properties file
    input_file = '{}/exportDescriptor.properties'.format(os.path.split(filename)[0])
    if not os.path.exists(input_file):
        message = f"No export descriptor file found. Manually update key to {space_key} if necessary!"
        log.warning(message)
        print(message)
        return
    bak_count = len(glob.glob1(os.path.split(input_file)[0], 'exportDescriptor.properties*.bak'))
    backup_file = '{}.bak'.format(input_file)
    if bak_count != 0:
        backup_file = '{}({}).bak'.format(input_file, bak_count + 1)
    os.rename(input_file, backup_file)
    output_file = input_file

    # Replace key in descriptor file
    with open(output_file, 'a') as outfile:
        with open(backup_file, 'r') as infile:
            for line in infile:
                if 'spaceKey' in line:
                    outfile.write('spaceKey={}\n'.format(space_key))
                    log.info('Replaced key in exportDescriptor.properties')
                else:
                    outfile.write(line)
    output_info('exportDescriptor.properties written to output file: {}'.format(output_file))


def write_xml(xml_data: etree._Element, filename: str):
    """
    Write output to XML file.

    Args:
        xml_data: Content of xml file read into etree._Element.
        filename: Absolute path to input xml file.
    Returns:
        etree._Element: updated xml content.
    """

    output_info('Writing XML to file.')
    input_path = os.path.split(filename)[0]
    input_file = os.path.split(filename)[1]
    bakup_count = len(glob.glob1(input_path, '{}*.bak'.format(input_file)))
    backup_file = '{}.bak'.format(input_file)
    if bakup_count != 0:  # Add number to backup file if necessary.
        backup_file = '{}({}).bak'.format(input_file, bakup_count + 1)
    os.rename(filename, os.path.join(input_path, backup_file))
    output_file = filename

    try:
        with open(output_file, 'wb') as xml_file:
            # xml_file.write(output)
            tree = etree.ElementTree(xml_data)
            tree.write(xml_file, encoding='UTF-8')
    except IOError as e:
        log.error('IOError: %s', e)
    output_info('XML written to output file: {}'.format(output_file))


def xml_cleanup(xml_data: etree._Element) -> etree._Element:
    """
    Check for and remove duplicate entities.

    Args:
        xml_data: content of xml file read into etree._Element.

    Returns:
        etree._Element: updated xml content.
    """

    # Search for and remove duplicate relationship elements.
    relationships = {}
    search_xpath = '//object[@class=\"User2ContentRelationEntity\"]'
    for element in xml_data.xpath(search_xpath):
        property_target_content_id = None
        property_source_content_id = None
        property_relationname_text = None

        for child in element.iterchildren():
            if len(child) == 0:
                if child.get('name') == 'relationName':
                    property_relationname_text = child.text
            else:
                for grandchild in child.iterchildren():
                    if child.get('name') == 'targetContent' and \
                            grandchild.get('name') == 'id':
                        property_target_content_id = grandchild.text
                    if child.get('name') == 'sourceContent' and \
                            grandchild.get('name') == 'key':
                        property_source_content_id = grandchild.text

        if property_target_content_id and property_source_content_id and property_relationname_text:
            if not property_target_content_id in relationships:
                # New targetContent id
                relationships[property_target_content_id] = \
                        {property_relationname_text: \
                        [property_source_content_id]}
            else:
                # Existing targetContent id
                if not property_relationname_text in \
                        relationships[property_target_content_id]:
                    # New relationName
                    relationships[property_target_content_id] \
                            [property_relationname_text] = \
                            [property_source_content_id]
                else:  # Existing relationName
                    if not property_source_content_id in \
                            relationships[property_target_content_id] \
                            [property_relationname_text]:
                        # New user key
                        relationships[property_target_content_id] \
                                [property_relationname_text].append \
                                (property_source_content_id)
                    else:  # Existing user key
                        # Delete entity
                        # add log entry for deletions
                        element.getparent().remove(element)
        else:
            output_info(
                'Unexpected value processing element {} at {}. '\
                'property_target_content_id=\"{}\", property_source_content_id=\"{}\", '\
                'property_relationname_text=\"{}\"'
                .format(
                    element,
                    element.sourceline,
                    property_target_content_id,
                    property_source_content_id,
                    property_relationname_text
                    )
                )
    return xml_data


def remove_duplicate_users(xml_data: etree._Element) -> etree._Element:
    """
    Search for all users. Add each user's key to a dict. If a user is already
    in the list, it's a duplicate. Delete any duplicate users.

    Args:
        xml_data: content of xml file read into etree._Element.

    Returns:
        etree._Element: updated xml content.
    """

    users = {}
    search_xpath = '//object[@class=\"ConfluenceUserImpl\"]'
    for element in xml_data.xpath(search_xpath):
        for child in element.iterchildren():
            if len(child) == 0:
                if child.get('name') == 'key':
                    if not child.text in users:
                        users[child.text] = None
                    else:
                        element.getparent().remove(element)
                        log.info('Removing duplicate entry for %s', child.text)
    return xml_data


def remove_page_restrictions(xml_data: etree._Element) -> etree._Element:
    """
    Search for any page restrictions and delete them. Page restrictions do not import correctly
    and will prevent permissions from being applied properly to the target instance.

    Args:
        xml_data: content of xml file read into etree._Element.

    Returns:
        etree._Element: updated xml content.
    """

    search_xpath = '//object[@class=\"ContentPermissionSet\"]'
    for element in xml_data.xpath(search_xpath):
        element.getparent().remove(element)
        log.info('Removing page restriction entry on line, %d', element.sourceline)
    return xml_data


def copy_log(source_filename: str, target_filename: str) -> str:
    """
    Copy a file from one location to another.
    """

    result = shutil.copy(source_filename, target_filename)
    return result



def finish_message(start_time: float):
    """
    Display finish message and elapsed run time

    Args:
        start_time: Time script started
    """

    elapsed_time = time.time() - start_time
    hours = divmod(elapsed_time, 3600)
    minutes = divmod(hours[1], 60)
    seconds = minutes[1]
    message = '{} finished, elapsed time (h:m:s): {:0>2}:{:0>2}:{:0>2}\n'\
        .format(os.path.basename(__file__), int(hours[0]), int(minutes[0]), int(seconds))
    log.info(message)
    print(message)
