from collections import Counter
from github.PullRequest import PullRequest
from prettytable import PrettyTable
import pandas as pd
from kfcicli.utils import WithLogging

from kfcicli.repository import Client
from kfcicli.charms import LocalCharmRepo
from dataclasses import dataclass

@dataclass
class KubeflowRepo:
    repository: Client
    charms: list[LocalCharmRepo]

    def to_dict(self):

        branches = {charm.branch for charm in self.charms}
        # Verify consistency of branches
        assert len(branches) == 1

        return {
            "url": self.repository._git_repo.remote().url,
            "branch": list(branches)[0],
            "charms": [
                {"path": str(charm.tf_module.parent), "name": charm.name}
                for charm in self.charms
            ]
        }

class PullRequests(WithLogging):
    FIELD_NAMES = ["pr", "success", "failure", "skipped", "approvals",
                   "can_be_merged"]

    def __init__(self, pull_requests: dict[str, PullRequest]):
        self.pull_requests = pull_requests

    @staticmethod
    def _parse_row(pr: PullRequest) -> list:
        last_commit = pr.get_commits().reversed[0]

        cnt = Counter(
            [check.conclusion for check in last_commit.get_check_runs()])

        approvals = PullRequests._get_approved_reviews(pr)

        try:
            approval_ratio = approvals[0] * 1.0 / approvals[1]
        except ZeroDivisionError:
            approval_ratio = 0

        return [
            pr.html_url,
            cnt.get("success", 0),
            cnt.get("failure", 0),
            cnt.get("skipped", 0),
            f"{approvals[0]}/{approvals[1]}",
            pr.mergeable and approval_ratio == 1
        ]

    @staticmethod
    def _parse_row_as_dict(pr: PullRequest):
        return dict(zip(PullRequests.FIELD_NAMES, PullRequests._parse_row(pr)))

    @property
    def table(self):
        table = PrettyTable()
        table.field_names = ["repo"] + self.FIELD_NAMES

        for _id, pr in self.pull_requests.items():
            table.add_row([_id] + self._parse_row(pr))

        return str(table)

    @property
    def df(self):
        rows = {
            _id: self._parse_row(pr)
            for _id, pr in self.pull_requests.items()
        }

        return pd.DataFrame.from_dict(rows, orient="index", columns=self.FIELD_NAMES)

    @staticmethod
    def _get_approved_reviews(pr: PullRequest):
        states = [review.state for review in pr.get_reviews()]
        return len([state for state in states if state == "APPROVED"]), len(
            states)

    def merge(self, force=False):
        results = {}
        for _id, pr in self.pull_requests.items():

            if pr.is_merged():
                self.logger.info(f"PR {pr.html_url} already merged. Skipping.")
                results[_id] = None
                continue

            if not force:
                row = self._parse_row_as_dict(pr)
                if not row["can_be_merged"]:
                    self.logger.info(f"PR {pr.html_url} not mergeable. Skipping.")
                    results[_id] = None
                    continue

            results[_id] = pr.merge(
                commit_title=f"{pr.title} (#{pr.number})",
                commit_message="merged remotely by cli tool",
                merge_method="squash"
            )

        return results