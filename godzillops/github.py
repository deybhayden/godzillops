# -*- coding: utf-8 -*-
"""github.py - GitHub API methods

The GitHubAdmin class serves as an interface to GitHub APIs. Right now it
is used for inviting users to a specified organization.
"""
import json
import logging
import urllib.request as urlreq


class GitHubAdmin(object):
    """GitHubAdmin class is a simple interface in front of GitHub's HTTP API

    This class takes a couple configuration pieces - api key & token - and
    returns a class instance capable of doing basic github member management.
    """

    def __init__(self, github_org, github_access_token):
        """Initialize GitHub API Interface

        Passed a GitHub organizaion and appropriate authentication credentials,
        this function initializes the GitHubAdmin class by setting API urls accordingly.

        Args:
            github_org (str): The orgId or name of a github organization.
            github_access_token (str): The oauth token of an admin/owner for the passed organization.
        """
        self.github_org = github_org
        self.github_api_url = "https://api.github.com/{0}?access_token=" + github_access_token

    def invite_to_github(self, username, teams):
        success = False
        data = json.dumps({"role": "member"}).encode()
        for team in teams:
            members_url = self.github_api_url.format(
                "teams/{}/memberships/{}".format(team, username)
            )
            req = urlreq.Request(
                url=members_url,
                data=data,
                method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urlreq.urlopen(req) as f:
                logging.info("Invite to github URL Request Status - %s", f.status)
                success = f.status == 200
        return success
