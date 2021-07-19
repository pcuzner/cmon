# Hacking on cmon

## tox
tox is setup to run mypy and flake8 checkers against the package

**TODO**: automate the testing so the tests can validate the codebase more easily

## Adding a new Panel

Add a function to the cmon/ceph module which returns a list of dicts
- test the function in the tests/test_ceph_funcs.py

Add a panel to the cmon/ui/panels module

Update the cmon/app module to include the new module
 - creating and instance of the new class
 - add a key to turn the panel on and off
 - add the new instance to self.body to add it to the UI

Update the cmon/ui/help class to describe your new panel

Update the cmon/config module to include the new module and set it's defaults

Update the main cmon script to include the new option to turn the new panel on at invocation time