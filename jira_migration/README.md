# Jira Migration Scripts

These scripts will assist in the migration of data from one instance of Jira to another. This does not import the CSV data for you. The intention here is to export as much data as possible from the source instance and format that data for import to another instance. The import script creates versions, components, a default scrum board and filter (delete if unnecessary), and sprints. Attachments must be uploaded to the server before the CSV in run through the Jira importer.

Use Jira date format: "d/M/y_H:m"

---

## Scripts

### General Note

- CSV columns "Last Comment" and "Last Worklog Comment" are re-formated copies of the most recent "Comment" and "Log Work" entries. There is no way to import these with the built-in CSV importer. Create a backup of the CSV and delete these columns prior to running this script to avoid problems. Scan the status and epic status columns before importing; non-existent statuses will fail the import, non-existent epic statuses will be created. Creation of non-existing epic statuses is an unexpected behavior and can lead to negative impact on other programs. Ensure that only existing epic statuses are in the CSV or at the very least select to map the field values during import.
- Sprints are exported by name, but imported by id.
- Epics are supposed to be imported by epic issue key or epic name, but we've found that only epic name is reliable.
- Epic statuses will be created if they don't exist. This is bad behavior and affects existing tenants. Import script validates that CSV values for Epic status are existing values for the given project or requests that you map to another value.

### jira_export.py

- This script parses the CSV file exported by Jira if provided, otherwise it will offer to export a project directly from Jira. Usernames, sprints, components, and versions will be written to csv files, "*OriginalCsvFile_TableName.csv*". Attachments can be downloaded from the source server. When downloading attachments this script re-creates the folder structure based on the attachment's path. When attachments are uploaded to Jira the files are renamed, leaving no way to reconnect attachments to their issues on the destination instance. By downloading the attachments instead of copying them from the server's datastore we are able to upload the attachments to the correct locations.
- If you have timeout issue exporting issues from Jira, try reducing the step size: PAGINATED_STEP = 250.
- The user exporting data will need the following permissions:
  - Project:
    - Browse Projects

### jira_import.py

- This is step two of the import script series. This script parses the main CSV file and associated CSV files (sprints, components, versions...) and creates relevant items in the target instance. If sprints are created you will have to run the post-import step after importing issues, in order to correctly status sprints. NOTE: you cannot set the sprint start and end dates via REST API. The planned start and end dates carry over, but not the actual start and end dates. This means that the sprint reports do not display as expected, there is no way to fix this.
- Please note that the direct attachment upload has not been re-integrated since a previous version where it existed. This feature is not yet available.
- A basic CSV Import configuration will be created for you during execution. This will configure the date format and project key for import. Once you map fields or values please save the configuration from the link at the bottom of the import status page, as it will have the additional mappings you configured during setup.

### Checklist Importing

- The jira_export.py script will create a *_Checklist.json file. This file is used as the input for the ChecklistImportAPIEndpoint.groovy script that is ran on the JIRA server via a Scriptrunner RESTendpoint. The API is restricted to SDTEOB_ENVIRONMENT_ADMINS. The API call occurs when selected in the post import section of the jira_import.py script. There are logs on the JIRA server that indicate success and the amount of issues affected.

### Screen Import

---

## Installation

Prior to running the script ensure you have the following libraries:
[configure pip to download packages from SRES](https://git.web.boeing.com/artifactory/documentation/-/blob/master/python/README.md) **(link will not display in IE)**

| Dependency      | Tested Version |
| --------------- | -------------- |
| colorama        | 0.4.4          |
| python-dateutil | 2.8.2          |
| requests        | 2.25.1         |
| tdqm            | 4.63.1         |
| urllib3         | 1.26.7         |

| Optional(Linux) | Tested Version |
| --------------- | -------------- |
| tkinter         | 8.5            |

A requirements.txt file is included. To install all required dependencies type the following command from the script folder:

~~~shell
pip3 install -r requirements.txt
~~~

or

~~~shell
pip install -r requirements.txt
~~~

The Python library tkinter is part of the standard library on Windows. If you want to use it in Linux you will have to install it. The following worked in my Amazon Workspace.

~~~Shell
sudo yum install python3-tkinter
~~~

---

## Usage

Run from command prompt

~~~shell
python -m <path to script>/jira_migration.py
~~~

~~~shell
./jira_migration.py
~~~

Linux

~~~shell
python3 jira_migration.py
~~~

---

### Warning

There is a quirk with git bash and getpass. This script incorporated this fix, but if you have issues and you're using git bash you may need to create the following alias.

~~~bash
alias python='winpty python.exe'
~~~

or, add the command to your .bashrc and start a new instance

~~~bash
vi .bashrc
alias python='winpty python.exe'
~~~

- There may be an error when writing some values to the log. You will see these displayed as UnicodeEncodeError:... There is a way to correct them in Python 3.9 by adding the encoding option to the logger format, but it is not present in 3.8 and I don't have a solution to fix it...yet. The error is safe to ignore and will not cause any additional errors.

- Using a personal access token(PAT) will not allow the script to elevate permissions without WebSudo. This means that any call with elevated permissions will return a 401 Permission Denied. For now this script will continue to use basic authentication.

- When mapping import fields, only Outward link types are allowed. Ignore the Inward link fields.

- Ran into issue with the field "Environment", there are two of them one is a label manager (custom field) the other is a system field. On the field mapping screen during import even when I selected the system field, it was importing the data to the custom field. I selected Environment, under System in the field drop list, but the saved config was still pointing to the custom field. Editing the saved config and entering "jira.field":"environment" fixed the problem. Just something to be aware of when you verify data after import. Always save the config file and log in case your import doesn't go as expected.

---

#### Formatting Notes

- angle brackets \<required argument>
- square brackets [optional argument]
- curly braces {default values}
- parentheses (miscellaneous info)

---
