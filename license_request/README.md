Automated User-Granting license on BEN (SDTEOB)
===============================================

Automate the provisioning of User-granting licenses for the SDTEOB toolchain. There is a lot of string matching going on in the script. This is inherently a bit fragile as its prone to user error when entering data. I will continue to try to make it more robust as time permits.

NOTES

-----

Installation

-----

*Prior to running pip install, configure pip to download packages from SRES:
Follow Instructions
[HERE](https://git.web.boeing.com/artifactory/documentation/-/blob/master/python/README.md)*

Dependencies (Verified versions):

* colorama (0.4.4)
* ldap3  (2.9)
* pyad  (0.6.0)
* pywin32 (301)
* requests (2.25.1)

```bash
pip install colorama ldap3 jira pyad pywin32 requests
```

Specific versions of libraries can be installed using "[library]==[version]" syntax:

```bash
pip install pyad==0.6.0
```

Usage
-----

You will be prompted for your domain, username, and password at runtime. Jira will be queried for license requests and then the script will attempt to process each request. If a request fails to be processed completely it will be moved to blocked for user review. If a request is unable to be parsed you can edit the request and run the script again.

If the license request has a spreadsheet attached, ensure that the spreadsheet contains BEMSID and "Needed Applications" columns. Save the spreadsheet as a CSV. When prompted, enter path to the csv file. *Suggestion: Name csv file after the issue key to avoid confusion when processing multiple requests (i.e. SDTEPROG-xxxx.csv).* **See sample CSV file SDTEPROG-sample.csv**

* General form: python license_request.py --cert[-c] [path to certificate file]

```bash
python license_request.py --cert[-c] "Boeing_Basic_Assurance_Software_Root_CA_G2.cer"
```

Output
------

Results are both displayed in the console and output to "license_request.log" in the script's root.

**Console**: users are displayed in a table with any invalid user's status in red.

```bash
$ python ./license_request.py

-------------------------------------------------------------------------------------------------------------------------
                                                   (x/y) SDTEPROG-xxxx                                                   
-------------------------------------------------------------------------------------------------------------------------
 Program             Name             Export St.       Company         CED     Role                Group(s)
---------- ------------------------- ------------ ------------------ -------- ------- -----------------------------------
  ABCDE        Doe (US), John J.     U. S. PERSON The Boeing Company   bps      All   SDTEOB_LIC_GEN_ABCDE_USERS
```

After displaying the table, you will be prompted to confirm whether you want to make these changes to Active Directory (AD).

```bash
Do you wish to make these changes? (Y/N):
```

Answering yes will commit the AD changes. Results will be added to the issue's comment section; True = membership confirmed, False = No Action performed or failed to add user. In the event of a failure, or an invalid user is found, the request will be transitioned to blocked for further review. If all user's are confirmed the issue will be closed.

**Warning**
-----------

There is a quirk with git bash and getpass. This script will attempt to circumvent the problem, but if you have issues and you're using git bash you may need to create the following alias.

```bash
alias python='winpty python.exe'
```

or, add this command to your .bashrc and start a new instance

```bash
vi .bashrc
alias python='winpty python.exe'
```
