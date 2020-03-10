#!/usr/bin/env python

__author__ = 'sp909e'
__copyright__ = 'Boeing (C) 2020, All rights reserved'
__license__ = 'Proprietary'
__status__ = 'development'

# Imports - built in
import argparse
import getpass
import datetime

# Imports - local or specific library 
import insite
import ldap_query


class Person:
	def __init__(self, userDataJson: dict):
		# Instance Attributes
		self.name = ''
		self.emailAddress = ''
		self.bemsid = ''
		
		self.company = ''
		self.exportStatus = ''
		self.cedDataSource = ''	

		self.validUser = False
		self.windowsId = ''
		
		self.setNameFromJson(userDataJson)
		self.setEmailAddressFromJson(userDataJson)
		self.setBemsidFromJson(userDataJson)
		
		self.setCompanyFromJson(userDataJson)
		self.setExportStatusFromJson(userDataJson)
		self.setCedDataSourceFromJson(userDataJson)
		
	def getName(self):
		return self.name
		
	def getEmailAddress(self):
		return self.emailAddress
		
	def getBemsid(self):
		return self.bemsid
	
	def getCompany(self):
		return self.company
	
	def getExportStatus(self):
		return self.exportStatus

	def getCedDataSource(self):
		return self.cedDataSource
	
	def getUserValidity(self):
		return self.validUser
	
	def getWindowsId(self):
		return self.windowsId
	
	def setName(self, name: str):
		self.name = name
	
	def setNameFromJson(self, json: dict):
		first = ''
		middle = ''
		last = ''
		first = json['resultholder']['profiles']['profileholder']['user']['firstName']
		try:
			middle = json['resultholder']['profiles']['profileholder']['user']['middleName']
		except:
			print('Middle name data not listed in inSite.')
		last = json['resultholder']['profiles']['profileholder']['user']['lastName']
		self.name = last + ', ' + first + ' ' + middle
		
	def setEmailAddress(self, emailAddress: str):
		self.emailAddress = emailAddress
	
	def setEmailAddressFromJson(self, json: dict):
		self.emailAddress = json['resultholder']['profiles']['profileholder']['user']['emailAddress']
		
	def setBemsid(self, bemsid: str):
		self.bemsid = bemsid

	def setBemsidFromJson(self, json: dict):
		self.bemsid = json['resultholder']['profiles']['profileholder']['user']['bemsId']
		
	def setCompany(self, company: str):
		self.company = company	
	
	def setCompanyFromJson(self, json: dict):
		self.company = json['resultholder']['profiles']['profileholder']['user']['company']

	def setExportStatus(self, exportStatus: str):
		self.exportStatus = exportStatus
	
	def setExportStatusFromJson(self, json: dict):
		self.exportStatus = json['resultholder']['profiles']['profileholder']['user']['usPersonStatusString']

	def setCedDataSource(self, cedDataSource: str):
		self.cedDataSource = cedDataSource
		
	def setCedDataSourceFromJson(self, json: dict):
		self.cedDataSource = json['resultholder']['profiles']['profileholder']['user']['cedDataSource']
	
	def setUserValidity(self):
		if (self.exportStatus).upper() == 'U. S. PERSON':
			self.validUser = True
	
	def setWindowsId(self, id: str):
		if (not id == None):
			self.windowsId = id

			
def getCredential(username: str) -> dict:
	password = getpass.getpass(prompt='Enter password for ' + username + ': ')
	return {"username" : username, "password" : password}
	

def OutputConsole(title: str, users: list) -> str:
	output = ''
	titleFormat = '{:^107}'
	output += titleFormat.format(title) + '\n'
	output += titleFormat.format('_' * 107) + '\n'
	headerFormat = '{:^25} {:^9} {:^8} {:^14} {:^25} {:^15} {:^5}'
	output += headerFormat.format('Name', 'BEMSID', 'UserId', 'Export', 'Company', 'CED', 'Valid') + '\n'
	output += headerFormat.format('-' * 25, '-' * 9, '-' * 8, '-' * 14, '-' * 25, '-' * 15, '-' * 5) + '\n'
	
	#rowFormat = '{:25.25} {:^9.9} {:^8.8} {:^14.14} {:^25.25} {:^15.15} {:^5.5}'
	rowFormat = '{:25.25} {:^9.9} {:^8.8} {:^14.14} {:^25.25} {:^15.15} {:^5.5}'
	for user in users:
		output += rowFormat.format(user.getName(), 
									user.getBemsid(), 
									user.getWindowsId(), 
									user.getExportStatus(),
									user.getCompany(), 
									user.getCedDataSource(), 
									'True' if (user.getUserValidity()) else 'False') + '\n'
	return output

	
def OutputCsv(users: list):
	output = ''
	csvFormat = '{},{},{},{},{},{},{}'
	output += csvFormat.format('Name', 'BEMSID', 'UserId', 'Export', 'Company', 'CED', 'Valid') + '\n'
	for user in users:
		output += csvFormat.format('\"' + user.getName() + '\"', 
							user.getBemsid(), 
							user.getWindowsId(), 
							user.getExportStatus(),
							user.getCompany(), 
							user.getCedDataSource(), 
							'True' if (user.getUserValidity()) else 'False') + '\n'
	timestamp = (datetime.datetime.now()).strftime('%Y%m%d-%I%M%S')
	outputFile = 'license_request_' + timestamp + '.csv'
	fileObject = open(outputFile, "w")
	fileObject.write(output)
	fileObject.close()

	
if __name__ == '__main__':
	# Parse command line arguments
	parser = argparse.ArgumentParser(description='Automated User-Granting license on BEN (SDTEOB).')
	parser.add_argument('--username', '-u', 
						help = 'quoted string \"domain\\username\". You will be prompted for a password.',
						action = 'store',
						required = True)
	parser.add_argument('--bemsid', '-b',
						help = 'Enter a comma separated list of BEMSIDs',
						action = 'store', nargs='+')
	args = parser.parse_args()
	
	credentials = {}
	if not (args.username == None):
		credentials = getCredential(args.username)
	
	# Configuration
	insiteUri = 'https://insite.web.boeing.com/'
	gc = 'ldap://nos.boeing.com:3268'
	baseDn = 'dc=boeing,dc=com'
	
	validUsers = []
	invalidUsers = []
	for id in args.bemsid:
		insiteJson = insite.getInsiteData(insiteUri, id)
		
		person = Person(insiteJson)
		person.setWindowsId(ldap_query.ldap3Query(credentials, gc, baseDn, person.getEmailAddress()))
		person.setUserValidity()
		
		if person.getUserValidity():
			validUsers.append(person)
		else:
			invalidUsers.append(person)
	
	if (len(validUsers) > 0):
		print(OutputConsole('Valid Users', validUsers))
		
	if (len(invalidUsers) > 0):
		print(OutputConsole('Invalid Users', invalidUsers))
	
	# Combine lists for csv output
	allUsers = []
	for user in validUsers:
		allUsers.append(user)
	for user in invalidUsers:
		allUsers.append(user)
	OutputCsv(allUsers)