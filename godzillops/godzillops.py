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
import urllib.request as urlreq
from collections import defaultdict
from datetime import datetime

import nltk
from dateutil.tz import tzlocal
from nltk.tokenize import TweetTokenizer

from .abacus import AbacusAdmin
from .github import GitHubAdmin
from .google import GOOGLE_GROUP_TAGS, GoogleAdmin
from .trello import TrelloAdmin


class GZChunker(nltk.chunk.ChunkParserI):
    """Custom ChunkParser used in the Chat class for chunking POS-tagged text.

    The chunks here represent named entities and action labels that help determine what
    GZ should do in response to text input.
    """

    # These sets are mini-corpora for checking input and determining intent
    create_actions = {'create', 'add', 'generate', 'make'}
    invite_actions = {'add', 'invite'}
    dev_titles = {'data', 'scientist', 'software', 'developer', 'engineer', 'coder', 'programmer'}
    design_titles = {'designer', 'ux', 'product', 'graphic'}
    founder_titles = {'founder', 'ceo', 'cto', 'gm', 'general', 'manager'}
    creative_titles = {'content', 'creative'}
    greetings = {'hey', 'hello', 'sup', 'greetings', 'hi', 'yo', 'howdy'}
    gz_aliases = {'godzillops', 'godzilla', 'gojira', 'gz'}
    cancel_actions = {'stop', 'cancel', 'nevermind', 'quit'}
    yes = {'yes', 'yeah', 'yep', 'yup', 'sure'}
    no = {'no', 'nope', 'nah'}
    email_regexp = re.compile(r'[^@]+@[^@]+\.[^@]+', re.IGNORECASE)

    def __init__(self, config):
        """Initialize the GZChunker class and any members that need to be created at runtime.

        Args:
            config (module): Python module storing configuration variables and secrets.
                Used to authenticate API services and connect data stores.
        """
        self.config = config

    def _generate_in_dict(self, action_state):
        """Use previous action state to default in_dict

        Args:
            action_state (dict): Current action for a given user (if in the middle of an unfinished action).
        Returns:
            in_dict (dict): Used to keep track of mid-sentence context when deciding
                how to chunk the tagged sentence into meaningful pieces.
        """
        in_dict = defaultdict(bool)
        action = action_state.get('action') or ''

        if action == 'create_google_account':
            in_dict['create_action'] = True
            in_dict['create_google_account'] = True
            if action_state['step'] == 'title':
                in_dict['check_for_title'] = True
        elif action.startswith('invite_to'):
            in_dict['invite_action'] = True
            in_dict[action] = True

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
                iobs.append((word, tag, 'B-GREETING'))
            # Named Entity Recognition - Find Emails
            elif self.email_regexp.match(lword):
                # This is probably an email address
                if lword.startswith('<mailto:') and lword.endswith('>'):
                    # Slack auto-formats email addresses like this:
                    # <mailto:hayden767@gmail.com|hayden767@gmail.com>
                    # Strip that before returning in parsed tree
                    lword = lword.split('|')[-1][:-1]
                if lword.startswith('mailto:'):
                    # Protect from copy paste
                    lword = lword.split(':', 1)[1]
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
            elif lword in self.config.GOOGLE_DEV_ROLES or lword in self.config.GITHUB_DEV_ROLES:
                iobs.append((lword, tag, 'B-DEV_ROLE'))
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
            elif in_dict['invite_action'] and lword == 'abacus':
                in_dict['invite_to_abacus'] = True
                iobs.append((word, tag, 'B-INVITE_TO_ABACUS'))
            # CANCEL ACTION
            elif lword in self.cancel_actions and (in_dict['create_action'] or in_dict['invite_action']) and not iobs:
                # Only recognize cancel action by itself, and return immediately
                # when it is encountered
                iobs.append((word, tag, 'B-CANCEL'))
                break
            # Named Entity Recognition - Handle All Previously Unmatched Proper Nouns
            elif tag.startswith('NP') or (in_dict['person'] and word[0].isupper()):
                if in_dict['person']:
                    iobs.append((word, tag, 'I-PERSON'))
                else:
                    iobs.append((word, tag, 'B-PERSON'))
                    in_dict['person'] = True
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
        probably_creative = lword in self.creative_titles
        probably_founder = lword in self.founder_titles

        # Use POS to capture possible google grouping
        if probably_dev:
            job_title_tag = 'GDEV'
        elif probably_design:
            job_title_tag = 'GDES'
        elif probably_creative:
            job_title_tag = 'GCRE'
        elif probably_founder:
            job_title_tag = 'GFOU'
        else:
            job_title_tag = 'NP'

        probably_job_title = any([probably_dev,
                                  probably_design,
                                  probably_creative,
                                  probably_founder,
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

# == END of GZChunker ===


def requires_admin(fxn):
    """Require admin privileges before executing a function

    Using Chat.context (the first argument of the function - i.e. self), see
    if the 'admin' key is set to True. If so, run the function.

    Args:
        fxn (function): The function being protected by the admin check.
    Returns:
        responses (generator): A generator of string responses from the executed function.
            An empty tuple will be returned if permission is denied.
    """
    def wrapped_fxn(*args, **kwargs):
        self = args[0]
        if self.context['admin']:
            logging.info('Admin access granted to user "%s"', self.context['user']['name'])
            return fxn(*args, **kwargs)
        else:
            return ()
    return wrapped_fxn


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
        self.chunker = GZChunker(config=config)

        # API Admin Classes - used to execute API-driven actions
        self.google_admin = GoogleAdmin(self.config.GOOGLE_SERVICE_ACCOUNT_JSON,
                                        self.config.GOOGLE_SUPER_ADMIN,
                                        self.config.GOOGLE_CALENDAR_ID,
                                        self.config.GOOGLE_WELCOME_TEXT,
                                        self.config.GOOGLE_WELCOME_ATTACHMENTS)
        self.trello_admin = TrelloAdmin(self.config.TRELLO_ORG,
                                        self.config.TRELLO_API_KEY,
                                        self.config.TRELLO_TOKEN)
        self.github_admin = GitHubAdmin(self.config.GITHUB_ORG,
                                        self.config.GITHUB_ACCESS_TOKEN)
        self.abacus_admin = AbacusAdmin(self.config.ABACUS_ZAPIER_WEBHOOK)

        # Action state is a dictionary used for managing incomplete
        # actions - cases where Godzillops needs to clarify or ask for more
        # information before finishing an action.
        self.action_state = {}

    def _create_tagger(self):
        """Create our own classifier based POS tagger.

        It uses the brown corpus since it is included in it's entirety (as opposed to Penn Treebank).
        Meaning, Godzillops uses Brown POS tags - run nltk.help.brown_tagset() for descriptions
        of each POS tag.

        The tagger is read from a pickle for performance reasons. To generate the tagger from scratch,
        you would run:

        .. highlight::

            from nltk.corpus import brown
            from nltk.tag.sequential import ClassifierBasedPOSTagger

            self.tagger = ClassifierBasedPOSTagger(train=brown.tagged_sents())
            with open('tagger.pickle', 'wb') as tagger_pickle:
                pickle.dump(self.tagger, tagger_pickle)
        """
        tagger_path = os.path.join(os.path.dirname(__file__), 'tagger.pickle')
        with open(tagger_path, 'rb') as tagger_pickle:
            self.tagger = pickle.load(tagger_pickle)
            logging.debug("tagger.pickle loaded from cache")

    #
    # ACTION STATE HELPERS - used to manager per user action states - or continued
    # actions over chat
    #

    def _clear_action_state(self, action_success, admin_required=False):
        """Clear existing action state for the user.

        The current action is stored in a user-keyed dictionary containing the action name and
        accompanying kwargs. It is cleared upon the 'completion' of an action - successful or not.

        Args:
            action_success (bool): True if the action was successful, False otherwise
            admin_required (bool): True if the action was an administrator action, False by default.
        Returns:
            completed_dict (dict): A dictionary representing information about the completed action and
                if it was successful or not.
        """
        old_action_state = self.action_state.pop(self.context['user']['id'], {})
        completed_dict = {'admin_action_complete': action_success and admin_required and self.context['admin']}

        message = 'I have done nothing.'
        completed_action = old_action_state.get('action')
        if action_success:
            message = 'At the bidding of my master ({}), '.format(self.context['user']['name'])
            if completed_action == 'create_google_account':
                message += 'I have created a new Google Account for {person}.'.format(**old_action_state['kwargs'])
            elif completed_action == 'invite_to_trello':
                message += 'I have invited {person} <{email}> to join our Trello organization.'.format(**old_action_state['kwargs'])
            elif completed_action == 'invite_to_github':
                message += 'I have invited {} to join our GitHub organization.'.format(old_action_state['kwargs']['username'])
            elif completed_action == 'invite_to_abacus':
                message += 'I have invited <{email}> to join our Abacus organization.'.format(**old_action_state['kwargs'])
            else:
                message = 'Command completed.'
        else:
            message = 'I have failed you.'

        completed_dict['message'] = message
        return completed_dict

    def _get_action_state(self):
        return self.action_state.get(self.context['user']['id'], {})

    def _set_action_state(self, **action_state):
        self.action_state.setdefault(self.context['user']['id'], {})
        self.action_state[self.context['user']['id']].update(action_state)

    def _set_context(self, context):
        """Set the message context dictionary.

        This context dict contains the username & timezone.

        Args:
            context (dict): Passed dictionary containing the message's context:
                username, timezone, etc.
        """
        now = datetime.now(tzlocal())
        if context is None:
            self.context = {'user': {'id': 'text', 'name': 'text',
                                     'tz': now.tzname(), 'tz_offset': 0},
                            'admin': True}
        else:
            if 'user' not in context:
                raise ValueError('Invalid message context. The "user" key is required.')
            self.context = context
            self.context['admin'] = self.context['user']['id'] in self.config.ADMINS

        # Use the time that the chat instance is running
        # with for future date time math
        self.context['gz_timestamp'] = now

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
            # Short circuit subtree parsing, and treat all leaves as username
            kwargs['username'], _ = chunked_text.leaves()[0]
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
            elif label in ('EMAIL', 'PERSON', 'USERNAME', 'DEV_ROLE'):
                entity_dict[label].append(' '.join(l[0] for l in subtree.leaves()))
            elif label in 'JOB_TITLE':
                # Store Full title name, and decide Google Groups based on custom POS tags
                job_title = []
                group_check = defaultdict(bool)
                for l in subtree.leaves():
                    job_title.append(l[0])
                    for gtag in GOOGLE_GROUP_TAGS:
                        group_check[gtag] = l[1] == gtag
                entity_dict[label].append(' '.join(job_title))

                # Rather sure on google groups to add user to since all title
                # pieces were categorizable by dev, design, or multimedia title corpus
                for glabel in GOOGLE_GROUP_TAGS:
                    if group_check[glabel]:
                        entity_dict['GOOGLE_GROUPS'] += self.config.GOOGLE_GROUPS[glabel]
            elif label == 'CANCEL' and action_state['action']:
                # Only set cancel if in a previous action
                action = 'cancel'

        if action != 'cancel':
            # Prepare New Kwarg Values for selected action
            for label in ('JOB_TITLE', 'PERSON', 'EMAIL', 'USERNAME'):
                if entity_dict[label]:
                    kwargs[label.lower()] = entity_dict[label][0]
            if entity_dict['GOOGLE_GROUPS']:
                kwargs['google_groups'] = entity_dict['GOOGLE_GROUPS']

            if entity_dict['DEV_ROLE']:
                if 'google_groups' in kwargs:
                    kwargs['google_groups'] += entity_dict['DEV_ROLE']
                else:
                    kwargs['dev_role'] = entity_dict['DEV_ROLE'][0]

        # Update current action state with determined course of action
        self._set_action_state(action=action, kwargs=kwargs)

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
                tokens = nltk.regexp_tokenize(_input, r"[\w]+")
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
        yield "Previous action canceled. I didn't want to do it anyways."
        yield self._clear_action_state(action_success=True)

    @requires_admin
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
        google_groups = kwargs.get('google_groups')
        all_good = given_name and family_name and email and job_title

        if not all_good:
            if not (given_name and family_name):
                self._set_action_state(step='name')
                yield "What is the employee's full name (Capitalized First & Last)?"
            elif not email:
                self._set_action_state(step='email')
                yield "What is a personal email address for {}?".format(given_name)
            else:
                self._set_action_state(step='title')
                yield "What is {}'s job title?".format(given_name)
        elif google_groups and self.config.GOOGLE_GROUPS['GDEV'] == google_groups:
            # Is a developer
            self._set_action_state(step='dev_role',
                                   regexp_tokenize=True)
            yield ("I see we're adding a developer! What team will they be on? "
                   "Choose from: '{}'.".format("', '".join(self.config.GOOGLE_DEV_ROLES)))
        else:
            username = kwargs.get('username', given_name.lower())
            yield "Okay, let me check if '{}' is an available Google username.".format(username)

            if not self.google_admin.is_username_available(username):
                self._set_action_state(step='username',
                                       regexp_tokenize=True)
                suggestion = (given_name[0] + family_name).lower()
                yield ("Aw nuts, that name is taken. "
                       "Might I suggest a nickname or something like {}? "
                       "Either way, enter a new username for me to use.".format(suggestion))
            else:
                yield "We're good to go! Creating the new account now."
                responses = self.google_admin.create_user(given_name, family_name,
                                                          username, email, job_title, google_groups)
                for response in responses:
                    yield response
                yield "Google account creation complete! What's next?"
                yield self._clear_action_state(action_success=True, admin_required=True)

    @requires_admin
    def invite_to_trello(self, **kwargs):
        """Invite a user to a Trello organization

        Args:
            person (Optional[str]): Name of user, if not passed, will prompt for it.
            email (Optional[str]): Email address, if not passed, will prompt for it.
        """
        name = kwargs.get('person')
        email = kwargs.get('email')
        all_good = name and email

        if not all_good:
            if not name:
                self._set_action_state(step='name')
                yield "What is the user's full name?"
            else:
                self._set_action_state(step='email')
                yield "What is {}'s {} email address?".format(name, self.google_admin.primary_domain)
        else:
            success = self.trello_admin.invite_to_trello(email, name)
            if success:
                yield "I have invited {} to join *{}* in Trello!".format(email, self.trello_admin.trello_org)
            else:
                yield "Huh, that didn't work, check out the logs?"
            yield self._clear_action_state(success, admin_required=True)

    @requires_admin
    def invite_to_github(self, **kwargs):
        """Invite a user to a GitHub organization

        Args:
            username (Optional[str]): GitHub username, if not passed, will prompt for it.
            dev_role (Optional[str]): What dev role is this developer? If not passed, will prompt for it.
        """
        username = kwargs.get('username')
        dev_role = kwargs.get('dev_role')

        if not username:
            self._set_action_state(step='username', regexp_tokenize=True)
            yield "What is the GitHub username?"
        elif not dev_role:
            self._set_action_state(step='dev_role',
                                   regexp_tokenize=True)
            yield ("What will be the user's dev role on our team? "
                   "Choose from: '{}'.".format("', '".join(self.config.GITHUB_DEV_ROLES.keys())))
        else:
            success = self.github_admin.invite_to_github(username,
                                                         self.config.GITHUB_DEV_ROLES[dev_role])
            if success:
                message = "I have invited `{}` to join *{}* in GitHub!"
            else:
                message = "Huh, I couldn't add `{}` to *{}* in GitHub."
            yield message.format(username, self.github_admin.github_org)
            yield self._clear_action_state(success, admin_required=True)

    @requires_admin
    def invite_to_abacus(self, **kwargs):
        """Invite a user to a Abacus organization

        Args:
            email (Optional[str]): Email address, if not passed, will prompt for it.
        """
        email = kwargs.get('email')

        if not email:
            self._set_action_state(step='email')
            yield "What is the new user's {} email address?".format(self.google_admin.primary_domain)
        else:
            success = self.abacus_admin.invite_to_abacus(email)
            if success:
                yield "I have invited {} to join Abacus!".format(email)
            else:
                yield "Huh, that didn't work, check out the logs?"
            yield self._clear_action_state(success, admin_required=True)

    def greet(self, **kwargs):
        """Say Hello back in response to a greeting from the user."""
        yield random.choice(list(self.chunker.greetings)).title()
        yield 'Can I help you with anything?'
        yield self._clear_action_state(action_success=True)

    def gz_gif(self, **kwargs):
        """Return a random Godzilla GIF."""
        yield 'RAWR!'
        with urlreq.urlopen(self.config.GZ_GIF_URL) as r:
            response = json.loads(r.read().decode('utf-8'))
            rand_index = random.choice(range(0, 24))
            yield response['data'][rand_index]['images']['downsized']['url']
        yield self._clear_action_state(action_success=True)

# == END of Chat ===
