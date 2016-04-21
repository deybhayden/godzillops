# -*- coding: utf-8 -*-
"""godzillops - ゴジラ - Gojira - King of Business Operations

This module contains the main Chat class of the godzillops library. The
Chat class is instantiated in a running Tokyo platform and responds to user
input. The responses are determined by NLP provided by NLTK and a custom chunker,
GZChunker - also in this file.

Attributes:
    CACHE_DIR (str): Location of the godzillops cache directory. Stored in the system's
        temporary directory. Used for caching the trained NLTK ClassifierBasedPOSTagger.
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
from nltk.tokenize import TweetTokenizer

from dateutil.tz import tzlocal

from .google import GoogleAdmin


CACHE_DIR = os.path.join(tempfile.gettempdir(), 'godzillops')


class GZChunker(nltk.chunk.ChunkParserI):
    """Custom ChunkParser used in the Chat class for chunking POS-tagged text.

    The chunks here represent named entities and action labels that help determine what
    GZ should do in response to text input.
    """

    # These sets are mini-corpora for checking input and determining intent
    create_actions = {'create', 'add', 'generate', 'make'}
    dev_titles = {'data', 'scientist', 'software', 'developer', 'engineer', 'coder', 'programmer'}
    design_titles = {'content', 'creative', 'designer', 'ux'}
    greetings = {'hey', 'hello', 'sup', 'greetings', 'hi', 'yo'}
    gz_aliases = {'godzillops', 'godzilla', 'zilla', 'gojira'}
    cancel_actions = {'stop', 'cancel', 'nevermind', 'quit'}
    email_regexp = re.compile('[^@]+@[^@]+\.[^@]+', re.IGNORECASE)

    def __init__(self):
        """Initialize the GZChunker class and any members that need to be created at runtime."""
        # Create a set of names from the NLTK names corpus - used for PERSON recognition
        self.names = set(names.words())

    def parse(self, tagged_text, action_state):
        """Implementing ChunkParserI's parse method.

        This method parses the POS tagged text and splits the text up into actionable chunks for Godzillops.

        Args:
            tagged_text (generator): Generator containing tuples of word & POS tag.
            action_state (dict): Current action for a given user (if mid unfinished action).

        Returns:
            Tree: Tree representing the different chunks of the text.
        """
        logging.debug(tagged_text)
        iobs = []
        # in_dict is used to keep track of mid sentence context when deciding
        # how to chunk the tagged sentence into meaningful pieces.
        in_dict = defaultdict(bool)

        # use previous action state to default in_dict
        if action_state.get('action') == 'create_google_account':
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
                iobs.append(self._parse_job_title(in_dict, word, tag, lword))
            elif self.email_regexp.match(lword):
                # This is probably an email address
                iobs.append((word, 'NN', 'I-EMAIL'))
            else:
                in_dict['person'] = False
                iobs.append((word, tag, 'O'))


        return nltk.chunk.conlltags2tree(iobs)

    def _parse_job_title(self, in_dict, word, tag, lword):
        """Parse Job Titles from inside the ChunkerParser

        Parsing possible titles was getting complicated, so moved to helper method.

        Args:
            in_dict (dict): Dictionary for keeping track of text context.
            word (str): Current word we are parsing (original case).
            tag (str): Current word we are parsing's POS.
            lword (str): Current word we are parsing (lowered case).

        Returns:
            tuple: IOB Tag containing the word, POS, and chunk label
        """
        probably_dev = lword in self.dev_titles
        probably_design = lword in self.design_titles

        # Use POS to capture possible google grouping
        if probably_dev:
            job_title_tag = 'GDEV'
        elif probably_design:
            job_title_tag = 'GDES'
        else:
            job_title_tag = 'NP'

        probably_job_title = any([probably_dev,
                                  probably_design,
                                  tag.startswith('NP')])

        if probably_job_title and in_dict['finding_title']:
            return (word, job_title_tag, 'I-JOB_TITLE')
        elif probably_job_title:
            in_dict['finding_title'] = True
            return (word, job_title_tag, 'B-JOB_TITLE')
        elif 'finding_title' in in_dict:
            del in_dict['finding_title']
            del in_dict['check_for_title']

        return (word, tag, 'O')


class Chat(object):
    """Main class of the Godzillops chat bot.

    Instantiated in the Tokyo runtime for handling responses to chat input.
    """

    def __init__(self, config):
        """Initialize the Godzillops chat bot brains.

        Creates a tokenizer, tagger, and customized chunker for NLP.

        Args:
            config (module): Python module storing configuration variables and secrets.
                Used to authenticate API services and connect data stores.
        """
        self.config = config
        # Context is a dictionary containing information about the user we're
        # chatting with - user name, admin, and timezone information
        self.context = {}

        logging.debug('Initialize Tokenizer')
        self.tokenizer = TweetTokenizer()
        logging.debug('Initialize Tagger')
        self._create_tagger()
        logging.debug('Initialize Chunker')
        self.chunker = GZChunker()

        # Action state is a dictionary used for managing incomplete
        # actions - cases where Godzillops needs to clarify or ask for more
        # information before finishing an action.
        self.action_state = {}

    def _create_tagger(self):
        """Create our own classifier based POS tagger.

        It uses the brown corpus since it is included in it's entirety (as opposed to Penn Treebank).
        Meaning, Godzillops uses Brown POS tags - run nltk.help.brown_tagset() for descriptions
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
        """Determine Chat Bot's Actions

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

        if action == 'create_google_account' and action_state['step'] == 'username':
            # Short circuit subtree parsing and use all text as the given username
            import pudb; pudb.set_trace()  # XXX BREAKPOINT
            kwargs['username'] = chunked_text

        # Used to store named entities
        entity_dict = defaultdict(list)

        for subtree in chunked_text.subtrees():
            label = subtree.label()
            if label == 'GREETING':
                action = 'greet'
            elif label == 'GODZILLA' and not action:
                action = 'gz_gif'
            elif label == 'CREATE_GOOGLE_ACCOUNT':
                action = label.lower()
            elif label in ('EMAIL', 'PERSON'):
                entity_dict[label].append(' '.join(l[0] for l in subtree.leaves()))
            elif label in 'JOB_TITLE':
                # Store Full title name, and decide Google Groups based on custom POS tags
                job_title = []
                group_check = defaultdict(bool)
                for l in subtree.leaves():
                    job_title.append(l[0])
                    group_check['GDEV'] = l[1] == 'GDEV'
                    group_check['GDES'] = l[1] == 'GDES'
                entity_dict[label].append(' '.join(job_title))

                # Rather sure on google groups to add user to
                # since all title pieces were categorizable by dev or design title corpus
                if group_check['GDEV']:
                    entity_dict['GOOGLE_GROUPS'] = ['dev', 'aws_restricted']
                elif group_check['GDES']:
                    entity_dict['GOOGLE_GROUPS'] = ['design']
            elif label == 'CANCEL_ACTION' and action_state['action']:
                # Only set cancel if in a previous action
                action = 'cancel'

        # Prepare Kwargs for selected action
        if action != 'cancel':
            # Carry over previous kwargs
            kwargs = action_state.get('kwargs', {})
            if action == 'create_google_account':
                for label in ('JOB_TITLE', 'PERSON', 'EMAIL'):
                    if entity_dict[label]:
                        kwargs[label.lower()] = entity_dict[label][0]
                kwargs['google_groups'] = entity_dict['GOOGLE_GROUPS']

        return action, kwargs

    def respond(self, _input, context=None):
        """Respond to user input

        This function takes a string of input, tokenizes, tags & chunks it and then runs it through
        the determine action function to get a course of action to proceed with and executes said action.

        Args:
            _input (str): String of text sent from a tokyo platform user.
            context (Optional[dict]): A context dictionary sent from the tokyo platform containing
                information about the user sending the text (i.e. user id, timestamp of message).

        Returns:
            responses (generator): A generator of string responses from the Godzillops bot sent from the executed action.
        """
        responses = ()
        try:
            self._set_context(context)
            tokens = self.tokenizer.tokenize(_input)
            tagged_text = self.tagger.tag(tokens)
            chunked_text = self.chunker.parse(tagged_text, self._get_action_state())
            action, kwargs = self.determine_action(chunked_text)
            if action is not None:
                responses = getattr(self, action)(**kwargs)
        except:
            logging.exception("An error occurred responding to the user.")
            responses = ('I... Erm... What? Try again.',)
        return responses

    #
    # ACTION METHODS
    #

    def cancel(self):
        """Clear any current action state (cancel creating a google account, for example)."""
        self._clear_action_state()
        yield "Previous action canceled. I didn't want to do it anyways."

    def create_google_account(self, **kwargs):
        """Create a new Google user account

        Args:
            name (Optional[str]): Name of user, if not passed, will prompt for it.
            email (Optional[str]): Personal email address, if not passed, will prompt for it.
            job_title (Optional[str]): User's Job Title, if not passed, will prompt for it.
            google_groups (Optional[list]): List of Google groups to add a user to.
                Previously determined from job_title.
            username (Optional[str]): Specific username for user.
        """
        name = kwargs.get('person')
        email = kwargs.get('email')
        job_title = kwargs.get('job_title')
        google_groups = kwargs.get('google_groups')
        username = kwargs.get('username')
        all_good = name and email and job_title

        if not all_good:
            self._set_action_state(action='create_google_account',
                                   kwargs=kwargs)
            if not name:
                self._set_action_state(step='name')
                yield "What is the employee's full name?"
            elif not email:
                self._set_action_state(step='email')
                yield "What is a personal email address for {}?".format(name)
            elif not job_title:
                self._set_action_state(step='title')
                yield "What will {}'s job title be?".format(name)
        else:
            split_name = name.split(maxsplit=1)
            given_name = split_name[0]
            family_name = split_name[1] if len(split_name) > 1 else None
            if not family_name:
                self._set_action_state(action='create_google_account',
                                       kwargs=kwargs, step='name')
                yield "Google requires both a first and last name - lame right? What is the employee's first & last name?"
                return

            username = username or given_name.lower()
            yield "Okay, let me check if '{}' is an available Google username.".format(username)

            ga = GoogleAdmin(self.config.GOOGLE_SERVICE_ACCOUNT_JSON,
                             self.config.GOOGLE_SUPER_ADMIN)

            if not ga.is_username_available(username):
                self._set_action_state(action='create_google_account',
                                       kwargs=kwargs, step='username')
                suggestion = (given_name[0] + family_name).lower()
                yield ("Aw nuts, that name is taken. "
                       "Might I suggest a nickname or something like {}? "
                       "Either way, enter a new username for me to use.".format(suggestion))
            else:
                yield "We're good to go! Creating the new account now."
                ga.create_user(given_name, family_name, username, email, job_title, google_groups)
                yield "A new google user account for {} has been created!""What is the employee's name?"
                self._clear_action_state()

    def greet(self):
        """Say Hello back in response to a greeting from the user."""
        yield random.choice(list(self.chunker.greetings)).title()
        yield 'Can I help you with anything?'

    def gz_gif(self):
        """Return a random Godzilla GIF."""
        yield 'RAWR!'
        with urlreq.urlopen('http://api.giphy.com/v1/gifs/search?q=godzilla&api_key=dc6zaTOxFJmzC') as r:
            response = json.loads(r.read().decode('utf-8'))
            rand_index = random.choice(range(0,24))
            yield response['data'][rand_index]['images']['downsized']['url']
