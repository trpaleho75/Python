# License request jira module

# Imports - built in
import json

# Imports - 3rd party
import requests

# Imports - local or specific library 
from requests.packages.urllib3.exceptions import InsecureRequestWarning # for testing
requests.packages.urllib3.disable_warnings(InsecureRequestWarning) # for testing


def getAllIssues(jiraUri: str, projectKey: str, issueStatus: str, componentName: str, b64Credential: str) -> list:
	headers = {'Authorization':'Basic ' + b64Credential}
	restPath = 'rest/api/2/search/'
	queryJql = ('?jql=project=' + projectKey + ' AND status=\'' + issueStatus + '\''\
				+ ' AND component = \'' + componentName + '\'&fields=key').replace(' ', '+')
	restResponse = requests.get(jiraUri + restPath + queryJql, headers = headers, verify = False)
	assert (restResponse.status_code == 200), 'getAllIssues REST response was not 200'
	jsonResponse = json.loads(restResponse.text)
	#issueCount = jsonResponse['total']
	issueCount = 5 # Response limiter for testing on closed issue status
	issues = []
	for key in range(issueCount):
		issues.append(jsonResponse['issues'][key]['key'])
	return issues

	
def getSingleIssue(jiraUri: str, issueId: str, b64Credential: str) -> dict:
	headers = {'Authorization':'Basic ' + b64Credential}
	restPath = 'rest/api/2/issue/'
	restResponse = requests.get(jiraUri + restPath + issueId, headers = headers, verify = False)
	assert (restResponse.status_code == 200), 'getSingleIssue REST response was not 200'
	jsonResponse = json.loads(restResponse.text)
	return jsonResponse
	

def getEpicFields(jiraUri, issueJson: str, b64Credential: str) -> list: # Returns [project key, story points]
	JIRA_EPIC_LINK = 'customfield_10100'
	JIRA_EPIC_NAME = 'customfield_10102'
	JIRA_STORY_POINTS = 'customfield_10106'
	
	epicFields = []
	epicLink = issueJson['fields'][JIRA_EPIC_LINK]
	epicName = getSingleIssue(jiraUri, epicLink, b64Credential)
	epicFields.append(epicName['fields'][JIRA_EPIC_NAME])
	epicFields.append(int(epicName['fields'][JIRA_STORY_POINTS]))
	return epicFields
	

def parseRecord(record: str, epicFields: list) -> list: # To Do: Add field validation checks
	name = ''
	email = ''
	winId = ''
	bemsid = ''
	role = ''
	projectKey = ''
	
	row = []
	for line in record.split('\n'):
		if line.find('=') >= 0:
			temp = line.split('=')
			if (temp[0].lower()).find('name') >= 0:
				name = temp[1]
			elif (temp[0].lower()).find('email') >= 0:
				email = temp[1]
			elif (temp[0].lower()).find('userid') >= 0:
				winId = temp[1]
			elif (temp[0].lower()).find('bemsid') >= 0:
				bemsid = temp[1]
			elif (temp[0].lower()).find('application') >= 0:
				role = temp[1]
	row.append(name.strip())
	row.append(email.strip())
	row.append(winId.strip())
	row.append(bemsid.strip())
	row.append(role.strip())
	row.append(epicFields[0])
	return row

	
def parseRequest(issueJson: str, epicFields: list) -> list: # Returns array of license requests from Jira issue
	jiraDescription = issueJson['fields']['description']
	nameCount = jiraDescription.count('Name=')
	requestStart = 0
	requestEnd = 0
	requests = []
	
	for name in range(nameCount):
		requestStart = jiraDescription.find('Name=', requestStart)
		nextRequest = jiraDescription.find('Name=', requestStart + 1)
		if nextRequest >= 0:
			requestEnd = nextRequest
		else:
			requestEnd = len(jiraDescription)
		parsedDescription = jiraDescription[requestStart:requestEnd]
		parsedRecord = parseRecord(parsedDescription, epicFields)
		requests.append(parsedRecord)
		requestStart = requestEnd
	return requests

	
def setComment(jiraUri: str, issueId: str, b64Credential: str, comment: str):
	headers = {'Authorization':'Basic ' + b64Credential, 'Accept':'application/json', 'Content-Type':'application/json'}
	restPath = 'rest/api/2/issue/' + issueId + '/comment'
	postData = {"body": comment}
	payload = json.dumps(postData)
	restResponse = requests.post(jiraUri + restPath, data = payload, headers = headers, verify = False)
	assert (restResponse.status_code == 201), 'setComment REST response was not 201'
	
	