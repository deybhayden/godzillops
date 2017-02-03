# -*- coding: utf-8 -*-
"""google.py - Google API methods

The GoogleAdmin class serves as an interface to Google APIs for interacting
with Google Admin SDK for creating users and managing groups.

Attributes:
    GOOGLE_GROUP_TAGS (tuple[str]): List of supported google group POS tags
    PASSWORD_CHARACTERS (str): All possible password characters used in generating
        random user passwords.
    PASSWORD_LENGTH (int): The default generated password length.
    SCOPES (list[str]): Google API Scopes to create authorized tokens against. If
        modifying these scopes, delete your previously saved credentials located in
        your system's temporary directory - they'll be named something
        like 'google-api-python-client-discovery-doc.cache'
"""
import base64
import logging
import mimetypes
import os
import random
import string
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from apiclient.errors import HttpError
from apiclient.discovery import build
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials

GOOGLE_GROUP_TAGS = ('GDEV', 'GDES', 'GCRE', 'GFOU')
PASSWORD_CHARACTERS = string.ascii_letters + string.punctuation + string.digits
PASSWORD_LENGTH = 18
SCOPES = ['https://www.googleapis.com/auth/admin.directory.domain.readonly',
          'https://www.googleapis.com/auth/admin.directory.user',
          'https://www.googleapis.com/auth/admin.directory.group',
          'https://www.googleapis.com/auth/gmail.send',
          'https://www.googleapis.com/auth/calendar']


