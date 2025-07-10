This pull request first and foremost:
- migrates from `pip`/`pip-compile` to `poetry` for Python dependency management, addressing [this issue]()

Moreover:
- version majors were pinned for all direct dependencies
- some CI steps were modified to have `tox` installed via `pipx` and to upgrade checkout actions
