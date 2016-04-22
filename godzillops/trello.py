# -*- coding: utf-8 -*-
"""trello.py - Trello API methods

The TrelloAdmin class serves as an interface to Trello APIs for adding
users and to a organization's groupmanaging groups.

Attributes:
"""
import logging
import urllib.parse as urlparse
import urllib.request as urlreq


class TrelloAdmin(object):
    """TrelloAdmin class is a simple interface in front of Trello's HTTP API

    This class takes a couple configuation pieces - api key & token - and
    returns a class instance capable of doing basic trello member management.
    """
    def __init__(self, trello_org, trello_api_key, trello_token):
        """Initialize Trello API Interface

        Passed a Trello organizaion and appropriate authentication credentials,
        this function initializes the TrelloAdmin class by setting API urls accordingly.

        Args:
            trello_org (str): The orgId or name of a Trello organization.
            trello_api_key (str): The public api key of a trello user.
            trello_token (str): The private token of an admin user for the passed organization.
        """
        self.trello_org = trello_org
        self.trello_api_url = "https://api.trello.com/1/{0}?key="+trello_api_key+"&token="+trello_token

    def invite_to_trello(self, email, full_name):
        success = False
        data = urlparse.urlencode({'email': email, 'fullName': full_name}).encode()
        members_url = self.trello_api_url.format('organizations/{}/members'
                                                 .format(self.trello_org))
        req = urlreq.Request(url=members_url, data=data, method='PUT')
        with urlreq.urlopen(req) as f:
            logging.info('Invite to Trello URL Request Status - {}'.format(f.status))
            success = f.status == 200
        return success
