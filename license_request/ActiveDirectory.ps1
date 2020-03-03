# Requires PowerShell -version 3

<#
.SYNOPSIS
	A set of functions that can be used to automate User-Granting licenses on BEN
  
.DESCRIPTION
	To automate the execution of service requests granting license access to the SDTEOB applications.
	The steps executed are based on the following Confluence work instruction:
	SDE Internal Work Instructions: https://confluence-sdteob.web.boeing.com/pages/viewpage.action?pageId=21676608
	
.PARAMETER IssueID
    The Jira issue ID associated with the current service request.
	
.PARAMETER Username
	The windows username of the user to be added to a group.
	
.PARAMETER ADGroup
	The Active Directory group name to add a user to.
	
.INPUTS

.OUTPUTS
	Log file <IssueID>.txt
  
.NOTES
	Version:        1.0
	Author:         sp909e
	Creation Date:  20200302
	Purpose/Change: Initial script development
  
.EXAMPLE
	ActiveDirectory.ps1 -IssueID "TEST-123" --Username "xy123z" --ADGroup "LICENSE_GROUP"
#>

[CmdletBinding()]

param (
	[Parameter(Mandatory=$true)]
	[string]$IssueId,

	[Parameter(Mandatory=$true)]
	[string]$Username,
	
	[Parameter(Mandatory=$true)]
	[string]$ADGroup
)


function logEntry {
	param (
		[Parameter(Mandatory=$true)]
		[string]$log,
		
		[Parameter(Mandatory=$true)]
		[string]$entry
	)
	
	If (-Not (Test-Path $log)) {
		Set-Content -Path $log -Value "$PSCommandPath"
	}
	
	$timeStamp = Get-Date -format "[yyyyMMdd-hhmmss]"
	Add-Content -Path $log -Value "$timeStamp $entry"
}


function validateUser {
	param (
		[string]$user
	)
	$domainControllers = (Get-ADForest).Domains
	$dc = $null
	ForEach ($domainController in $domainControllers) {
		$ADUserObject = (Get-ADUser `
						-LDAPFilter "(SAMAccountName=$user)" `
						-Server $domainController `
						-ErrorAction Continue)
		If ($ADUserObject) {
			$dc = $domainController
			logEntry $logfile "Found $user in Active Directory on $dc."
			return $ADUserObject
		}
	}
	logEntry $logfile "$user not found in Active Directory"
	return $null
}


function validateGroup {
	param (
		[string]$group
	)
	$domainControllers = (Get-ADForest).Domains
	$dc = $null
	ForEach ($domainController in $domainControllers) {
		$ADgroupObject = (Get-ADGroup `
							-LDAPFilter "(SAMAccountName=$group)" `
							-Server $domainController `
							-ErrorAction Continue)
		If ($ADgroupObject) {
			$dc = $domainController
			logEntry $logfile "Found $group in Active Directory on $dc."
			return $ADgroupObject
		}
	}
	logEntry $logfile "$group not found in Active Directory"
	return $null	
}


function addGroupMember {
	param (
		[Microsoft.ActiveDirectory.Management.ADGroup]$group,
		[Microsoft.ActiveDirectory.Management.ADUser]$user
	)
	If ($userObject -AND $groupObject) {
		logEntry $logFile "Adding user to group."
		Add-ADGroupMember -Identity $groupObject -Members $userObject -WhatIf # Simulated add, no actual changes will be made so verifyAdd will be false
		$verifyAdd = Get-ADGroupMember -Identity $groupObject | Where-Object -Property DistinguishedName -EQ $userObject.DistinguishedName
		If ($verifyAdd) {
			logEntry $logfile "User successfully added to group"
			return $true
		} Else {
			logEntry $logfile "User was not added to group"
			return $false
		}
	}
}
	

$logFile = "$issueId.txt"
$userObject = validateUser $Username $dc
$groupObject = validateGroup $ADGroup $dc
$result = addGroupMember $groupObject $userObject





