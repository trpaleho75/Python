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
	
.PARAMETER adGroup
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
	ActiveDirectory.ps1 -issueId "TEST-123" --Username "xy123z" --adGroup "LICENSE_GROUP"
#>

[CmdletBinding()]

param (
	[Parameter(Mandatory=$true)]
	[string]$issueId,

	[Parameter(Mandatory=$true)]
	[string]$username,
	
	[Parameter(Mandatory=$true)]
	[string]$adGroup
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
	Write-Debug "validateUser().`$user=$user"
	
	$domainControllers = (Get-ADForest).Domains
	$dc = $null
	ForEach ($domainController in $domainControllers) {
		$adUserObject = (Get-ADUser `
						-LDAPFilter "(SAMAccountName=$user)" `
						-Server $domainController `
						-ErrorAction Continue)
		If ($adUserObject) {
			$dc = $domainController
			logEntry $logfile "Found $user in Active Directory on $dc."
			return $adUserObject
		}
	}
	logEntry $logfile "$user not found in Active Directory"
	return $null
}


function validateGroup {
	param (
		[string]$group
	)
	Write-Debug "validateGroup().`$group=$group"
	
	$domainControllers = (Get-ADForest).Domains
	$dc = $null
	ForEach ($domainController in $domainControllers) {
		$adGroupObject = (Get-ADGroup `
							-LDAPFilter "(SAMAccountName=$group)" `
							-Server $domainController `
							-ErrorAction Continue)
		If ($adGroupObject) {
			$dc = $domainController
			logEntry $logfile "Found $group in Active Directory on $dc."
			return $adGroupObject
		}
	}
	logEntry $logfile "$group not found in Active Directory"
	return $null	
}


function addGroupMember {
	param (
		[Microsoft.ActiveDirectory.Management.adGroup]$group,
		[Microsoft.ActiveDirectory.Management.ADUser]$user
	)
	Write-Debug "addGroupMember().`$group=$group"	
	Write-Debug "addGroupMember().`$user=$user"
	
	$groupObject = validateGroup $group
	$userObject = validateUser $user
	
	If ($userObject -AND $groupObject) {
		Write-Debug "addGroupMember().`$userObject -And `$groupObject evaluate True"
		
		logEntry $logFile "Adding user to group."
		Add-ADGroupMember -Identity $groupObject -Members $userObject -WhatIf # Simulated add, no actual changes will be made so verifyAdd will be false

		$globalCatalog = 'nos.boeing.com' # Add dynamic search for GC
		$verifyAdd = (Get-ADGroup `
			-Identity $groupObject `
			-Server $globalCatalog `
			-Properties Members `
			| Select-Object -ExpandProperty Members).contains($userObject.DistinguishedName)
		Write-Debug "addGroupMember().`$verifyAdd=$verifyAdd"
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
$result = addGroupMember $adGroup $username

If ($result) {
	Exit 0
} Else {
	Exit 1
}




