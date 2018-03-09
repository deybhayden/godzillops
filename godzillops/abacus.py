# -*- coding: utf-8 -*-
"""abacus.py - Abacus/Zapier integration

The AbacusAdmin class serves as an interface to a Zapier Webhook built to "trigger"
an Abacus "Invite New User" action in Zapier. Right now it is used for inviting users
to a specified organization.
"""
import json
import logging
import urllib.request as urlreq


class AbacusAdmin(object):
    """AbacusAdmin class is a simple interface in front of Zapier Webhook

    This class takes a single configuration piece - zapier webhook - and
    returns a class instance capable of doing basic Abacus member management.
    """

    def __init__(self, zapier_webhook):
        """Initialize Abacus API Interface

        Passed a Zapier webhook, this function initializes the AbacusAdmin
        class by setting API urls accordingly.

        Args:
            zapier_webhook (str): The Zapier webhook URL to POST to when inviting new users.
        """
        self.zapier_webhook = zapier_webhook

    def invite_to_abacus(self, email):
        success = False
        data = json.dumps({'email': email}).encode()
        req = urlreq.Request(
            url=self.zapier_webhook,
            data=data,
            method='POST',
            headers={'Content-Type': 'application/json'})
        with urlreq.urlopen(req) as f:
            logging.info('Invite to Abacus URL Request Status - {}'.format(f.status))
            success = f.status == 200
        return success
