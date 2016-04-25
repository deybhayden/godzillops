#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_godzillops
----------------------------------

Tests for `godzillops` module.
"""

import os
import sys
sys.path.append(os.path.dirname(__file__))
import unittest
from unittest.mock import Mock

from godzillops import godzillops
import config_test


class TestChat(unittest.TestCase):

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


if __name__ == '__main__':
    import sys
    sys.exit(unittest.main())
