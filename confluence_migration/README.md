# Confluence Import/Export Tool

This script will parse usernames and keys from Confluence XML exports into CSV. The script then maps the usernames to the target system (CSV should be completed by program focal/delegate). NOTE: The last user record in the CSV is for remapping users that are no longer with the company or are no longer valid. The username in the remap_user's target_username field can be used whenever a key does not have a machine user in the target instance. When asked for credentials you must use an account that has permission to view users on the target instance.

This script will also allow you to change the key of an exported Confluence space. You will be asked if you would like to change the space's key.

You will be asked if you would like to remove content restrictions. Confluence does not import page restrictions correctly, leading to problems changing permissions or accessing spaces that have content restrictions. I recommend removing them prior to import by answering, (y)es when prompted.

## Installation

Prior to running the script ensure you have the following libraries:
[configure pip to download packages from SRES](https://git.web.boeing.com/artifactory/documentation/-/blob/master/python/README.md) **(link will not display in IE)**

| Dependency      | Tested Version |
| --------------- | -------------- |
| colorama        | 0.4.4          |
| lxml            | 4.7.1          |
| requests        | 2.25.1         |
| urllib3         | 1.26.7         |

```Shell
pip install colorama lxml requests urllib3
```

## Usage

_Run the script to create a user table for mapping:_

1. Extract the Confluence export zip file.
2. Run the script, providing the entities.xml file when prompted.
3. Follow the prompts to prepare the files for import.
4. The script will output a CSV file containing the usernames and keys of each user. The last line in the CSV file is a user named 'remap_user'. Enter a username to use when a key is unknown on the target instance.

_Run the script with a completed user table._

1. Run the script, providing the entities.xml file when prompted.
2. Provide the path to the completed UserTable.csv wehn prompted.
3. The script will backup any modified file, adding a .bak extension.
4. The new entities.xml, and exportDescriptor.properties if rekeyed, should be combined with the attachments folder and zipped for import.

### **Warning**

There is a quirk with git bash and getpass. This script will attempt to circumvent the problem but if you have issues and you're using git bash you may need to create the following alias.

```Shell
alias python='winpty python.exe'
```

or, add the command to your .bashrc and start a new instance

```Shell
vi .bashrc
alias python='winpty python.exe'
```

### **Note:**

If authentication to Confluence becomes an issue try this:
<https://confluence.atlassian.com/confkb/authentication_denied-error-when-accessing-confluence-content-via-rest-api-call-966681459.html>

If using a TempPass:
You may have to log into the SDTE Confluence instance and use the admin cog to enter your TempPass before this script will work properly.

## Output

A CSV file named _UserTable.csv_ will be created, after the first run, at the path contaning _entities.xml_. This file will contain the usernames and keys from the exported xml.
If a valid confluence instance responded, the CSV will also contain the full name of each user.

A log file _confluence.log_ is also created, in the script's source directory. The log contains details of the steps the script performed.
