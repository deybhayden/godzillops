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
sys.path.append(os.path.dirname(__file__))
import unittest
from unittest.mock import Mock
from functools import partial

from godzillops import godzillops
import config_test


class TestChat(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Make sure we start with a new ClassifierBasedPOSTagger.
        # Removing the CACHE_DIR makes sure that subsequent tests
        # (after the first one) will pull the pickled tagger from the cache,
        # giving us coverage with/without the tagger being cached.
        shutil.rmtree(godzillops.CACHE_DIR, ignore_errors=True)

    def setUp(self):
        self.google_mock = Mock()
        self.trello_mock = Mock()
        godzillops.GoogleAdmin = self.google_mock
        godzillops.TrelloAdmin = self.trello_mock
        self.chat = godzillops.Chat(config_test)

    def tearDown(self):
        pass

    def test_000_chat_init_successful(self):
        self.assertEqual(self.chat.config.PLATFORM, 'text')

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


if __name__ == '__main__':
    import sys
    sys.exit(unittest.main())
