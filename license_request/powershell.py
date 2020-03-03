#!python

# Imports - built in
import subprocess

def setGroupMember(issueId, windowsId, adGroup): # Call associated powershell script to add user to Active Directory group
	commandArgs = ('PowerShell.exe', '-Command', '.\\ActiveDirectory.ps1 -IssueId "' + issueId + '" -Username "' + windowsId +'" -ADGroup "' + adGroup + '"')
	proc = subprocess.call(commandArgs)
	return proc