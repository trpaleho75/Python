#!/usr/bin/env python3
"""
Module for AD integration.
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports - standard library
import logging
from time import perf_counter
from tqdm import tqdm

# Imports - 3rd party
from pyad import aduser, adgroup


# Get logger
log = logging.getLogger(__name__)


def get_user(
    windows_dn: str
    ) -> aduser:
    """
    Get the windows user object of the given distinguished name.

    Args:
        windows_dn: Distinguished name of AD user.

    Returns:
        AD User object
    """
    mark = perf_counter()
    user = None
    if not windows_dn is None:
        user = aduser.ADUser.from_dn(windows_dn)
    log.info(f'query took: {perf_counter() - mark} seconds')
    return user


def get_group(group_dn: str) -> adgroup:
    """
    Given an AD group's distinguished name, pull out the domain name and
    retrieve the group object. Return the group object, or None, if it does
    not exist.

    Args:
        group_dn: Distinguished name of AD group.

    Returns:
        AD group object
    """

    mark = perf_counter()
    # Parse domain and build server string
    server_name = '.'.join([part.split('=')[1] for part in group_dn.split(',') 
        if 'DC=' in part])

    ad_group = None
    ad_group = adgroup.ADGroup.from_dn(group_dn,
        options=dict(ldap_server=server_name))
    log.info(f'query took: {perf_counter() - mark} seconds')
    return ad_group


def add_members(
    group: adgroup,
    members: list,
    ) -> list:
    """
    Add user to group. Return list of users successfully added.

    Args:
        group(pyad.adgroup): pyad AD group object.
        members(list): List of pyad.aduser objects.
    
    Returns:
        (list): List of pyad.aduser objects that were successfully added.
    """

    mark = perf_counter()
    
    if group is None:
        return []
    
    if len(members) == 0:
        return []
    
    max_loop = 20
    description = f'Adding Members to {group.prefixed_cn}'
    progress_bar = tqdm(desc = description, total = len(members))
    unvalidated_members = members # Start with all users unvalidated
    while len(unvalidated_members) > 0 or max_loop > 0:
        mark2 = perf_counter()
        current_members = group.get_members()
        log.info(f'Current member query took: {perf_counter() - mark2} '
            f'seconds.')

        current_member_dn = [member.dn for member in current_members]
        unvalidated_members = [user for user in unvalidated_members if 
            not user.dn in current_member_dn] # Members not in group already
        if len(unvalidated_members) == 0:
            log.info('All members validated. Exiting loop.')
            progress_bar_next = len(members) - len(unvalidated_members)
            progress_bar.update(progress_bar_next - progress_bar.n)
            break
        mark3 = perf_counter()
        group.add_members(unvalidated_members)
        log.info(f'Add group members took: {perf_counter() - mark3} seconds.')
        progress_bar_next = len(members) - len(unvalidated_members)
        progress_bar.update(progress_bar_next - progress_bar.n)
        max_loop -= 1
    progress_bar.close()
    
    # Final list of users that were not validated
    unvalidated_member_dn = [member.dn for member in unvalidated_members] 
    log.info(f'Add member total operation: {perf_counter() - mark} seconds')
    return [user for user in members if not user.dn in unvalidated_member_dn]