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
from .trello import TrelloAdmin
from .github import GitHubAdmin


CACHE_DIR = os.path.join(tempfile.gettempdir(), 'godzillops')


class GZChunker(nltk.chunk.ChunkParserI):
    """Custom ChunkParser used in the Chat class for chunking POS-tagged text.

    The chunks here represent named entities and action labels that help determine what
    GZ should do in response to text input.
    """

    # These sets are mini-corpora for checking input and determining intent
    create_actions = {'create', 'add', 'generate', 'make'}
    invite_actions = {'add', 'invite'}
    dev_titles = {'data', 'scientist', 'software', 'developer', 'engineer', 'coder', 'programmer'}
    design_titles = {'content', 'creative', 'designer', 'ux', 'product', 'graphic'}
    greetings = {'hey', 'hello', 'sup', 'greetings', 'hi', 'yo', 'howdy'}
    gz_aliases = {'godzillops', 'godzilla', 'zilla', 'gojira', 'gz'}
    cancel_actions = {'stop', 'cancel', 'nevermind', 'quit'}
    yes = {'yes', 'yeah', 'yep', 'yup', 'sure'}
    no = {'no', 'nope', 'nah'}
    email_regexp = re.compile('[^@]+@[^@]+\.[^@]+', re.IGNORECASE)

    def __init__(self):
        """Initialize the GZChunker class and any members that need to be created at runtime."""
        # Create a set of names from the NLTK names corpus - used for PERSON recognition
        self.names = set(names.words())

    def _generate_in_dict(self, action_state):
        """Use previous action state to default in_dict

        Args:
            action_state (dict): Current action for a given user (if in the middle of an unfinished action).
        Returns:
            in_dict (dict): Used to keep track of mid-sentence context when deciding
                how to chunk the tagged sentence into meaningful pieces.
        """
        in_dict = defaultdict(bool)
        action = action_state.get('action')

        if action == 'create_google_account':
            in_dict['create_action'] = True
            in_dict['create_google_account'] = True
            if action_state['step'] == 'title':
                in_dict['check_for_title'] = True
        elif action == 'invite_to_trello':
            in_dict['invite_action'] = True
            in_dict['invite_to_trello'] = True
        elif action == 'invite_to_github':
            in_dict['invite_action'] = True
            in_dict['invite_to_github'] = True

        return in_dict

    def parse(self, tagged_text, action_state):
        """Implementing ChunkParserI's parse method.

        This method parses the POS tagged text and splits the text up into actionable chunks for Godzillops.

        Args:
            tagged_text (generator): Generator containing tuples of word & POS tag.
            action_state (dict): Current action for a given user (if in the middle of an unfinished action).

        Returns:
            Tree: Tree representing the different chunks of the text.
        """
        logging.debug(tagged_text)

        iobs = []
        in_dict = self._generate_in_dict(action_state)
        i = 0
        tagged_len = len(tagged_text)

        while i < tagged_len:
            word, tag = tagged_text[i]
            i += 1
            lword = word.lower()
            # They said our name!
            if lword in self.gz_aliases:
                iobs.append((word, tag, 'B-GODZILLA'))
            # They said hello!
            elif lword in self.greetings:
                in_dict['greeting'] = True
                iobs.append((word, tag, 'B-GREETING'))
            # Named Entity Recognition - Find People
            elif word in self.names or in_dict['person'] and (word[0].isupper() or tag.startswith('NP')):
                if in_dict['person']:
                    iobs.append((word, tag, 'I-PERSON'))
                else:
                    iobs.append((word, tag, 'B-PERSON'))
                    in_dict['person'] = True
            # Named Entity Recognition - Find Emails
            elif self.email_regexp.match(lword):
                # This is probably an email address
                if lword.startswith('<mailto:') and lword.endswith('>'):
                    # Slack auto-formats email addresses like this:
                    # <mailto:hayden767@gmail.com|hayden767@gmail.com>
                    # Strip that before returning in parsed tree
                    lword = lword.split('|')[-1][:-1]
                iobs.append((lword, 'NN', 'B-EMAIL'))
            # Named Entity Recognition - Usernames
            elif lword.startswith('@'):
                # Chunk as a username and lose the @ symbol
                iobs.append((lword[1:], tag, 'B-USERNAME'))
            # CREATE ACTIONS
            elif lword in self.create_actions and tag.startswith('VB'):
                in_dict['create_action'] = True
                if lword in self.invite_actions:
                    # 'add' is shared by both, no harm (yet) in setting both
                    in_dict['invite_action'] = True
                iobs.append((word, tag, 'O'))
            elif in_dict['create_action'] and lword == 'google':
                in_dict['create_google_account'] = True
                iobs.append((word, tag, 'B-CREATE_GOOGLE_ACCOUNT'))
            elif in_dict['create_google_account'] and lword == 'title':
                in_dict['check_for_title'] = True
                in_dict['title'] = []
                iobs.append((word, tag, 'O'))
            elif in_dict['check_for_title']:
                iobs.append(self._parse_job_title(in_dict, word, tag, lword))
            # INVITE ACTIONS
            elif lword in self.invite_actions and tag.startswith('VB'):
                in_dict['invite_action'] = True
                iobs.append((word, tag, 'O'))
            elif in_dict['invite_action'] and lword == 'trello':
                in_dict['invite_to_trello'] = True
                iobs.append((word, tag, 'B-INVITE_TO_TRELLO'))
            elif in_dict['invite_action'] and lword == 'github':
                in_dict['invite_to_github'] = True
                iobs.append((word, tag, 'B-INVITE_TO_GITHUB'))
            # CANCEL ACTION
            elif lword in self.cancel_actions and not iobs:
                got_something_to_cancel = False
                for running_action in ('create_action', 'invite_action'):
                    if in_dict[running_action]:
                        got_something_to_cancel = True
                        break
                if got_something_to_cancel:
                    # Only recognize cancel action by itself, and return immediately
                    # when it is encountered
                    iobs.append((word, tag, 'B-CANCEL'))
                    break
            # Just a word, tag it and move on
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

        # API Admin Classes - used to execute API-driven actions
        self.google_admin = GoogleAdmin(self.config.GOOGLE_SERVICE_ACCOUNT_JSON,
                                        self.config.GOOGLE_SUPER_ADMIN)
        self.trello_admin = TrelloAdmin(self.config.TRELLO_ORG,
                                        self.config.TRELLO_API_KEY,
                                        self.config.TRELLO_TOKEN)
        self.github_admin = GitHubAdmin(self.config.GITHUB_ORG,
                                        self.config.GITHUB_ACCESS_TOKEN,
                                        self.config.GITHUB_TEAM)

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

    def determine_action(self, chunked_text, action_state):
        """Determine Chat Bot's Actions

        This function takes a Tree of chunked text, reads through the
        different subtrees and determines what the bot should do next.

        Args:
            chunked_text (Tree): A tree of chunked text produced by the GZChunker class.
            action_state (dict): Current action for a given user (if mid unfinished action).

        Returns:
            tuple: A tuple with two items:
                action (str): This string corresponds to the keys in the self.actions mapping.
                    Whatever the value is determines what function will be ran in self.respond.
                kwargs (dict): Dynamic keyword arguments passed to each action function.
        """
        logging.debug(chunked_text)
        action = action_state.get('action')
        kwargs = action_state.get('kwargs', {})

        if action == 'create_google_account' and action_state['step'] == 'username':
            # Short circuit subtree parsing, and treat first leaf as a username
            kwargs['username'], _ = chunked_text.leaves()[0]
            return action, kwargs
        elif action == 'invite_to_github' and action_state['step'] == 'username':
            # Short circuit subtree parsing, and treat all leaves as usernames
            kwargs['usernames'] = [u for u, _ in chunked_text.leaves()]
            return action, kwargs

        # Used to store named entities
        entity_dict = defaultdict(list)

        for subtree in chunked_text.subtrees():
            label = subtree.label()
            if label == 'GREETING':
                # Default to say hi, if they did - will probably be overridden
                action = 'greet'
            elif label == 'GODZILLA' and not action:
                # Return a gif if they didn't say anything but our name
                action = 'gz_gif'
            elif label.startswith(('CREATE_', 'INVITE_')):
                action = label.lower()
            elif label in ('EMAIL', 'PERSON', 'USERNAME'):
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
                for glabel in ('GDES', 'GDEV'):
                    if group_check[glabel]:
                        entity_dict['GOOGLE_GROUPS'] += self.config.GOOGLE_GROUPS[glabel]
            elif label == 'CANCEL' and action_state['action']:
                # Only set cancel if in a previous action
                action = 'cancel'

        if action != 'cancel':
            # Prepare New Kwarg Values for selected action
            if action in ('create_google_account', 'invite_to_trello'):
                for label in ('JOB_TITLE', 'PERSON', 'EMAIL'):
                    if entity_dict[label]:
                        kwargs[label.lower()] = entity_dict[label][0]
                if entity_dict['GOOGLE_GROUPS']:
                    kwargs['google_groups'] = entity_dict['GOOGLE_GROUPS']
            elif action in ('invite_to_github',):
                kwargs['usernames'] = entity_dict.get('USERNAME', [])

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
            # Set current message context - Who are we talking too? Where are they at?
            self._set_context(context)
            # Get current action state - if we are currently doing something for this user already.
            action_state = self._get_action_state()

            # Tokenize raw _input
            if action_state.get('regexp_tokenize'):
                 # Use simple alphanumeric Regex - used in some actions
                tokens = nltk.regexp_tokenize(_input, "[\w]+")
            else:
                # Use Twitter Tokenizer - split by space, punctuation but not on @ & #
                tokens = self.tokenizer.tokenize(_input)

            # Tag for POS using Brown corpus ClassifierBasedPOSTagger
            tagged_text = self.tagger.tag(tokens)
            # Parse the text using GZChunker into actionable chunks
            chunked_text = self.chunker.parse(tagged_text, action_state)
            # Determine what the action should be, and prepare keyword args for the returned function
            action, kwargs = self.determine_action(chunked_text, action_state)

            if action is not None:
                # If we should take action, execute the function with the kwargs
                # now and return the results
                responses = getattr(self, action)(**kwargs)
        except:
            logging.exception("An error occurred responding to the user.")
            responses = ('I... erm... what? Try again.',)
        return responses

    #
    # ACTION METHODS
    #

    def cancel(self, **kwargs):
        """Clear any current action state (cancel creating a google account, for example)."""
        self._clear_action_state()
        yield "Previous action canceled. I didn't want to do it anyways."

    # TODO: Figure out action chaining & confirmation
    # def confirm(self, **kwargs):
    #     """Confirm via Yes/No text if the next action in a chain of actions should be ran.

    #     Args:
    #         run_action (bool): If true, run the 'next_action' function, otherwise don't.
    #         action_chain list[tuple]: A list of pairs, matching a message to prompt the user for confirmation and an action function to run.
    #     """
    #     run_action = kwargs.pop('run_action')
    #     action_chain = kwargs.pop('action_chain')
    #     if action_chain:
    #         _, next_action = action_chain.pop()
    #         if run_action:
    #             for response in getattr(self, next_action)(**kwargs):
    #                 yield response
    #             kwargs['action_chain'] = action_chain
    #             self._set_action_state(action='confirm',
    #                                    kwargs=kwargs)
    #             yield action_chain[0][0]
    #     else:
    #         self._clear_action_state()

    def create_google_account(self, **kwargs):
        """Create a new Google user account

        Args:
            person (Optional[str]): Full name of user, if not passed, will prompt for it.
            email (Optional[str]): Personal email address, if not passed, will prompt for it.
            job_title (Optional[str]): User's Job Title, if not passed, will prompt for it.
            google_groups (Optional[list]): List of Google groups to add a user to.
                Previously determined from job_title.
            username (Optional[str]): Specific username for user.
        """
        split_name = kwargs.get('person', '').split(maxsplit=1)
        split_name_len = len(split_name)
        if split_name_len == 2:
            given_name, family_name = split_name
        elif split_name_len == 1:
            given_name, family_name = split_name[0], None
        else:
            given_name, family_name = None, None
        email = kwargs.get('email')
        job_title = kwargs.get('job_title')
        all_good = given_name and family_name and email and job_title

        if not all_good:
            self._set_action_state(action='create_google_account',
                                   kwargs=kwargs)
            if not (given_name and family_name):
                self._set_action_state(step='name')
                yield "What is the employee's full name (first & last)?"
            elif not email:
                self._set_action_state(step='email')
                yield "What is a personal email address for {}?".format(given_name)
            elif not job_title:
                self._set_action_state(step='title')
                yield "What is {}'s job title?".format(given_name)
        else:
            username = kwargs.get('username', given_name.lower())
            yield "Okay, let me check if '{}' is an available Google username.".format(username)

            if not self.google_admin.is_username_available(username):
                self._set_action_state(action='create_google_account',
                                       kwargs=kwargs, step='username',
                                       regexp_tokenize=True)
                suggestion = (given_name[0] + family_name).lower()
                yield ("Aw nuts, that name is taken. "
                       "Might I suggest a nickname or something like {}? "
                       "Either way, enter a new username for me to use.".format(suggestion))
            else:
                yield "We're good to go! Creating the new account now."
                responses = self.google_admin.create_user(given_name, family_name,
                                                          username, email, job_title,
                                                          kwargs.get('google_groups'))
                for response in responses:
                    yield response
                yield "Google account creation complete! What's next?"
                self._clear_action_state()

    def invite_to_trello(self, **kwargs):
        """Invite a user to a Trello organization

        Args:
            person (Optional[str]): Name of user, if not passed, will prompt for it.
            email (Optional[str]): Google apps address, if not passed, will prompt for it.
        """
        name = kwargs.get('person')
        email = kwargs.get('email')
        all_good = name and email

        if not all_good:
            self._set_action_state(action='invite_to_trello',
                                   kwargs=kwargs)
            if not name:
                self._set_action_state(step='name')
                yield "What is the user's full name?"
            elif not email or not email.endswith(self.google_admin.primary_domain):
                self._set_action_state(step='email')
                yield "What is {}'s {} email address?".format(name, self.google_admin.primary_domain)
        else:
            success = self.trello_admin.invite_to_trello(email, name)
            if success:
                yield "I have invited {} to join *{}* in Trello!".format(email, self.trello_admin.trello_org)
            else:
                yield "Huh, that didn't work, check out the logs?"
            self._clear_action_state()

    def invite_to_github(self, **kwargs):
        """Invite a user to a GitHub organization

        Args:
            usernames (Optional[list]): List of GitHub usernames, if not passed, will prompt for it.
        """
        usernames = kwargs.get('usernames')

        if not usernames:
            self._set_action_state(action='invite_to_github',
                                   kwargs=kwargs, step='username',
                                   regexp_tokenize=True)
            yield "Please list the GitHub username(s) so I can send out an invite."
        else:
            for username in usernames:
                success = self.github_admin.invite_to_github(username)
                if success:
                    message = "I have invited `{}` to join *{}* in GitHub!"
                else:
                    message = "Huh, I couldn't add `{}` to *{}* in GitHub."
                yield message.format(username, self.github_admin.github_org)
            self._clear_action_state()

    def greet(self, **kwargs):
        """Say Hello back in response to a greeting from the user."""
        yield random.choice(list(self.chunker.greetings)).title()
        yield 'Can I help you with anything?'

    def gz_gif(self, **kwargs):
        """Return a random Godzilla GIF."""
        yield 'RAWR!'
        with urlreq.urlopen(self.config.GZ_GIF_URL) as r:
            response = json.loads(r.read().decode('utf-8'))
            rand_index = random.choice(range(0, 24))
            yield response['data'][rand_index]['images']['downsized']['url']
