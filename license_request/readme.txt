Automated User-Granting license on BEN (SDTEOB)
===============================================

The purpose of this project is to automate the execution of service requests
granting license access to the SDTEOB applications. The steps executed are
based on the following Confluence work instruction:
.. _SDE Internal Work Instructions:
	https://confluence-sdteob.web.boeing.com/pages/viewpage.action?pageId=21676608


Installation
------------

Python 3+ with 3rd party 'requests' package installed.
```
pip install requests
```
Powershell is required. Active Directory module will install automatically when
needed.

File List
---------
readme.txt
license_request.py
jira.py
insite.py
powershell.py
ActiveDirectory.ps1

Usage
-----

```
encode-b64.ps1 # Input Windows credentials, output b64 credentials to clipboard
python.exe driver_licenseRequest.py '<b64 encoded credentials(paste from encode-b64.ps1)>'
```


