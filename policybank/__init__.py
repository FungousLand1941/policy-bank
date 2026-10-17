"""policybank: development-selected routing of public robot policies for BEHAVIOR-1K.

The package has four layers, each usable on its own:

* :mod:`policybank.metrics` and :mod:`policybank.provenance` score and audit evaluator output.
* :mod:`policybank.selection` chooses one policy per task from development rollouts with an
  empirical-Bayes posterior and conservative switching rules.
* :mod:`policybank.routing` freezes, validates and hashes the resulting task-to-policy route.
* :mod:`policybank.serving` serves a routed policy over the challenge websocket protocol with
  fail-stop semantics.
"""

__version__ = "1.0.0"

N_TASKS = 100
REPORT_INSTANCES = tuple(range(301, 311))
DEV_INSTANCES = tuple(range(311, 321))
HIDDEN_INSTANCES = tuple(range(321, 341))
