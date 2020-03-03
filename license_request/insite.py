# License request inSite module

# Imports - built in
import json

# Imports - 3rd party
import requests

# Imports - local or specific library 
from requests.packages.urllib3.exceptions import InsecureRequestWarning # for testing
requests.packages.urllib3.disable_warnings(InsecureRequestWarning) # for testing


def getInsiteData(insiteURI: str, bemsid: str) -> dict:
	restPath = 'culture/service/boeingUserWebServiceJSON/'
	query = 'bemsid?query='
	restResponse = requests.get(insiteURI + restPath + query + bemsid, verify=False)
	return json.loads(restResponse.text)
	

def getCompany(json) -> str:
	return json['resultholder']['profiles']['profileholder']['user']['company']
	
	
def getExportStatus(json) -> bool:
	return json['resultholder']['profiles']['profileholder']['user']['usPersonStatusString']


def getCedDataSourceType(json) -> str:
	return json['resultholder']['profiles']['profileholder']['user']['cedDataSource']
	

def getBemsidFromWindowsID(insiteURI: str, windowsId: str) -> str:
	restPath = 'culture/service/boeingUserWebServiceJSON/'
	query = 'userid?query='
	if windowsId.find('\\') >= 0:
		windowsId = (windowsId.split('\\'))[1]
	restResponse = requests.get(insiteURI + restPath + query + windowsId, verify=False)
	jsonResponse = json.loads(restResponse.text)
	try:
		bemsid = jsonResponse['resultholder']['profiles']['profileholder']['user']['bemsId']
	except:
		bemsid = ''
		print('Windows Id validation error. Verify user has a windows account')
	return bemsid
	