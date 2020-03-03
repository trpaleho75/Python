# Convert command line string to b64
$myCredentials = Get-Credential
$output = ([convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($myCredentials.Username + ':' + $myCredentials.GetNetworkCredential().password)))
Set-Clipboard -Value $output
Write-Host "Your b64 credential string has been copied to the clipboard."