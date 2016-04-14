# -*- coding: utf-8 -*-
import nltk
from nltk.parse import load_parser

class Chat(object):
    bot_prefixes = ['godzillops', 'godzilla', 'zilla', 'gojira']

    def __init__(self):
        self.chart_parser = load_parser('grammars/book_grammars/feat0.fcfg', trace=1)

    def set_context(self, context):
        # TODO: Use this to set information about the user - Name, TZ, etc
        pass

    def respond(self, _input, context=None):
        if context:
            self.set_context(context)

        tokens = _input.split()
        chunks = self.chart_parser.parse(tokens)

        import pudb; pudb.set_trace()  # XXX BREAKPOINT
