#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_godzillops
----------------------------------

Tests for `godzillops` module.
"""

import os
import shutil
import sys
import unittest
from functools import partial
from unittest.mock import Mock, patch

from apiclient.errors import HttpError
from httplib2 import Response
from godzillops import godzillops, google, trello

sys.path.append(os.path.dirname(__file__))
import config_test

def apiclient_mock_creator(mocks):
    def apiclient_build_mock(*args, **kwargs):
        return mocks[args[0]]
    return apiclient_build_mock


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
        # Create our per-test mocks
        self.logging_mock = Mock(name='logging')
        self.logging_patch = patch('godzillops.godzillops.logging', self.logging_mock)
        self.logging_patch.start()
        self.service_cred_mock = Mock(name='ServiceAccountCredentials')
        self.admin_service_mock = Mock(name='admin_service')
        self.admin_service_mock.domains().list(customer='my_customer').execute = Mock(return_value={'domains': [{'isPrimary': True, 'domainName': 'example.com'},
                                                                                                                {'isPrimary:': False, 'domainName': 'example.org'}]})
        self.gmail_service_mock = Mock(name='gmail_service')
        self.apiclient_build_mock = apiclient_mock_creator({'admin': self.admin_service_mock,
                                                            'gmail': self.gmail_service_mock})
        self.google_patch = patch.multiple('godzillops.google',
                                           ServiceAccountCredentials=self.service_cred_mock,
                                           build=self.apiclient_build_mock)
        self.google_patch.start()

        # Mocking & Patching all done, create a patched instance of our Chat class - sans Logging/API pieces
        self.chat = godzillops.Chat(config_test)

    def tearDown(self):
        self.google_patch.stop()
        self.logging_patch.stop()

    def test_000_chat_init_successful(self):
        self.assertEqual(self.chat.config.PLATFORM, 'text')

    def test_000_respond_exception(self):
        """Test begin adding a user to trello, then cancel."""
        self.chat.determine_action = Mock(side_effect=ValueError('BOOM!'))
        (response,) = self.chat.respond('GZ, are you okay?')
        self.logging_mock.exception.assert_called_with("An error occurred responding to the user.")
        self.assertEqual("I... erm... what? Try again.", response)

    def test_001_say_hello_gz(self):
        responses = self.chat.respond('Hi Godzilla!')
        for index, response in enumerate(responses):
            if not index:
                # make sure he said hi back
                self.assertIn(response.lower(), self.chat.chunker.greetings)

    def test_002_gz_gif(self):
        responses = self.chat.respond('Gojira!')
        expected_responses = [partial(self.assertEqual, 'RAWR!'),
                              partial(self.assertIn, 'giphy.com')]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_003_create_google_account(self):
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
                              partial(self.assertIn, 'groups now: dev'),
                              partial(self.assertIn, 'Sending them a welcome email'),
                              partial(self.assertIn, 'Google account creation complete!')]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_004_create_google_account(self):
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
                              partial(self.assertIn, 'groups now: design'),
                              partial(self.assertIn, 'Sending them a welcome email'),
                              partial(self.assertIn, 'Google account creation complete!')]
        for index, response in enumerate(responses):
            expected_responses[index](response)

    def test_005_invite_to_trello(self):
        """Test adding a user to trello."""

    def test_006_cancel(self):
        """Test begin adding a user to trello, then cancel."""

    def test_007_slack_specific(self):
        """Test some Slack specific behavior."""


if __name__ == '__main__':
    import sys
    sys.exit(unittest.main())
