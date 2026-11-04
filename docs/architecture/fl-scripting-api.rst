🎛️ FL Studio's scripting API
============================

FL Studio embeds a Python interpreter and exposes its own state to scripts
through plain modules - ``transport``, ``mixer``, ``channels``, ``pattern``,
``playlist`` and nine more. Those modules only exist *inside* FL Studio, so
PyFLP can neither import them nor discover them at runtime.

:mod:`pyflp.live.api` therefore ships the API surface as data: for every
module, the name and parameter list of every function.

.. code:: py

    >>> from pyflp.live import api
    >>> api.signature("mixer.setTrackVolume")
    'index: int, volume: float, pickupMode: int = midi.PIM_None'
    >>> api.describe("transport.getSongPos")
    {'module': 'transport', 'function': 'getSongPos',
     'signature': 'getSongPos(mode: Literal[-1] = -1)', 'call': 'transport.getSongPos(...)'}

The same catalogue is available from the shell:

.. code:: console

    $ flpdiff api                       # every module and its function count
    $ flpdiff api mixer                 # every mixer function signature
    $ flpdiff api --search TrackVolume  # substring search

Coverage
--------

Fourteen modules and 422 functions are catalogued:

* ``ui`` - 71 functions
* ``mixer`` - 69
* ``channels`` - 48
* ``playlist`` - 41
* ``device`` - 34
* ``callbacks`` - 26
* ``patterns`` - 25
* ``general`` - 24
* ``utils`` - 21
* ``transport`` - 20
* ``plugins`` - 13
* ``launchMapPages`` - 12
* ``arrangement`` - 9
* ``screen`` - 9

Every function listed for the ``plugins`` module needs FL Studio 20.8.4 or
newer; an older FL Studio has no ``plugins`` module at all, which is why the
bundled device script guards the import and reports ``NOT_FOUND`` with a
readable message instead of failing to load.

.. note::

   The catalogue is regenerated from its source documents with
   ``python scripts/gen_live_api.py --docs <path>``; the ``--check`` flag
   verifies that the committed module is up to date.

Provenance
----------

Only function names, module names and parameter lists - facts about a public
API - are carried over. The prose descriptions in the source documents are
deliberately not copied.

* Image-Line's published scripting reference:
  https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/midi_scripting.htm
* The ``flstudio-scripting`` reference documents from
  https://github.com/delorenj/skills, which transcribe the ``fl-studio-stubs``
  type stubs.

How this relates to :mod:`pyflp.live`
-------------------------------------

The catalogue describes what a *controller script* can call. PyFLP's own
device script (:mod:`pyflp.live.device`) is such a script, and
:mod:`pyflp.live.commands` mirrors the subset of the API that PyFLP exposes
over SysEx. Use the catalogue when writing a new command - the parameters it
lists are the ones the device script can pass on.
