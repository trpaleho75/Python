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
		startIndex = windowsId.find('}')
		if startIndex >= 0:
			windowsId = windowsId[startIndex + 1:windowsId.rfind('{')]
		
		startIndex = windowsId.find('*') 
		if startIndex >= 0:
			windowsId = windowsId[startIndex + 1:windowsId.rfind('*')]
		
		startIndex = windowsId.find('\\')
		if startIndex >= 0:
			windowsId = windowsId[startIndex + 1:len(windowsId)]
		
		self.windowsId = windowsId		
		
	def setBemsid(self, bemsid: str):
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
	

	def setUserValidity(self, insiteURI: str):
		if ((self.getExportStatus()).upper() == 'U. S. PERSON' \
			and insite.getBemsidFromWindowsID(insiteURI, self.windowsId) == self.bemsid):
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
	

	def tableHeader(self):
		headerFormat = '{:^15}{:^10}{:^25}{:^35}{:^12}{:^12}{:^30}{:^65}{:^30}{:^16}{:^10}{:^6}'
		print('\n')
		print(headerFormat.format('Story','Project','Name','Email','WinId','BEMSID','Role','AD Group(s)','Company','Export Status','CED','Valid'))
		print(headerFormat.format('-' * 14,'-' * 9,'-' * 24,'-' * 34,'-' * 11,'-' * 11,'-' * 29,'-' * 64,'-' * 29,'-' * 15,'-' * 9,'-' * 6))

		
	def toTable(self):
		tableFormat = '{:15}{:^10}{:25}{:<35}{:^12}{:^12}{:30}{:65}{:^30}{:^16}{:^10}{:^6}'
		tableHeader()
		print(tableFormat.format(self.issueId, \
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
		

if __name__ == '__main__':
	# Parse command line arguments
	parser = argparse.ArgumentParser(description='Automated User-Granting license on BEN (SDTEOB).')
	parser.add_argument('credential', help = 'Enter your b64 encoded credential string',
						action = 'store')
	args = parser.parse_args()
	b64Credential = args.credential
	
	# Configuration
	jiraURI = 'https://jira-sdteob.web.boeing.com/'
	jiraCert = ''
	jiraProject = 'SDTEPROG'
	#jiraStatus = 'To Do'
	jiraStatus = 'Closed' # For testing when no new issues are available
	jiraComponent = 'License-Request'
	insiteURI = 'https://insite.web.boeing.com/'

	projects = [] # To Do: Get Confluence and Epic story points and compare to AD totals
	serviceRequests = jira.getAllIssues(jiraURI, jiraProject, jiraStatus, jiraComponent, b64Credential)
	assert len(serviceRequests) > 0, 'No service requests found.'
	for request in serviceRequests:
		peopleAccept = []
		peopleReject = []
		
		requestJiraData = jira.getSingleIssue(jiraURI, request, b64Credential)
		epicFields = jira.getEpicFields(jiraURI, requestJiraData, b64Credential)
		projects.append(Project(epicFields[0], epicFields[1]))
		users = jira.parseRequest(requestJiraData, epicFields)
		
		for user in users:
			myPerson = Person(user, request)
			myPerson.setIssueId(request)
			
			requestInsiteData = insite.getInsiteData(insiteURI, myPerson.getBemsid())
			myPerson.setCompany(insite.getCompany(requestInsiteData))
			myPerson.setExportStatus(insite.getExportStatus(requestInsiteData))
			myPerson.setCedDataSource(insite.getCedDataSourceType(requestInsiteData))
			myPerson.setGroups()
			
			myPerson.setUserValidity(insiteURI)
			if myPerson.getUserValidity() == True:
				peopleAccept.append(myPerson)
			else:
				peopleReject.append(myPerson)
		
		# Report results to Jira
		commentFormat = '{}, added to group(s): {}\n'
		acceptedUsers = ''
		for person in peopleAccept:
			acceptedUsers += commentFormat.format(person.getName(), str(person.getGroups()))
			for group in person.getGroups():
				powershell.setGroupMember(person.getIssueId(), person.getWindowsId(), group)
		print(acceptedUsers)
		# jira.setComment(jiraURI, request, b64Credential, acceptedUsers)
		
		commentFormat = '{}, not added to group(s): {}\n'
		rejectedUsers = ''
		for person in peopleReject:
			rejectedUsers += commentFormat.format(person.getName(), str(person.getGroups()))
		print(rejectedUsers)
		# jira.setComment(jiraURI, request, b64Credential, rejectedUsers)
	