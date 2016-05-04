#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_godzillops
----------------------------------

Tests for `godzillops` module.
"""
import json
import os
import shutil
import sys
import unittest
import urllib.parse as urlparse
from functools import partial
from unittest.mock import Mock, patch, call

from apiclient.errors import HttpError
from httplib2 import Response
from godzillops import godzillops

sys.path.append(os.path.dirname(__file__))
import config_test


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

    @classmethod
    def setUpClass(cls):
        if not os.environ.get('KEEP_GZ_CACHE'):
            # Unless told not to via the KEEP_GZ_CACHE environment variable,
            # make sure we start with a new ClassifierBasedPOSTagger.
            # Removing the CACHE_DIR makes sure that subsequent tests
            # (after the first one) will pull the pickled tagger from the cache,
            # giving us coverage with/without the tagger being cached.
            shutil.rmtree(godzillops.CACHE_DIR, ignore_errors=True)

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
        self.admin_service_mock.domains().list(customer='my_customer').execute = Mock(return_value={'domains': [{'isPrimary': True, 'domainName': 'example.com'},
                                                                                                                {'isPrimary:': False, 'domainName': 'example.org'}]})
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

        # Mocking & Patching all done, create a patched instance of our Chat class - sans Logging/API pieces
        self.chat = godzillops.Chat(config_test)

    def tearDown(self):
        self.github_patch.stop()
        self.trello_patch.stop()
        self.google_patch.stop()
        self.gz_patch.stop()

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
        for index, response in enumerate(responses):
            if not index:
                # make sure he said hi back
                self.assertIn(response.lower(), self.chat.chunker.greetings)

    def test_003_gz_gif(self):
        """Test that GZ returns a random godzilla gif when only his name is mentioned."""
        self.gz_urlresp.content = b'{"data":[{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}},{"images":{"downsized":{"url": "giphy.com"}}}]}'
        responses = self.chat.respond('Gojira!')
        expected_responses = [partial(self.assertEqual, 'RAWR!'),
                              partial(self.assertIn, 'giphy.com')]
        for index, response in enumerate(responses):
            expected_responses[index](response)
        self.gz_urlreq.urlopen.assert_called_with(self.chat.config.GZ_GIF_URL)

    def test_004_create_google_account(self):
        """Create google account with a single Chat.respond call."""
        # Make sure that the username is available
        self.admin_service_mock.users().get(userKey='bill@example.com').execute = Mock(side_effect=HttpError(Response({'status': 404}),
                                                                                                             b'User does not exist.'))
        # Set up proper gmail response
        self.gmail_service_mock.users().messages().send().execute = Mock(return_value={'id': '123456789'})
        responses = self.chat.respond('I need to create a google account for Bill Tester.'
                                      ' His email is bill@gmail.com, and his title will be'
                                      ' Software Engineer.')
        expected_responses = [partial(self.assertIn, "'bill' is an available Google username."),
                              partial(self.assertIn, 'good to go'),
                              partial(self.assertIn, 'groups now: *dev*'),
                              partial(self.assertIn, 'Sending them a welcome email'),
                              partial(self.assertIn, 'Google account creation complete!')]
        for index, response in enumerate(responses):
            expected_responses[index](response)

        self.cal_service_mock.acl().insert.assert_called_with(calendarId=self.chat.config.GOOGLE_CALENDAR_ID,
                                                              body={'role': 'reader',
                                                                    'scope': {'type': 'user', 'value': 'bill@example.com'}})

    def test_005_create_google_account(self):
        """Create google account with a multiple Chat.respond calls.

        Also, the username is unavailable the first time.
        """
        (response,) = self.chat.respond('I need to create a new google account.')
        self.assertEqual("What is the employee's full name (first & last)?", response)
        self.assertEqual(self.chat.action_state['text']['action'], 'create_google_account')
        (response,) = self.chat.respond('Bill')
        self.assertEqual("What is the employee's full name (first & last)?", response)
        (response,) = self.chat.respond('Bill Tester')
        self.assertEqual("What is a personal email address for Bill?", response)
        (response,) = self.chat.respond('bill@yahoo.com')
        self.assertEqual("What is Bill's job title?", response)
        responses = self.chat.respond('UX Designer')
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
                              partial(self.assertIn, 'groups now: *design*'),
                              partial(self.assertIn, 'Sending them a welcome email'),
                              partial(self.assertIn, 'Google account creation complete!')]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_006_invite_to_trello(self):
        """Test adding a user to trello."""
        (response,) = self.chat.respond('I need to add Bill Tester to Trello')
        self.assertEqual("What is Bill Tester's example.com email address?", response)
        (response,) = self.chat.respond('bill@example.com')
        members_url = self.chat.trello_admin.trello_api_url.format('organizations/yourorg/members')
        data = urlparse.urlencode({'email': 'bill@example.com', 'fullName': 'Bill Tester'}).encode()
        self.trello_urlreq.Request.assert_called_with(url=members_url, data=data, method='PUT')
        self.trello_urlreq.urlopen.assert_called_with(self.trello_urlreq.Request())
        self.assertEqual("I have invited bill@example.com to join *yourorg* in Trello!", response)

    def test_007_invite_to_trello(self):
        """Test adding a user to trello - but throw an exception causing it to fail."""
        self.trello_urlresp.status = 404
        (response,) = self.chat.respond('I need to add Bill Tester (bill@example.com) to Trello.')
        self.assertIn("Huh, that didn't work", response)

    def test_008_slack_and_cancel(self):
        """Test Slack specific behavior by adding a user to trello, then canceling."""
        context = {'user': 'U01234567', 'tz': 'America/Chicago', 'tz_offset': -18000}
        response = self.chat.respond('Invite <mailto:bill@example.com|bill@example.com> to Trello', context)
        # No response since that fake user string isn't an admin in config_test.py
        self.assertEqual(response, ())
        context['user'] = 'text'
        (response,) = self.chat.respond('Invite <mailto:bill@example.com|bill@example.com> to Trello', context)
        self.assertEqual("What is the user's full name?", response)
        (response,) = self.chat.respond('Nevermind.', context)
        self.assertIn("Previous action canceled.", response)

    def test_009_invite_to_github(self):
        """Test inviting a new user to our GitHub organization/team."""
        (response,) = self.chat.respond('I need to add @billyt3st3r to Github')
        members_url = self.chat.github_admin.github_api_url.format('teams/1234567/memberships/billyt3st3r')
        data = json.dumps({'role': 'member'}).encode()
        self.github_urlreq.Request.assert_called_with(url=members_url, data=data, method='PUT',
                                                      headers={'Content-Type': 'application/json'})
        self.github_urlreq.urlopen.assert_called_with(self.github_urlreq.Request())
        self.assertEqual("I have invited `billyt3st3r` to join *yourorg* in GitHub!", response)

    def test_010_invite_to_github(self):
        """Test inviting 2 users to our GitHub organization/team, but don't say who at first."""
        (response,) = self.chat.respond('I need to invite a couple people to join our Github.')
        self.assertEqual("Please list the GitHub username(s) so I can send out an invite.", response)

        usernames = ('billyt3st3r', 'suzzee_z')
        responses = self.chat.respond(', '.join(usernames))

        data = json.dumps({'role': 'member'}).encode()
        expected_responses, urlreq_calls = [], []
        for username in usernames:
            expected_responses.append(partial(self.assertIn, "invited `{}` to join *yourorg* in GitHub".format(username)))
            members_url = self.chat.github_admin.github_api_url.format('teams/1234567/memberships/'+username)
            urlreq_calls.append(call(url=members_url, data=data, method='PUT',
                                     headers={'Content-Type': 'application/json'}))


        for index, response in enumerate(responses):
            expected_responses[index](response)

        self.github_urlreq.Request.assert_has_calls(urlreq_calls)
        self.github_urlreq.urlopen.assert_has_calls((call(self.github_urlreq.Request()),
                                                     call(self.github_urlreq.Request())))

    def test_011_invite_to_github(self):
        """Test adding a user to github - but throw an exception causing it to fail."""
        self.github_urlresp.status = 404
        (response,) = self.chat.respond('I need to add @billyt3st3r to Github.')
        self.assertIn("Huh, I couldn't add `billyt3st3r` to *yourorg* in GitHub", response)

    def test_012_context_exception(self):
        """Test responding to a borked context object"""
        context = {'tz': 'America/Chicago', 'tz_offset': -18000}
        (response,) = self.chat.respond('GZ, are you okay?', context)
        self.logging_mock.exception.assert_called_with("An error occurred responding to the user.")
        self.assertEqual("I... erm... what? Try again.", response)


if __name__ == '__main__':
    import sys
    sys.exit(unittest.main())
