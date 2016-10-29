#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_godzillops
----------------------------------

Tests for `godzillops` module.
"""
import json
import os
import sys
import unittest
import urllib.parse as urlparse
from functools import partial
from unittest.mock import Mock, patch, call

from apiclient.errors import HttpError
from httplib2 import Response
from godzillops import godzillops

TEST_DIR = os.path.dirname(__file__)
sys.path.append(TEST_DIR)


def apiclient_mock_creator(mocks):
    def apiclient_build_mock(*args, **kwargs):
        return mocks[args[0]]
    return apiclient_build_mock


class MockUrllibResponse(object):
    def __init__(self, status, content=None):
        self.status = status
        if content and not isinstance(content, bytes):
            raise ValueError('content must be in bytes')
        self.content = content

    def read(self):
        return self.content


class TestChat(unittest.TestCase):

    def setUp(self):
        """setUp runs before every test is executed.

        Make sure that we create and mock all API pieces - i.e. Google API objects & Trello urllib calls.
        """
        # First, we need to create our per-test mocks

        # == Godzillops ==
        self.logging_mock = Mock(name='logging')
        self.gz_urlreq = Mock(name='urlreq')
        self.gz_urlresp = MockUrllibResponse(status=200)
        self.gz_urlreq.urlopen.return_value = Mock(name='urlopen',
                                                   __enter__=Mock(return_value=self.gz_urlresp),
                                                   __exit__=Mock(return_value=False))
        self.gz_patch = patch.multiple('godzillops.godzillops',
                                       logging=self.logging_mock,
                                       urlreq=self.gz_urlreq)
        self.gz_patch.start()

        # == Google Mocks ==
        self.service_cred_mock = Mock(name='ServiceAccountCredentials')
        self.admin_service_mock = Mock(name='admin_service')
        self.admin_service_mock.domains().list(customer='my_customer').execute = Mock(return_value={'domains': [{'isPrimary': False, 'domainName': 'example.org'},
                                                                                                                {'isPrimary': True, 'domainName': 'example.com'}]})
        self.gmail_service_mock = Mock(name='gmail_service')
        self.cal_service_mock = Mock(name='cal_service')
        self.apiclient_build_mock = apiclient_mock_creator({'admin': self.admin_service_mock,
                                                            'gmail': self.gmail_service_mock,
                                                            'calendar': self.cal_service_mock})
        self.google_patch = patch.multiple('godzillops.google',
                                           ServiceAccountCredentials=self.service_cred_mock,
                                           build=self.apiclient_build_mock)
        self.google_patch.start()

        # == Trello Mocks ==
        self.trello_urlreq = Mock(name='urlreq')
        self.trello_urlresp = MockUrllibResponse(status=200)
        self.trello_urlreq.urlopen.return_value = Mock(name='urlopen',
                                                       __enter__=Mock(return_value=self.trello_urlresp),
                                                       __exit__=Mock(return_value=False))
        self.trello_patch = patch('godzillops.trello.urlreq', self.trello_urlreq)
        self.trello_patch.start()

        # == GitHub Mocks ==
        self.github_urlreq = Mock(name='urlreq')
        self.github_urlresp = MockUrllibResponse(status=200)
        self.github_urlreq.urlopen.return_value = Mock(name='urlopen',
                                                       __enter__=Mock(return_value=self.github_urlresp),
                                                       __exit__=Mock(return_value=False))
        self.github_patch = patch('godzillops.github.urlreq', self.github_urlreq)
        self.github_patch.start()

        # == Abacus Mocks ==
        self.abacus_urlreq = Mock(name='urlreq')
        self.abacus_urlresp = MockUrllibResponse(status=200)
        self.abacus_urlreq.urlopen.return_value = Mock(name='urlopen',
                                                       __enter__=Mock(return_value=self.abacus_urlresp),
                                                       __exit__=Mock(return_value=False))
        self.abacus_patch = patch('godzillops.abacus.urlreq', self.abacus_urlreq)
        self.abacus_patch.start()

        # Mocking & Patching all done, create a patched instance of our Chat class - sans Logging/API pieces
        import config_test
        self.chat = godzillops.Chat(config_test)

    def tearDown(self):
        self.github_patch.stop()
        self.trello_patch.stop()
        self.google_patch.stop()
        self.gz_patch.stop()

    def _clear_action_state_assert(self, success, msg):
        return partial(self.assertEqual, {'admin_action_complete': success,
                                          'message': msg})

    def _create_google_account_aux(self, title, groups_to_check):
        (response,) = self.chat.respond('I need to create a new google account.')
        self.assertEqual("What is the employee's full name (Capitalized First & Last)?", response)
        self.assertEqual(self.chat.action_state['text']['action'], 'create_google_account')
        (response,) = self.chat.respond('Bill')
        self.assertEqual("What is the employee's full name (Capitalized First & Last)?", response)
        (response,) = self.chat.respond('Bill Tester')
        self.assertEqual("What is a personal email address for Bill?", response)
        (response,) = self.chat.respond('bill@yahoo.com')
        self.assertEqual("What is Bill's job title?", response)
        if 'dev' in groups_to_check:
            (response,) = self.chat.respond(title)
            self.assertIn("I see we're adding a developer! What team will they be on?", response)
            responses = self.chat.respond('frontend')
        else:
            responses = self.chat.respond(title)
        expected_responses = [partial(self.assertIn, "'bill' is an available Google username."),
                              partial(self.assertIn, 'Aw nuts, that name is taken. Might I suggest a nickname or something like btester')]
        for index, response in enumerate(responses):
            expected_responses[index](response)
        # Make sure that the username is available
        self.admin_service_mock.users().get(userKey='bill@example.com').execute = Mock(side_effect=HttpError(Response({'status': 404}),
                                                                                                             b'User does not exist.'))
        # Set up proper gmail response
        self.gmail_service_mock.users().messages().send().execute = Mock(return_value={'id': '123456789'})
        self.assertEqual(self.chat.action_state['text']['step'], 'username')
        responses = self.chat.respond('btester')
        expected_responses = [partial(self.assertIn, "'btester' is an available Google username."),
                              partial(self.assertIn, 'good to go'),
                              partial(self.assertIn, 'groups now: *{}*'.format(', '.join(groups_to_check))),
                              partial(self.assertIn, 'Sending them a welcome email'),
                              partial(self.assertIn, 'Google account creation complete!'),
                              self._clear_action_state_assert(True, "At the bidding of my master (text), I have created a new Google Account for Bill Tester.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_000_chat_init_successful(self):
        """Make sure we initialized the Chat class without exception."""
        self.assertEqual(self.chat.config.PLATFORM, 'text')

    def test_001_respond_exception(self):
        """Test a determine_action exception mid-response."""
        self.chat.determine_action = Mock(side_effect=ValueError('BOOM!'))
        (response,) = self.chat.respond('GZ, are you okay?')
        self.logging_mock.exception.assert_called_with("An error occurred responding to the user.")
        self.assertEqual("I... erm... what? Try again.", response)

    def test_002_say_hello_gz(self):
        """Test that GZ returns a greeting when greeted."""
        responses = self.chat.respond('Hi Godzilla!')
        expected_responses = [None,
                              partial(self.assertEqual, "Can I help you with anything?"),
                              self._clear_action_state_assert(False, "Command completed.")]
        for index, response in enumerate(responses):
            if not index:
                self.assertIn(response.lower(), self.chat.chunker.greetings)
            else:
                expected_responses[index](response)
        # Test a no-action input - GZ returns nothing
        response = self.chat.respond('Maybe?')
        self.assertEqual(response, ())

    def test_003_gz_gif(self):
        """Test that GZ returns a random godzilla gif when only his name is mentioned."""
        with open(os.path.join(TEST_DIR, 'giphy.json'), 'rb') as giphy_json:
            self.gz_urlresp.content = giphy_json.read()
        responses = self.chat.respond('Gojira!')
        expected_responses = [partial(self.assertEqual, 'RAWR!'),
                              partial(self.assertIn, 'giphy.com'),
                              self._clear_action_state_assert(False, "Command completed.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)
        self.gz_urlreq.urlopen.assert_called_with(self.chat.config.GZ_GIF_URL)

    def test_004_create_google_account(self):
        """Create google account with a single Chat.respond call."""
        # Make sure that the username is available
        self.admin_service_mock.users().get(userKey='almondo@example.com').execute = Mock(side_effect=HttpError(Response({'status': 404}),
                                                                                                                 b'User does not exist.'))
        # Set up proper gmail response
        self.gmail_service_mock.users().messages().send().execute = Mock(return_value={'id': '123456789'})
        responses = self.chat.respond('I need to create a google account for Almondo Finklebottom.'
                                      ' His email is almondo@gmail.com, and his title will be'
                                      ' Software Engineer on the backend team.')
        expected_responses = [partial(self.assertIn, "'almondo' is an available Google username."),
                              partial(self.assertIn, 'good to go'),
                              partial(self.assertIn, 'groups now: *dev, backend*'),
                              partial(self.assertIn, 'Sending them a welcome email'),
                              partial(self.assertIn, 'Google account creation complete!'),
                              self._clear_action_state_assert(True, "At the bidding of my master (text), I have created a new Google Account for Almondo Finklebottom.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

        self.cal_service_mock.acl().insert.assert_called_with(calendarId=self.chat.config.GOOGLE_CALENDAR_ID,
                                                              body={'role': 'reader',
                                                                    'scope': {'type': 'user', 'value': 'almondo@example.com'}})

    def test_005_create_google_account(self):
        """Create Designer-type google account with a multiple Chat.respond calls.

        Also, the username is unavailable the first time.
        """
        self._create_google_account_aux('UX Designer', ['design'])

    def test_006_create_google_account(self):
        """Create Multimedia-based google account with a multiple Chat.respond calls.

        Also, the username is unavailable the first time.
        """
        self._create_google_account_aux('Content Creative', ['creatives'])

    def test_007_invite_to_trello(self):
        """Test adding a user to trello."""
        (response,) = self.chat.respond('I need to add Bill Tester to Trello')
        self.assertEqual("What is Bill Tester's example.com email address?", response)
        responses = self.chat.respond('bill@example.com')
        expected_responses = [partial(self.assertEqual, "I have invited bill@example.com to join *yourorg* in Trello!"),
                              self._clear_action_state_assert(True, "At the bidding of my master (text), I have invited Bill Tester <bill@example.com> to join our Trello organization.")]

        for index, response in enumerate(responses):
            expected_responses[index](response)

        members_url = self.chat.trello_admin.trello_api_url.format('organizations/yourorg/members')
        data = urlparse.urlencode({'email': 'bill@example.com', 'fullName': 'Bill Tester'}).encode()
        self.trello_urlreq.Request.assert_called_with(url=members_url, data=data, method='PUT')
        self.trello_urlreq.urlopen.assert_called_with(self.trello_urlreq.Request())

    def test_008_invite_to_trello(self):
        """Test adding a user to trello - but throw an exception causing it to fail."""
        self.trello_urlresp.status = 404
        responses = self.chat.respond('I need to add Bill Tester (bill@example.com) to Trello.')
        expected_responses = [partial(self.assertIn, "Huh, that didn't work"),
                              self._clear_action_state_assert(False, "I have failed you.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_009_slack_and_cancel(self):
        """Test Slack specific behavior by adding a user to trello, then canceling."""
        context = {'user': {'id': 'U01234567', 'name': 'ben', 'tz': 'America/Chicago', 'tz_offset': -18000}}
        response = self.chat.respond('Invite <mailto:bill@example.com|bill@example.com> to Trello', context)
        # No response since that fake user string isn't an admin in config_test.py
        self.assertEqual(response, ())
        context['user']['id'] = 'text'
        (response,) = self.chat.respond('Invite <mailto:bill@example.com|bill@example.com> to Trello', context)
        self.assertEqual("What is the user's full name?", response)
        responses = self.chat.respond('Nevermind.', context)
        expected_responses = [partial(self.assertIn, "Previous action canceled."),
                              self._clear_action_state_assert(False, "Command completed.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_0010_invite_to_github(self):
        """Test inviting a new user to our GitHub organization/team."""
        responses = self.chat.respond('I need to add @billyt3st3r to Github as a backend team member.')
        expected_responses = [partial(self.assertEqual, "I have invited `billyt3st3r` to join *yourorg* in GitHub!"),
                              self._clear_action_state_assert(True, "At the bidding of my master (text), I have invited billyt3st3r to join our GitHub organization.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

        urlreq_calls = []
        data = json.dumps({'role': 'member'}).encode()
        for team in self.chat.config.GITHUB_DEV_ROLES['backend']:
            members_url = self.chat.github_admin.github_api_url.format('teams/{}/memberships/billyt3st3r'.format(team))
            urlreq_calls.append(call(url=members_url, data=data, method='PUT',
                                     headers={'Content-Type': 'application/json'}))

        self.github_urlreq.Request.assert_has_calls(urlreq_calls)
        self.github_urlreq.urlopen.assert_has_calls((call(self.github_urlreq.Request()),
                                                     call(self.github_urlreq.Request())))

    def test_011_invite_to_github(self):
        """Test inviting a user to our GitHub organization/team, but don't say who at first."""
        (response,) = self.chat.respond('I need to invite someone to join our Github.')
        self.assertEqual("What is the GitHub username?", response)
        username = 'billyt3st3r'
        (response,) = self.chat.respond(username)
        (response,) = self.chat.respond('bill@yahoo.com')
        self.assertIn("What will be the user's dev role on our team? Choose from:", response)
        responses = self.chat.respond('frontend')

        expected_responses, urlreq_calls = [], []
        expected_responses.append(partial(self.assertIn, "invited `{}` to join *yourorg* in GitHub".format(username)))
        urlreq_calls = []
        data = json.dumps({'role': 'member'}).encode()
        for team in self.chat.config.GITHUB_DEV_ROLES['frontend']:
            members_url = self.chat.github_admin.github_api_url.format('teams/{}/memberships/billyt3st3r'.format(team))
            urlreq_calls.append(call(url=members_url, data=data, method='PUT',
                                     headers={'Content-Type': 'application/json'}))
        expected_responses.append(self._clear_action_state_assert(True, "At the bidding of my master (text), I have invited billyt3st3r to join our GitHub organization."))

        for index, response in enumerate(responses):
            expected_responses[index](response)

        self.github_urlreq.Request.assert_has_calls(urlreq_calls)
        self.github_urlreq.urlopen.assert_called_with(self.github_urlreq.Request())

    def test_012_invite_to_github(self):
        """Test adding a user to github - but throw an exception causing it to fail."""
        self.github_urlresp.status = 404
        responses = self.chat.respond('I need to add @billyt3st3r to the frontend team on Github.')
        expected_responses = [partial(self.assertIn, "Huh, I couldn't add `billyt3st3r` to *yourorg* in GitHub"),
                              self._clear_action_state_assert(False, "I have failed you.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_013_context_exception(self):
        """Test responding to a borked context object"""
        context = {}
        (response,) = self.chat.respond('GZ, are you okay?', context)
        self.logging_mock.exception.assert_called_with("An error occurred responding to the user.")
        self.assertEqual("I... erm... what? Try again.", response)

    def test_014_invite_to_abacus(self):
        """Test adding a user to abacus."""
        (response,) = self.chat.respond('I need to invite someone to Abacus')
        self.assertEqual("What is the new user's example.com email address?", response)
        responses = self.chat.respond('bill@example.com')
        expected_responses = [partial(self.assertEqual, "I have invited bill@example.com to join Abacus!"),
                              self._clear_action_state_assert(True, "At the bidding of my master (text), I have invited <bill@example.com> to join our Abacus organization.")]

        for index, response in enumerate(responses):
            expected_responses[index](response)

        data = json.dumps({'email': 'bill@example.com'}).encode()
        self.abacus_urlreq.Request.assert_called_with(url=self.chat.config.ABACUS_ZAPIER_WEBHOOK,
                                                      data=data, method='POST',
                                                      headers={'Content-Type': 'application/json'})
        self.abacus_urlreq.urlopen.assert_called_with(self.abacus_urlreq.Request())

    def test_015_invite_to_abacus(self):
        """Test adding a user to abacus - but throw an exception causing it to fail."""
        self.abacus_urlresp.status = 404
        responses = self.chat.respond('I need to add Bill Tester (bill@example.com) to Abacus.')
        expected_responses = [partial(self.assertIn, "Huh, that didn't work"),
                              self._clear_action_state_assert(False, "I have failed you.")]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_016_create_google_account(self):
        """Create Developer google account with a multiple Chat.respond calls.

        Also, the username is unavailable the first time.
        """
        self._create_google_account_aux('Software Engineer', ['dev', 'frontend'])


if __name__ == '__main__':
    sys.exit(unittest.main())
