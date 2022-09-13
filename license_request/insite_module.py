#!/usr/bin/env python3
"""
This class module contains methods for interaction with Boeing's inSite website.
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports - standard library
import logging
import sys
import time
from http import HTTPStatus
from json import loads

# Imports - 3rd party
import requests

# Imports - Local
import common_functions


# Get logger
log = logging.getLogger(__name__)


def get_insite_data(
    insite_uri: str,
    bemsid: str
    ) -> dict:
    """
    Query inSite for user data based on a given BEMSID.

    Parameters:
    insiteUri (str): Identifier(URL) of the inSite server.
    bemsid (str): Id number of user to query.

    Returns:
    JSON formatted dictionary of user information from inSite.
    """

    if bemsid == '':
        print('\nNo BEMSID received. Check request and retry.')
        return None

    insite_data = None
    rest_path = '/culture/service/boeingUserWebServiceJSON/'
    query = f'{insite_uri}{rest_path}bemsid?query={bemsid}'
    error = None
    for retry in range(common_functions.RETRIES):
        rest_response = requests.get(query, verify=False)

        if rest_response.status_code == HTTPStatus.OK:
            if (rest_response.text).find(bemsid):
                insite_data = loads(rest_response.text)
                break
        else:
            log.error(f'Response invalid, retry '
                f'{retry + 1}/{common_functions.RETRIES}:HTTP status code = '
                f'{rest_response.status_code}')
            if retry == (common_functions.RETRIES - 1):
                error = rest_response.content
            time.sleep(common_functions.SLEEP_SECONDS)
    if insite_data is None:
        print('\nInsite query failed, exiting. Check log for details.')
        log.error(error)
        sys.exit()
    return insite_data
