# -*- coding: utf-8 -*-
import json
import logging
import os
import random
import urllib.request as urlreq
from collections import defaultdict

import nltk
from nltk.corpus import conll2000
from nltk.tag.sequential import ClassifierBasedPOSTagger
from nltk.tokenize import TreebankWordTokenizer

MODULE_DIR = os.path.dirname(__file__)

class GZChunker(nltk.chunk.ChunkParserI):

    gz_aliases = {'godzillops', 'godzilla', 'zilla', 'gojira'}
    singular_noun_tags = {'NN', 'NNP', 'PRP'}

    def __init__(self):
        self.greetings = open(os.path.join(MODULE_DIR, 'corpora', 'greetings.txt')).read().split()

    def parse(self, tagged_sent):
        iobs = []
        in_greeting = False

        for word, tag in tagged_sent:
            lword = word.lower()
            if lword in self.gz_aliases:
                if in_greeting:
                    in_greeting = False
                    iobs.append((word, tag, 'B-GODZILLA'))
                else:
                    iobs.append((word, tag, 'I-GODZILLA'))
            elif lword in self.greetings and tag in self.singular_noun_tags:
                in_greeting = True
                iobs.append((word, tag, 'I-GREETING'))
            else:
                in_greeting = False
                iobs.append((word, tag, 'O'))

        return nltk.chunk.conlltags2tree(iobs)


class Chat(object):
    """
    Main class of the GozillOps chat bot. Instantiated in the Tokyo
    runtime for handling responses to chat input.
    """

    def __init__(self):
        logging.debug('Initialize Tokenizer')
        self.tokenizer = TreebankWordTokenizer()
        logging.debug('Initialize Tagger')
        self.tagger = ClassifierBasedPOSTagger(train=conll2000.tagged_sents('train.txt'))
        logging.debug('Initialize Chunker')
        self.chunker = GZChunker()

        self.actions = defaultdict(self.nop, **{
            'GREETING': self.greet,
            'GZGIF': self.gz_gif
        })

    def nop(self):
        """
        NOP Factory - be able to respond to any nonsense with this function.
        """
        return lambda: ''

    def greet(self):
        return random.choice(self.chunker.greetings).title()

    def gz_gif(self):
        """
        Return a random Godzilla GIF
        """
        with urlreq.urlopen('http://api.giphy.com/v1/gifs/search?q=godzilla&api_key=dc6zaTOxFJmzC&limit=1') as r:
            response = json.loads(r.read().decode('utf-8'))
            return response['data'][0]['images']['downsized']['url']

    def determine_action(self, chunk_sents):
        action = None
        for chunk in chunk_sents:
            for subtree in chunk.subtrees():
                label = subtree.label()
                if label == 'GREETING':
                    action = label
                elif label == 'GODZILLA' and not action:
                    action = 'GZGIF'

        return action

    def ie_preprocess(self, _input):
        sents = nltk.sent_tokenize(_input)
        sents = self.tokenizer.tokenize_sents(sents)
        sents = self.tagger.tag_sents(sents)
        return sents

    def set_context(self, context=None):
        # TODO: Use to capture username, how GZ is being chatted and Timezone
        self.context = context

    def respond(self, _input, context=None):
        self.set_context(context)

        tagged_sents = self.ie_preprocess(_input)
        chunked_sents = self.chunker.parse_sents(tagged_sents)
        action = self.determine_action(chunked_sents)

        return self.actions[action]()
