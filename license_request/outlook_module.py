#!/usr/bin/env python3
"""
Outlook interface
"""


__copyright__ = 'Boeing (C) 2021, All rights reserved'
__license__ = 'Proprietary'


# Imports
import win32com.client as win32


def send_email(
    subject: str,
    body_text: str = '',
    body_html: str = '',
    recipients: list = [],
    recipients_cc: list = [],
    recipients_bcc: list = [],
    attachments: list = []
    ):
    """
    Send email through Outlook

    Args:
        subject: Subject string.
        body_text: Text body content (if not using HTML), use blank string to skip.
        body_html: HTML content for email body.
        recipients: List of email addresses for To:
        recipients_cc: List of email addresses for CC:
        recipients_bcc: List of email addresses for BCC:
        attachments: list of filenames to attach.
    """

    outlook = win32.Dispatch('outlook.application')
    mail = outlook.CreateItem(0)

    mail.To = add_recipients(recipients)
    mail.CC = add_recipients(recipients_cc)
    mail.BCC = add_recipients(recipients_bcc)
    mail.Subject = subject
    mail.Body = body_text
    mail.HTMLBody = body_html

    # To attach a file to the email (optional):
    for attachment in attachments:
        mail.Attachments.Add(attachment)

    mail.Send()


def add_recipients(recipients: list) -> str:
    """
    Add recipients from list to string

    Args:
        recipients: list of email addresses
    
    Returns:
        String of email adresses separated by semicolons
    """

    recipients_to = ''
    for recipient in recipients:
        # Validate address format: name@domain.ext
        if '@' in recipient and '.' in recipient:
            if recipients.index(recipient) == 0:
                recipients_to = recipient
            else:
                recipients_to += '; {}'.format(recipient)
    return recipients_to


def parse_template(template_file: str) -> dict:
    """
    Parse subject and body from email template. Expected format is "Subject: ... Body: ..."

    Args:
        template_file: filename string
    
    Returns:
        Dict: {'subject':'', 'body': ''}
    """

    # If script path is not cwd then use absolute path.
    template_file_obj = open(template_file, 'r')
    template_text = template_file_obj.read()
    
    search_string = 'Subject:'
    subject_start = template_text.index(search_string) + len(search_string)
    search_string = 'Body:'
    subject_end = template_text.index(search_string)
    subject = template_text[subject_start:subject_end]
    subject = subject.strip()

    search_string = 'Body:'
    body_start = template_text.index(search_string) + len(search_string)
    body = template_text[body_start:]
    body = body.strip()

    return {'subject': subject, 'body': body}
