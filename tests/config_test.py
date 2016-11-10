import logging
LOG_LEVEL = logging.DEBUG
PLATFORM = "text"
ADMINS = ["text"]
GZ_GIF_URL = "http://api.giphy.com/v1/gifs/search?q=godzilla&api_key=dc6zaTOxFJmzC"
# === SLACK ===
SLACK_TOKEN = "xoxb-12345678910-asdfasdfasdfasdfasdfasdf"
SLACK_USER = "U12345678"
# === GOOGLE ===
GOOGLE_SERVICE_ACCOUNT_JSON = {
    "type": "service_account",
    "project_id": "",
    "private_key_id": "",
    "private_key": "",
    "client_email": "",
    "client_id": "",
    "auth_uri": "",
    "token_uri": "",
    "auth_provider_x509_cert_url": "",
    "client_x509_cert_url": ""
}
GOOGLE_SUPER_ADMIN = 'admin@example.com'
GOOGLE_GROUPS = {
    'GDES': ['design'],
    'GDEV': ['dev'],
    'GCRE': ['creatives']
}
GOOGLE_DEV_ROLES = ['backend', 'frontend']
GOOGLE_CALENDAR_ID = 'cal-id@group.calendar.google.com'
GOOGLE_WELCOME_TEXT = ''
# === TRELLO ===
TRELLO_ORG = 'yourorg'
TRELLO_API_KEY = 'asdfasdfasdfasdfasdfasdfasdfasdf'
TRELLO_TOKEN = 'asdfasdfasdfasdfasdfasdfasdfasdfasdfsadfasdfasdfasdfasdfasdfasdf'
# === GITHUB ===
GITHUB_ORG = 'yourorg'
GITHUB_ACCESS_TOKEN = 'asdfasdfasdfasdfasdfasdfasdfasdfasdfsadfasdfasdfasdfasdfasdfasdf'
GITHUB_DEV_ROLES = {
    'backend': [1234567, 8901234],
    'frontend': [1234567]
}
# === ABACUS ===
ABACUS_ZAPIER_WEBHOOK = 'https://hooks.zapier.com/hooks/catch/asdf'
