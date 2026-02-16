import requests
import os
class GitHubClient:
    def __init__(self):
        self.base = 'https://api.github.com'
        self.headers = {'Authorization': f'token {os.getenv("GITHUB_TOKEN")}'}
    def get_repos(self, user):
        return requests.get(f'{self.base}/users/{user}/repos', headers=self.headers).json()