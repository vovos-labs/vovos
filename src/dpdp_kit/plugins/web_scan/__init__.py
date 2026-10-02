"""web-scan plugin: loads a website once, without interacting, and inspects what happens before consent.

Requires the optional ``web`` extra: ``pip install "dpdp-kit[web]"`` then ``playwright install chromium``
(or pass ``--browser-channel chrome`` to use an installed Chrome).
"""

from . import checks  # noqa: F401
