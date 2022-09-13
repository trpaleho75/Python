#!python
"""
This module contains methods performing LDAP queries On-BEN.
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports - standard library
import logging
from ldap3 import Server, Connection


# Get logger
log = logging.getLogger(__name__)


def get_ldap_data(
    domain: str,
    username: str,
    password: str,
    ldap_server: str,
    search_base: str,
    filter_list: list,
    attributes: list
    ) -> (list):
    """
    Perform an encrypted ldap query using SSL (port 3269)
    
    Args:
        credentials: Credential dict for NTLM authentication to LDAP server
            {'domain':'', 'username':'', 'password':'', 'b64':''}
        ldap_server (str): The global catalog server to query.
        search_base (str): Distinguished name of component to query.
        search_filter (str): LDAP search filter.
        attributes (dict): Fields to return from query.
    
    Returns:
        (ldap3.abstract.entry.Entry) (list): list returned from query.
        If no results are retreived from a successful query a value of None will
        be returned.
    """
    
    server = Server(ldap_server, port = 3269, use_ssl = True)
    conn = Connection(server, user = f'{domain}\\{username}', 
        password = password)
    conn.bind()
    
    results = []
    for filter in filter_list:
        conn.search(
                search_base=search_base,
                search_filter=filter,
                attributes=attributes
            )
        if (len(conn.entries)) > 0:
            for entry in conn.entries:
                results.append(entry)
        else:
            log.error('No results returned from LDAP query.')

    conn.unbind()
    return results


def get_members(
    domain: str,
    username: str,
    password: str,
    ldap_server: str,
    group_dn: str
    ) -> (list):
    """
    Get members of a given group
    
    Args:
        credentials: Credential dict for NTLM authentication to LDAP server
            {'domain':'', 'username':'', 'password':'', 'b64':''}
        ldap_server (str): The global catalog server to query.
        search_base (str): Distinguished name of component to query.
        search_filter (str): LDAP search filter.
        attributes (dict): Fields to return from query.
        group_dn: DistinguishedName of group to query membership of
    
    Returns:
        list: list of member DNs
        If no results are retreived from a successful query a value of None will
        be returned.
    """

    search_filters = []
    search_filters.append('(objectClass=group)')

    ldap_attributes = [
        'member'
    ]

    ldap_response = get_ldap_data(domain, username, password, ldap_server,
        group_dn, search_filters, ldap_attributes)

    if len(ldap_response) == 1:
        return ldap_response[0].member.values
    else:
        return None
