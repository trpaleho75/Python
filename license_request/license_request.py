#!python

"""
	Description:
	The purpose of this project is to automate the execution of service requests granting license access to the SDTEOB
	applications. The steps executed are based on the following Confluence work instruction:
	SDE Internal Work Instructions:
		https://confluence-sdteob.web.boeing.com/pages/viewpage.action?pageId=21676608
	
	Input:
	There is one required command line argument, a base64 encoded string consisting of 'username:password'. This
	string can be obtained from the included PowerShell or Bash scripts, encode-b64.ps1 and encode-b64.sh.
	
	# Future Work
	API
		main
		package
	Error handling
	Peer Review
	Merge
	Unit tests
	usage/man page
	arg parse
	
	InSite input bemsid return us person and company affiliation
	Encapsulate into api
	
	determine lists for valid vs invalid and notification of failure
	possible comment back to Jira
	
	optional:
	check license pool before importing
	report: count allocated licenses
	get forcasted user licenses (story points in epic)
	***
"""

__author__ = 'sp909e'
__copyright__ = 'Boeing (C) 2020, All rights reserved'
__license__ = 'Proprietary'
__email__ = 'travis.l.holt@boeing.com'
__status__ = 'development'


# Imports - built in
import argparse


# Imports - local or specific library 
import jira
import insite
import powershell


class Person:
	"""This class represents a single user"""
	# Constant userData indices
	FULLNAME = 0
	EMAIL = 1
	WINDOWSID = 2
	BEMSID = 3
	ROLE = 4
	PROJECTKEY = 5

		
	def __init__(self, userData: list, issueId: str):
		# Instance Attributes
		self.issueId = ''
		self.projectKey = ''
		self.name = ''
		self.emailAddress = ''
		self.windowsId = ''
		self.bemsid = ''
		self.role = ''
		
		self.company = ''
		self.exportStatus = ''
		self.cedDataSource = ''	
	
		self.groups = []
		self.validUser = False
		
		self.groups.clear()
		self.setIssueId(issueId)
		self.setProjectKey(userData[self.PROJECTKEY])
		self.setName(userData[self.FULLNAME])
		self.setEmailAddress(userData[self.EMAIL])
		self.setWindowsId(userData[self.WINDOWSID])
		self.setBemsid(userData[self.BEMSID])
		self.setRole(userData[self.ROLE])
		
	
	def getIssueId(self):
		return self.issueId
	
	
	def getProjectKey(self):
		return self.projectKey
		
	
	def getName(self):
		return self.name

		
	def getEmailAddress(self):
		return self.emailAddress
		
		
	def getWindowsId(self):
		return self.windowsId
		
		
	def getBemsid(self):
		return self.bemsid
		
		
	def getRole(self):
		return self.role

	
	def getCompany(self):
		return self.company
	

	def getExportStatus(self):
		return self.exportStatus


	def getCedDataSource(self):
		return self.cedDataSource
		
		
	def getGroups(self):
		return self.groups
		
		
	def getUserValidity(self):
		return self.validUser

		
	def setIssueId(self, issueId: str):
		self.issueId = issueId
	
	
	def setProjectKey(self, projectKey: str):
		self.projectKey = projectKey
		
	
	def setName(self, name: str):
		self.name = name

		
	def setEmailAddress(self, emailAddress: str):
		charIndex = emailAddress.find('mailto') - 1 # extract just email from [user@domain.ext|mailto:user@domain.ext]
		if charIndex >= 0:
			emailAddress = emailAddress[1:charIndex] # Start at 1 to remove leading bracket
		self.emailAddress = emailAddress
		
		
	def setWindowsId(self, windowsId: str):
		findIndex = windowsId.find('}')
		if findIndex >= 0:
			windowsId = windowsId[findIndex + 1:windowsId.rfind('{')]
		
		findIndex = windowsId.find('*') 
		if findIndex >= 0:
			windowsId = windowsId[findIndex + 1:windowsId.rfind('*')]
		
		findIndex = windowsId.find('\\')
		if findIndex >= 0:
			windowsId = windowsId[findIndex + 1:len(windowsId)]
		
		self.windowsId = windowsId		
		
	def setBemsid(self, bemsid: str):
		findIndex = bemsid.find('[')
		if findIndex >= 0:
			bemsid = bemsid[findIndex + 1:len(bemsid)]
			
		findIndex = bemsid.find('|')
		if findIndex >= 0:
			bemsid = (bemsid[0:findIndex]).strip()

		self.bemsid = bemsid


	def setRole(self, role: str):
		self.role = role

		
	def setCompany(self, company: str):
		self.company = company


	def setExportStatus(self, exportStatus: str):
		self.exportStatus = exportStatus


	def setCedDataSource(self, cedDataSource: str):
		self.cedDataSource = cedDataSource

		
	def setGroups(self):
		cnLeft = 'SDTEOB_LIC'
		cnRight = '_USERS'
		cnExt = '_EXT'
		cnGen = '_GEN'
		cnDev = '_DEV'
		genGroup = cnLeft \
			+ ('' if (self.cedDataSource).lower() == 'eclascon' or (self.cedDataSource).lower() == 'bps' else cnExt) \
			+ cnGen \
			+ '_' + self.projectKey \
			+ cnRight
		self.groups.append(genGroup)
		if (self.role).lower().find('dev') >= 0:
			devGroup = genGroup.replace(cnGen, cnDev)
			self.groups.append(devGroup)
	

	def setUserValidity(self, insiteUri: str):
		if ((self.getExportStatus()).upper() == 'U. S. PERSON' \
			and insite.getBemsidFromWindowsId(insiteUri, self.windowsId) == self.bemsid):
				self.validUser = True

				
	def toString(self):
		stringFormat = '{},{},{},{},{},{},{},{},{},{},{},{}'
		print(stringFormat.format(self.issueId, \
								self.projectKey, \
								self.name, \
								self.emailAddress, \
								self.windowsId, \
								self.bemsid, \
								self.role, \
								str(self.groups), \
								self.company, \
								self.exportStatus, \
								self.cedDataSource, \
								'True' if (self.validUser) else 'False'))
								
								
