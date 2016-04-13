# -*- coding: utf-8 -*-
import nltk
import random
from nltk.corpus import wordnet

class Chat(object):
    bot_prefixes = ['godzillops', 'godzilla', 'zilla', 'gojira']

    def __init__(self):
        pass

    def greet(self):
        syn = wordnet.synsets('hello')[0]
        return random.choice([l.name() for l in syn.lemmas()]).title()

    def determine_action(self, sentences):
        return 'greet'

    def ie_preprocess(self, _input):
        sentences = nltk.sent_tokenize(_input)
        sentences = [nltk.word_tokenize(sent) for sent in sentences]
        sentences = [nltk.pos_tag(sent) for sent in sentences]
        return sentences

    def set_context(self, context):
        pass

    def respond(self, _input, context=None):
        if context:
            self.set_context(context)

        # Begin process of information extraction
        sentences = self.ie_preprocess(_input)

        import pudb; pudb.set_trace()  # XXX BREAKPOINT
        action = self.determine_action(sentences)

        return self.actions[action]()
