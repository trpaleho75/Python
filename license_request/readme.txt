Automated User-Granting license on BEN (SDTEOB)
===============================================
The purpose of this project is to semi-automate the execution of service
requests granting license access to the SDTEOB applications. The steps 
executed are based on the following Confluence work instruction:
.. _SDE Internal Work Instructions:
	https://confluence-sdteob.web.boeing.com/pages/viewpage.action?pageId=21676608


Installation
------------
Required libraries
	requests
	ldap3
```
pip install requests, ldap3
```


File List
---------
readme.txt
license_request.py
insite.py
ldap_query.py
python_ldap-3.2.0-cp38-cp38-win_amd64.whl


Usage
-----
The input username is the person executing the script. You will be prompted for the password
mathing this user account. The account is used to perform an LDAP query against nos.boeing.com.

license_request.py --username[-u] '<domain\username>' --bemsid[-b] x, y, z, ...

```
python license_request.py --username 'ab\xy123z' --bemsid 1234567, 2345678, 3456789

python license_request.py -u 'ab\xy123z' -b 1234567, 2345678, 3456789
```

If the script hangs in git bash at runtime close the window and open a new instance. Run the 
following command prior to executing the script:
	alias python='winpty python.exe'
or add the command to your .bashrc


Output
------
Console: Valid and invalid users are displayed in tabular format
File: CSV file "license_request_<timestamp>.csv" output containing user findings.

Copy one or more windows IDs from the UserId column of the CSV into the ADUC members "Add..." dialog;
make sure to set "locations..." to "Entire Directory".