class GoogleAdmin(object):
    """GoogleAdmin class is a more usable interface to googleapiclient

    This class takes a couple configuration pieces - service account keys & super admin account - and
    returns a class instance capable of doing basic google user management.
    """
    def __init__(self, service_account_json, sub_account, calendar_id, welcome_text, welcome_attachments):
        """Initialize Google API Service Interface

        Given a service account json object and super admin account email from Google Apps Domain,
        this function initializes the GoogleAdmin class by creating a Google Admin SDK API service object.

        Args:
            service_account_json (dict): Parsed JSON Key File for a Google Service Account
            sub_account (str): The super admin account to act on behalf of
            calendar_id (str): The company calendar to add new users to as readers
            welcome_text (str): Customizable welcome email text for each new account
            welcome_attachments (list): Customizable list of files to attach to welcome email
        """
        credentials = ServiceAccountCredentials._from_parsed_json_keyfile(service_account_json, SCOPES)
        delegated_creds = credentials.create_delegated(sub_account)
        http = delegated_creds.authorize(Http())
        self.sub_account = sub_account
        self.calendar_id = calendar_id
        self.admin_service = build('admin', 'directory_v1', http=http)
        self.gmail_service = build('gmail', 'v1', http=http)
        self.cal_service = build('calendar', 'v3', http=http)
        self.primary_domain = self._get_primary_domain()
        self.welcome_text = welcome_text
        self.welcome_attachments = welcome_attachments

    def create_user(self, given_name, family_name, username, personal_email, job_title, groups):
        """Create a new Google user and add him/her to the list of groups passed.

        Args:
            given_name (str): First name of new user
            family_name (str): Last name of new user
            username (str): Used for the primary email handle / Google username.
            personal_email (str): Personal email address - used to send new login credentials to
            job_title (str): Job title of new user
            groups (list): List of google group names determined by GZChunker
        """
        email = '{}@{}'.format(username, self.primary_domain)
        emails = [{'address': email, 'primary': True, 'type': 'work'},
                  {'address': personal_email, 'type': 'other'}]
        orgs = [{'primary': True, 'title': job_title}]
        password = self._generate_password()

        logging.info("Creating new google account - {}".format(email))
        response = (self.admin_service.users()
                                      .insert(body={'name': {'givenName': given_name,
                                                             'familyName': family_name},
                                                    'password': password,
                                                    'changePasswordAtNextLogin': True,
                                                    'primaryEmail': email,
                                                    'emails': emails,
                                                    'organizations': orgs})
                                      .execute())

        yield 'User created! Going to add them to the following groups now: *{}*'.format(', '.join(groups))
        for group in groups:
            group_key = '{}@{}'.format(group, self.primary_domain)
            logging.info("Adding {} to the '{}' group".format(email, group_key))
            (self.admin_service.members()
                               .insert(groupKey=group_key,
                                       body={'email': email,
                                             'role': 'MEMBER'})
                               .execute())

        logging.info("Adding {} to the '{}' calendar".format(email, self.calendar_id))
        (self.cal_service.acl().insert(calendarId=self.calendar_id,
                                       body={'role': 'reader',
                                             'scope': {'type': 'user', 'value': email}})
                               .execute())

        yield 'Sending them a welcome email to their personal address with login credentials to the new account.'
        logging.info('Emailing {} the credentials of the new google account'.format(given_name))
        message_text = """
Hello {given_name},

You have a new account at {domain}
Account details:

Username
{username}

Password
{password}

Start using your new account by signing in at https://www.google.com/accounts/AccountChooser?Email={email}&continue=https://apps.google.com/user/hub
{welcome_text}""".format(domain=self.primary_domain, welcome_text=self.welcome_text, **locals())

        message = self._create_message(personal_email, 'Welcome to {}'.format(self.primary_domain), message_text, self.welcome_attachments)
        # Send message as super admin
        self.send_message('me', message)

    def _create_message(self, to, subject, message_text, message_attachments):
        """Create a message for an email.

        Args:
            to: Email address of the receiver.
            subject: The subject of the email message.
            message_text: The text of the email message.
            message_attachments: List of files to attach to email

        Returns:
            An object containing a base64url encoded email object.
        """
        message = MIMEMultipart()
        message['to'] = to
        message['from'] = self.sub_account
        message['subject'] = subject

        msg = MIMEText(message_text)
        message.attach(msg)

        for attachment in message_attachments:
            content_type, encoding = mimetypes.guess_type(attachment)
            if content_type is None or encoding is not None:
                content_type = 'application/octet-stream'

            main_type, sub_type = content_type.split('/', 1)
            if main_type == 'text':
                with open(attachment, 'rb') as fp:
                    msg = MIMEText(fp.read(), _subtype=sub_type)
            elif main_type == 'image':
                with open(attachment, 'rb') as fp:
                    msg = MIMEImage(fp.read(), _subtype=sub_type)
            elif main_type == 'audio':
                with open(attachment, 'rb') as fp:
                    msg = MIMEAudio(fp.read(), _subtype=sub_type)
            else:
                with open(attachment, 'rb') as fp:
                    msg = MIMEBase(main_type, sub_type)
                    msg.set_payload(fp.read())

            filename = os.path.basename(attachment)
            msg.add_header('Content-Disposition', 'attachment', filename=filename)
            message.attach(msg)

        return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}

    def send_message(self, user_id, message):
        """Send an email message.

        Args:
          user_id: User's email address. The special value "me"
          can be used to indicate the authenticated user.
          message: Message to be sent.

        Returns:
          Sent Message.
        """
        message = (self.gmail_service.users().messages()
                                     .send(userId=user_id,
                                           body=message)
                                     .execute())
        logging.info('Sent Message Id: {}'.format(message['id']))
        return message

    def is_username_available(self, username):
        """Check if a username is available in the primary domain.

        Args:
            username (str): Google username / email handle

        Returns:
            bool: If the name is available, return True, False otherwise
        """
        email = '{}@{}'.format(username, self.primary_domain)
        try:
            self.admin_service.users().get(userKey=email).execute()
            # Executed without error, meaning this user already exists
            return False
        except HttpError:
            # Error was raised since the user isn't found, meaning it's available
            return True

    def _generate_password(self):
        """Generate a random password comprised of PASSWORD_LENGTH PASSWORD_CHARACTERS.

        Returns:
            str: A randomly generated password.
        """
        return ''.join(random.choice(PASSWORD_CHARACTERS)
                       for _ in range(PASSWORD_LENGTH))

    def _get_primary_domain(self):
        """Get the primary domain for this Google Account.

        Returns:
            str: The primary domain of the google account.
        """
        domains = (self.admin_service.domains()
                                     .list(customer='my_customer')
                                     .execute())['domains']
        (primary_domain,) = [d['domainName'] for d in domains if d['isPrimary']]
        return primary_domain
