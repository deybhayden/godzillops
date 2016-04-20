# -*- coding: utf-8 -*-
import json
import logging
import os
import pickle
import random
import re
import tempfile
import urllib.request as urlreq
from collections import defaultdict

import nltk
from nltk.corpus import names, brown
from nltk.tag.sequential import ClassifierBasedPOSTagger

from .google import build_admin_service


CACHE_DIR = os.path.join(tempfile.gettempdir(), 'godzillops')



class GZChunker(nltk.chunk.ChunkParserI):

    create_actions = {'create', 'add', 'generate', 'make'}
    dev_titles = {'developer', 'engineer', 'coder', 'programmer'}
    design_titles = {'creative', 'designer', 'ux'}
    greetings = {'hey', 'hello', 'sup', 'greetings', 'hi', 'yo'}
    gz_aliases = {'godzillops', 'godzilla', 'zilla', 'gojira'}
    cancel_actions = {'stop', 'cancel', 'nevermind', 'quit'}
    email_regexp = re.compile('[^@]+@[^@]+\.[^@]+', re.IGNORECASE)

    def __init__(self):
        self.names = set(names.words())

    def parse(self, tagged_text, action_state):
        logging.debug(tagged_text)
        iobs = []
        # in_dict is used to keep track of mid sentence context when deciding
        # how to chunk the tagged sentence into meaningful pieces.
        in_dict = defaultdict(bool)

        # use previous action state to default in_dict
        if action_state.get('action') == 'CREATE_GOOGLE_ACCOUNT':
            in_dict['create_action'] = True
            in_dict['create_google_account'] = True

        i = 0
        tagged_len = len(tagged_text)

        while i < tagged_len:
            word, tag = tagged_text[i]
            i += 1
            lword = word.lower()
            if lword in self.gz_aliases:
                if in_dict['greeting']:
                    in_dict['greeting'] = False
                    iobs.append((word, tag, 'B-GODZILLA'))
                else:
                    iobs.append((word, tag, 'I-GODZILLA'))
            elif word in self.names or in_dict['person'] and tag.startswith('NP'):
                if in_dict['person']:
                    iobs.append((word, tag, 'I-PERSON'))
                else:
                    iobs.append((word, tag, 'B-PERSON'))
                    in_dict['person'] = True
            elif lword in self.greetings:
                in_dict['greeting'] = True
                iobs.append((word, tag, 'I-GREETING'))
            elif lword in self.create_actions and tag.startswith('VB'):
                in_dict['create_action'] = True
                iobs.append((word, tag, 'I-CREATE_ACTION'))
            elif in_dict['create_action'] and lword == 'google':
                in_dict['create_action'] = False
                in_dict['create_google_account'] = True
                iobs.append((word, tag, 'I-CREATE_GOOGLE_ACCOUNT'))
            elif in_dict['create_google_account'] and lword == 'title':
                in_dict['check_for_title'] = True
                in_dict['title'] = []
            elif in_dict['create_action'] and lword in self.cancel_actions and not iobs:
                # Only recognize cancel action by itself, and return immediately
                # when it is encountered
                iobs.append((word, tag, 'I-CANCEL_ACTION'))
                break
            elif in_dict['check_for_title']:
                probably_job_title = any([lword in self.dev_titles,
                                          lword in self.design_titles,
                                          tag.startswith('NP')])
                if probably_job_title and in_dict['finding_title']:
                    iobs.append((word, 'NP', 'I-JOB_TITLE'))
                elif probably_job_title:
                    iobs.append((word, 'NP', 'B-JOB_TITLE'))
                    in_dict['finding_title'] = True
                elif 'finding_title' in in_dict:
                    del in_dict['finding_title']
                    del in_dict['check_for_title']
                    iobs.append((word, tag, 'O'))
                else:
                    iobs.append((word, tag, 'O'))
            elif self.email_regexp.match(lword):
                # This is probably an email address
                iobs.append((word, 'NN', 'I-EMAIL'))
            else:
                in_dict['person'] = False
                iobs.append((word, tag, 'O'))


        return nltk.chunk.conlltags2tree(iobs)