class Project:
	projectKey = ''
	storyPoints = ''
	pointsUsed = ''
	
	def __init__(self, projectKey, storyPoints):
		self.setProjectKey(projectKey)
		self.setStoryPoints(storyPoints)
	
	
	def getProjectKey(self):
		return self.projectKey

		
	def getStoryPoints(self):
		return self.storyPoints

		
	def getPointsUsed(self):
		return self.pointsUsed
		

	def setProjectKey(self, projectKey):
		self.projectKey = projectKey

		
	def setStoryPoints(self, storyPoints):
		self.storyPoints = storyPoints

		
	def setPoints(self, points):
		self.pointsUsed = points
		

def outputCsv(userList: list, listName: str):
	outputFile = listname + '.csv'
	fileObject = open(outputFile, "a")
	lines = fileObjects.readlines()
	if lines <= 0:
		csvFormat = '{},{},{},{},{},{},{},{},{},{},{},{}'
		fileObject.write(stringFormat.format('IssueId','ProjectKey','Name','EmailAddress','Windows Username','BEMSID','Role','AD Groups','Company','Export Status','CED Source','Valid'))
	for user in userList:
		fileObject.write(user.toString())
	fileObject.close()
	
	
if __name__ == '__main__':
	# Parse command line arguments
	parser = argparse.ArgumentParser(description='Automated User-Granting license on BEN (SDTEOB).')
	parser.add_argument('credential', help = 'Enter your b64 encoded credential string.',
						action = 'store')
	args = parser.parse_args()
	b64Credential = args.credential
	
	# Configuration
	jiraUri = 'https://jira-sdteob.web.boeing.com/'
	jiraCert = ''
	jiraProject = 'SDTEPROG'
	jiraStatus = 'Closed' # 'To Do'
	jiraComponent = 'License-Request'
	insiteUri = 'https://insite.web.boeing.com/'

	projects = [] # To Do: Get Confluence and Epic story points and compare to AD totals
	
	serviceRequests = jira.getAllIssues(jiraUri, jiraProject, jiraStatus, jiraComponent, b64Credential)
	assert len(serviceRequests) > 0, 'No service requests found.'
	
	for request in serviceRequests:
		peopleAccept = []
		peopleReject = []
		
		requestJiraData = jira.getSingleIssue(jiraUri, request, b64Credential)
		epicFields = jira.getEpicFields(jiraUri, requestJiraData, b64Credential)
		projects.append(Project(epicFields[0], epicFields[1]))
		users = jira.parseRequest(requestJiraData, epicFields)
		
		for user in users:
			myPerson = Person(user, request)
			myPerson.setIssueId(request)
			
			requestInsiteData = insite.getInsiteData(insiteUri, myPerson.getBemsid())
			myPerson.setCompany(insite.getCompany(requestInsiteData))
			myPerson.setExportStatus(insite.getExportStatus(requestInsiteData))
			myPerson.setCedDataSource(insite.getCedDataSourceType(requestInsiteData))
			myPerson.setGroups()
			
			myPerson.setUserValidity(insiteUri)
			if myPerson.getUserValidity() == True:
				peopleAccept.append(myPerson)
			else:
				peopleReject.append(myPerson)
		
		# Add accepted users to group
		commentFormat = '{}, added to group(s): {}\n'
		acceptedUsers = ''
		userAddResult = ''
		for person in peopleAccept:
			acceptedUsers += commentFormat.format(person.getName(), str(person.getGroups()))
			for group in person.getGroups():
				userAddResult = powershell.setGroupMember(person.getIssueId(), person.getWindowsId(), group)
				print(userAddResult)
		print(acceptedUsers)
		# jira.setComment(jiraUri, request, b64Credential, acceptedUsers)
		
		commentFormat = '{}, not added to group(s): {}\n'
		rejectedUsers = ''
		for person in peopleReject:
			rejectedUsers += commentFormat.format(person.getName(), str(person.getGroups()))
		print(rejectedUsers)
		# jira.setComment(jiraUri, request, b64Credential, rejectedUsers)
	