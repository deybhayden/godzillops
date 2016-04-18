"""
APIs for interacting with Google Admin SDK for creating users and managing
groups.
"""
from apiclient.discovery import build
from httplib2 import Http
from oauth2client.service_account import ServiceAccountCredentials


# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/admin-directory_v1-python-quickstart.json
SCOPES = ['https://www.googleapis.com/auth/admin.directory.user', 'https://www.googleapis.com/auth/admin.directory.group']


def build_admin_service(service_account_json):
    """
    Given a service account json object from Google, this function creates
    a Google Admin SDK API service object and returns it.
    """
    credentials = ServiceAccountCredentials._from_parsed_json_keyfile(service_account_json, SCOPES)
    http = credentials.authorize(Http())
    service = build('admin', 'directory_v1', http=http)
    return service
