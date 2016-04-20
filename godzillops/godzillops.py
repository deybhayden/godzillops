# -*- coding: utf-8 -*-
"""godzillops - ゴジラ - Gojira - King of Business Operations

This module contains the main Chat class of the godzillops library. The
Chat class is instantiated in a running Tokyo platform and responds to user
input. The responses are determined by NLP provided by NLTK and a custom chunker,
GZChunker - also in this file.
"""
import json
import logging
import os
import pickle
import random
import re
import tempfile
import urllib.request as urlreq
from collections import defaultdict
from datetime import datetime

import nltk
from nltk.corpus import names, brown
from nltk.tag.sequential import ClassifierBasedPOSTagger

from dateutil.tz import tzlocal

from .google import build_admin_service


CACHE_DIR = os.path.join(tempfile.gettempdir(), 'godzillops')


class GZChunker(nltk.chunk.ChunkParserI):
    """
    Custom ChunkParser used in the godzillops.Chat class for chunking POS-tagged text.
    The chunks here represent named entities and action labels that help determine what
    GZ should do in response to text input.
    """

    # These sets are mini-corpora for checking input and determining intent
    create_actions = {'create', 'add', 'generate', 'make'}
    dev_titles = {'developer', 'engineer', 'coder', 'programmer'}
    design_titles = {'creative', 'designer', 'ux'}
    greetings = {'hey', 'hello', 'sup', 'greetings', 'hi', 'yo'}
    gz_aliases = {'godzillops', 'godzilla', 'zilla', 'gojira'}
    cancel_actions = {'stop', 'cancel', 'nevermind', 'quit'}
    email_regexp = re.compile('[^@]+@[^@]+\.[^@]+', re.IGNORECASE)

    def __init__(self):
        """
        Initialize the GZChunker class and any members that need to be created
        at runtime.
        """
        # Create a set of names from the NLTK names corpus - used for PERSON recognition
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
            if action_state['step'] == 'title':
                in_dict['check_for_title'] = True

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
        # Context is a dictionary containing information about the user we're
        # chatting with - user name, admin, and timezone information
        self.context = {}

        logging.debug('Initialize Tagger')
        self._create_tagger()
        logging.debug('Initialize Chunker')
        self.chunker = GZChunker()

        # Actions is a mapping of Chunker labels to functions that
        # Godzillops exposes as commands
        self.actions = {
            None: self.nop,
            'GREETING': self.greet,
            'GZGIF': self.gz_gif,
            'CREATE_GOOGLE_ACCOUNT': self.create_google_account,
            'CANCEL': self.cancel
        }

        # Action state is a dictionary used for managing incomplete
        # actions - cases where Godzillops needs to clarify or ask for more
        # information before finishing an action.
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

    #
    # ACTION STATE HELPERS - used to manager per user action states - or continued
    # actions over chat
    #

    def _clear_action_state(self):
        self.action_state[self.context['user']] = {}

    def _get_action_state(self):
        return self.action_state.get(self.context['user'], {})

    def _set_action_state(self, **action_state):
        self.action_state.setdefault(self.context['user'], {})
        self.action_state[self.context['user']].update(action_state)

    def _set_context(self, context):
        if context is None:
            self.context = {'user': 'text', 'admin': True,
                            'tz': datetime.now(tzlocal()).tzname()}
        else:
            # TODO: Mangle whatever this context object is into the
            # expected format
            self.context = context

    #
    # DETERMINE ACTION AND RESPOND
    #

    def determine_action(self, chunked_text):
        """
        This function takes a Tree of chunked text, reads through the
        different subtrees and determines what the bot should do next.

        Args:
            chunked_text (Tree): A tree of chunked text produced by the GZChunker class.

        Returns:
            tuple: A tuple with two items:

                action (str): This string corresponds to the keys in the self.actions mapping.
                    Whatever the value is determines what function will be ran in self.respond.
                kwargs (dict): Dynamic keyword arguments passed to each action function.
        """
        logging.debug(chunked_text)
        action_state = self._get_action_state()
        action = action_state.get('action')
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
            elif label == 'CANCEL_ACTION' and action_state['action']:
                # Only set cancel if in a previous action
                action = 'CANCEL'

        # Prepare Args & Kwargs for selected action
        if action != 'CANCEL':
            # Carry over previous kwargs
            kwargs = action_state.get('kwargs', {})
            if action == 'CREATE_GOOGLE_ACCOUNT':
                for label in ('JOB_TITLE', 'PERSON', 'EMAIL'):
                    if entity_dict[label]:
                        kwargs[label.lower()] = entity_dict[label][0]

        return action, kwargs

    def respond(self, _input, context=None):
        """
        This function takes a string of input, tokenizes, tags & chunks it and then runs it through
        the determine action function to get a course of action to proceed with and executes said action.

        Args:
            _input (str): String of text sent from a tokyo platform user.
            context (Optional[dict]): A context dictionary sent from the tokyo platform containing
                information about the user sending the text (i.e. user id, timestamp of message).

        Returns:
            generator: A generator of string responses from the Godzillops bot sent from the executed action.
        """
        self._set_context(context)

        tagged_text = self.tagger.tag(_input.split())
        chunked_text = self.chunker.parse(tagged_text, self._get_action_state())
        action, kwargs = self.determine_action(chunked_text)

        return self.actions[action](**kwargs)

    #
    # ACTION METHODS
    #

    def cancel(self):
        self._clear_action_state()
        yield "Previous action canceled. I didn't want to do it anyways."

    def create_google_account(self, **kwargs):
        name = kwargs.get('person')
        email = kwargs.get('email')
        job_title = kwargs.get('job_title')
        all_good = name and email and job_title

        if not all_good:
            self.locked = True
            self._set_action_state(action='CREATE_GOOGLE_ACCOUNT',
                                   kwargs=kwargs)
            if not name:
                self._set_action_state(step='name')
                yield "What is the employee's name?"
            elif not email:
                self._set_action_state(step='email')
                yield "What is {}'s old email address?".format(name)
            elif not job_title:
                self._set_action_state(step='title')
                yield "What will {}'s job title be?".format(name)
        else:
            service = build_admin_service(self.config.GOOGLE_SERVICE_ACCOUNT_JSON,
                                          self.config.GOOGLE_SUPER_ADMIN)
            # TODO: Create Account
            self._clear_action_state()

    def greet(self):
        yield random.choice(list(self.chunker.greetings)).title()
        yield 'Can I help you with anything?'

    def gz_gif(self):
        """
        Return a random Godzilla GIF
        """
        yield 'RAWR!'
        with urlreq.urlopen('http://api.giphy.com/v1/gifs/search?q=godzilla&api_key=dc6zaTOxFJmzC') as r:
            response = json.loads(r.read().decode('utf-8'))
            rand_index = random.choice(range(0,24))
            yield response['data'][rand_index]['images']['downsized']['url']

    def nop(self):
        """
        NOP Factory - be able to respond to any nonsense with this function.
        """
        # TODO: List some helpful stuff or try to suggest commands based on what they said.
        yield ''