class Chat(object):
    """
    Main class of the Godzillops chat bot. Instantiated in the Tokyo
    runtime for handling responses to chat input.
    """

    def __init__(self, config):
        """
        Initialize the Godzillops chat bot brains.
        Creates a tokenizer, tagger, and customized chunker for NLP.

        Args:
            config (module): Python module storing configuration variables and secrets.
                Used to authenticate API services and connect data stores.
        """
        self.config = config

        logging.debug('Initialize Tagger')
        self._create_tagger()
        logging.debug('Initialize Chunker')
        self.chunker = GZChunker()

        self.actions = {
            None: self.nop,
            'GREETING': self.greet,
            'GZGIF': self.gz_gif,
            'CREATE_GOOGLE_ACCOUNT': self.create_google_account,
            'CANCEL': self.cancel
        }

        self.action_state = {}

    def _create_tagger(self):
        """
        Create our own classifier based POS tagger. It uses the brown corpus
        since it is included in it's entirety (as opposed to Penn Treebank)- thus
        using Brown POS tags - run nltk.help.brown_tagset() for descriptions
        of each POS tag.
        """
        if not os.path.exists(CACHE_DIR):
            os.mkdir(CACHE_DIR)

        tagger_path = os.path.join(CACHE_DIR, 'tagger.pickle')
        # Check to see if a trained tagger is already cached, if so, use it
        if os.path.exists(tagger_path):
            with open(tagger_path, 'rb') as tagger_pickle:
                self.tagger = pickle.load(tagger_pickle)
                logging.debug("Tagger loaded from cache: '{}'".format(tagger_path))
        else:
            self.tagger = ClassifierBasedPOSTagger(train=brown.tagged_sents())
            with open(tagger_path, 'wb') as tagger_pickle:
                pickle.dump(self.tagger, tagger_pickle)
                logging.debug("Tagger placed in cache: '{}'".format(tagger_path))

    def nop(self):
        """
        NOP Factory - be able to respond to any nonsense with this function.
        """
        # TODO: List some helpful stuff or try to suggest commands based on what they said.
        yield ''

    def greet(self):
        yield random.choice(list(self.chunker.greetings)).title()
        yield 'Can I help you with anything?'

    def cancel(self):
        self.action_state = {}
        yield "Previous action canceled. I didn't want to do it anyways."

    def gz_gif(self):
        """
        Return a random Godzilla GIF
        """
        yield 'RAWR!'
        with urlreq.urlopen('http://api.giphy.com/v1/gifs/search?q=godzilla&api_key=dc6zaTOxFJmzC') as r:
            response = json.loads(r.read().decode('utf-8'))
            rand_index = random.choice(range(0,24))
            yield response['data'][rand_index]['images']['downsized']['url']

    def create_google_account(self, **kwargs):
        name = kwargs.get('person')
        email = kwargs.get('email')
        job_title = kwargs.get('job_title')
        all_good = name and email and job_title

        if not all_good:
            self.locked = True
            self.action_state = {
                'action': 'CREATE_GOOGLE_ACCOUNT',
                'kwargs': kwargs
            }
            if not name:
                self.action_state['step'] = 'name'
                yield "What is the employee's name?"
            elif not email:
                self.action_state['step'] = 'email'
                yield "What is {}'s old email address?".format(name)
            elif not job_title:
                self.action_state['step'] = 'title'
                yield "What will {}'s job title be?".format(name)


        service = build_admin_service(self.config.GOOGLE_SERVICE_ACCOUNT_JSON,
                                      self.config.GOOGLE_SUPER_ADMIN)



    def determine_action(self, chunked_text):
        logging.debug(chunked_text)
        action = self.action_state.get('action')
        kwargs = {}

        # Used to store named entities
        entity_dict = defaultdict(list)

        for subtree in chunked_text.subtrees():
            label = subtree.label()
            if label == 'GREETING':
                action = label
            elif label == 'GODZILLA' and not action:
                action = 'GZGIF'
            elif label == 'CREATE_GOOGLE_ACCOUNT':
                action = label
            elif label in ('EMAIL', 'PERSON', 'JOB_TITLE'):
                entity_dict[label].append(' '.join(l[0] for l in subtree.leaves()))
            elif label == 'CANCEL_ACTION' and self.action_state['action']:
                # Only set cancel if in a previous action
                action = 'CANCEL'

        # Prepare Args & Kwargs for selected action
        if action != 'CANCEL':
            # Carry over previous kwargs
            kwargs = self.action_state.get('kwargs', {})
            if action == 'CREATE_GOOGLE_ACCOUNT':
                for label in ('JOB_TITLE', 'PERSON', 'EMAIL'):
                    if entity_dict[label]:
                        kwargs[label.lower()] = entity_dict[label][0]

        return action, kwargs

    def set_context(self, context=None):
        # TODO: Use to capture username, how GZ is being chatted and Timezone
        self.context = context

    def respond(self, _input, context=None):
        self.set_context(context)

        tagged_text = self.tagger.tag(_input.split())
        chunked_text = self.chunker.parse(tagged_text, self.action_state)
        action, kwargs = self.determine_action(chunked_text)

        return self.actions[action](**kwargs)
