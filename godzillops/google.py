# -*- coding: utf-8 -*-
"""google.py - Google API methods

The GoogleAdmin class serves as an interface to Google APIs for interacting
with  Google Admin SDK for creating users and managing groups.

Attributes:
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
import random
import string
from email.mime.text import MIMEText

from apiclient.errors import HttpError
from apiclient.discovery import build
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials


PASSWORD_CHARACTERS = string.ascii_letters + string.punctuation + string.digits
PASSWORD_LENGTH = 18
SCOPES = ['https://www.googleapis.com/auth/admin.directory.domain.readonly',
          'https://www.googleapis.com/auth/admin.directory.user',
          'https://www.googleapis.com/auth/admin.directory.group',
          'https://www.googleapis.com/auth/gmail.send']


class GoogleAdmin(object):
    """GoogleAdmin class is a more usable interface to googleapiclient

    This class takes a couple configuation pieces - service account keys & super admin account - and
    returns a class instance capable of doing basic google user management.
    """
    def __init__(self, service_account_json, sub_account):
        """Initialize Google API Service Interface

        Given a service account json object and super admin account email from Google Apps Domain,
        this function initializes the GoogleAdmin class by creating a Google Admin SDK API service object.

        Args:
            service_account_json (dict): Parsed JSON Key File for a Google Service Account
            sub_account (str): The super admin account to act on behalf of
        """
        credentials = ServiceAccountCredentials._from_parsed_json_keyfile(service_account_json, SCOPES)
        delegated_creds = credentials.create_delegated(sub_account)
        http = delegated_creds.authorize(Http())
        self.sub_account = sub_account
        self.service = build('admin', 'directory_v1', http=http)
        self.primary_domain = self._get_primary_domain()

    def create_user(self, given_name, family_name, username, old_email, job_title, groups):
        """Create a new Google user and add him/her to the list of groups passed.

        Args:
            given_name (str): First name of new user
            family_name (str): Last name of new user
            username (str): Used for the primary email handle / Google username.
            old_email (str): Old email address - used to send new login credentials to
            job_title (str): Job title of new user
            groups (list): List of google group names determined by GZChunker
        """
        email = '{}@{}'.format(username, self.primary_domain)
        emails = [{'address': email, 'primary': True, 'type': 'work'},
                  {'address': old_email, 'type': 'other'}]
        orgs = [{'primary': True, 'title': job_title}]
        plain, b16password = self._generate_password()

        logging.info("Creating new google account - {}".format(email))
        response = self.service.users().insert(customer='my_customer',
                                               name={'givenName': given_name,
                                                     'familyName': family_name},
                                               password=b16password,
                                               primaryEmail=email,
                                               emails=emails,
                                               organizations=orgs)
        for group in groups:
            logging.info("Adding {} to the '{}' group".format(email, group))
            self.service.members().insert(groupKey=group, email=email, role='MEMBER')

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
        """.format(domain=self.primary_domain, **locals())
        message = self._create_message(old_email, 'Welcome to {}'.format(self.primary_domain), message_text)

    def _create_message(self, to, subject, message_text):
      """Create a message for an email.

          Args:
            to: Email address of the receiver.
            subject: The subject of the email message.
            message_text: The text of the email message.

          Returns:
            An object containing a base64url encoded email object.
      """
      message = MIMEText(message_text)
      message['to'] = to
      message['from'] = self.sub_account
      message['cc'] = self.sub_account
      message['subject'] = subject
      return {'raw': base64.urlsafe_b64encode(message.as_string())}

    def send_message(self, user_id, message):
        """Send an email message.

        Args:
          user_id: User's email address. The special value "me"
          can be used to indicate the authenticated user.
          message: Message to be sent.

        Returns:
          Sent Message.
        """
        message = self.service.users().messages().send(userId=user_id,
                                                       body=message).execute()
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
            self.service.users().get(userKey=email).execute()
            # Executed without error, meaning this user already exists
            return False
        except HttpError as error:
            if error.resp.status == 404:
                # Error was raised since the user isn't found, meaning it's available
                return True

    def _generate_password(self):
        plain = ''.join(random.choice(PASSWORD_CHARACTERS) for _ in range(PASSWORD_LENGTH))
        return plain, base64.b16encode(plain.encode('ascii'))

    def _get_primary_domain(self):
        domain_obj = self.service.domains().list(customer='my_customer').execute()
        for domain in domain_obj['domains']:
            if domain['isPrimary']:
                return domain['domainName']

