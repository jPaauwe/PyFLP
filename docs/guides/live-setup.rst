.. _live-setup:

🛰️ Controlling a running FL Studio
==================================

:func:`pyflp.parse` and :func:`pyflp.save` work on ``.flp`` files while FL
Studio is closed; :mod:`pyflp.live` works the other way round - it drives FL
Studio while it is open, over two virtual MIDI ports.

Use the live side for what only FL Studio can do (creating patterns,
selecting channels, moving the playhead, driving plugins) and the offline side
for what a file is better at (editing a pattern which isn't open, placing
playlist clips, rewriting anything at all). Both halves live in the same
package, so a script can switch between them freely.

Setup
-----

1. **Create two virtual MIDI ports.**

   * Windows: `loopMIDI <https://www.tobias-erichsen.de/software/loopmidi.html>`_,
     one port named ``PyFLP`` and one named ``PyFLP-rx``.
   * macOS: Audio MIDI Setup, enable the IAC driver and add two buses with the
     same names.

2. **Install the device files.**

   .. code:: py

      >>> from pyflp.live import device
      >>> report = device.install()
      >>> report["device_script"]["path"]       # doctest: +SKIP

   This copies ``fl_device.py`` into
   ``<Documents>/Image-Line/FL Studio/Settings/Hardware/PyFLP/``, and the
   piano-roll helper scripts into ``Settings/Piano roll scripts``. Pass
   ``piano_roll_scripts=False`` to skip the latter, or a directory as the
   first argument to install somewhere else. ``pyflp-live device-install``
   does the same from the shell.

3. **Tell FL Studio about the ports.** In Options > MIDI Settings: enable
   ``PyFLP`` as an *input*, set its controller type to ``PyFLP`` and give it a
   port number; enable ``PyFLP-rx`` as an *output* with the same port number.
   Restart FL Studio.

4. **Check it works.**

   .. code:: console

      $ pyflp-live ping
      {"ok": true, "command": "ping", "args": {},
       "result": {"ok": true, "latency_ms": 4.1, "tempo": 120.0}, "error": null}

Using it
--------

.. code:: py

    from pyflp.live import Client

    with Client.connect() as fl:
        fl.tempo(174.0)
        fl.mixer_volume_set(1, 0.75)
        fl.new_pattern("Chorus")
        fl.play()
        state = fl.snapshot()

Every method returns the device's result payload or raises
:class:`~pyflp.live.errors.LiveError` with a stable code (``NOT_FOUND``,
``TIMEOUT``, ...). When you want the raw envelope instead, call
:meth:`Client.send <pyflp.live.client.Client.send>`.

Ports are found by case-insensitive substring, defaulting to ``PyFLP`` /
``PyFLP-rx``; override them with ``Client.connect(port="loopMIDI 1",
return_port="loopMIDI 2")`` or ``PYFLP_LIVE_PORT`` / ``PYFLP_LIVE_RETURN_PORT``.

Batching
~~~~~~~~

:meth:`Client.batch <pyflp.live.client.Client.batch>` runs several commands in
one session and reports one envelope per step:

.. code:: py

    steps = [
        {"name": "tempo", "args": {"bpm": 128}},
        {"name": "new_pattern"},
        {"name": "mixer_volume_set", "args": {"track": 1, "value": 0.8}},
        {"name": "play"},
    ]
    for response in fl.batch(steps):
        print(response["ok"], response["command"])

Snapshots and assertions
~~~~~~~~~~~~~~~~~~~~~~~~

A live snapshot is a plain dictionary; :mod:`pyflp.tools.snapshot` compares it
and checks expectations against it, and the same functions accept an offline
snapshot of a saved project:

.. code:: py

    from pyflp.tools import snapshot as S

    before = fl.snapshot()
    fl.tempo(180.0)
    after = fl.snapshot(throttle=False)

    print(S.render_diff(S.diff_snapshots(before, after)))
    S.assert_snapshot(after, [{"path": "tempo", "op": "eq", "value": 180.0}])

Piano roll notes
~~~~~~~~~~~~~~~~

Two commands write notes without the native note bridge:

* ``fl.step_melody(notes)`` expands notes onto the step sequencer - the
  simplest path, quantised to 1/16th steps.
* :func:`pyflp.live.device.write_piano_roll_queue` writes the notes next to
  ``pyflp_import.pyscript``; running *Tools > Scripts > pyflp_import* in FL
  Studio's piano roll inserts them sample accurately.
  :func:`~pyflp.live.device.read_piano_roll_export` reads them back after
  running ``pyflp_export``.

The offline alternative is better when the pattern isn't open:
:func:`pyflp.tools.edit.add_notes` writes straight into the ``.flp``.

Troubleshooting
---------------

``PORT_NOT_FOUND``
    The port name doesn't match. ``pyflp-live ports`` lists what PyFLP can
    see; remember FL Studio must be running to open ``PyFLP-rx``.

``TIMEOUT``
    The port is open but nothing answered: the device script isn't installed,
    isn't selected as the controller type, or FL Studio is showing a modal
    dialog.

``NOT_FOUND`` for anything plugin related
    FL Studio 20.7 and older have no ``plugins`` scripting module; everything
    else still works.

``pyflp-live doctor``
    Runs every check above and prints one entry per check.

What was not carried over from flcli
------------------------------------

:mod:`pyflp.live` is a port of `flcli <https://github.com/s4k10503/flcli>`_,
but four of its shell conveniences have no PyFLP equivalent, on purpose:

* **The TOML config file.** PyFLP takes the ports from
  ``Client.connect(port=..., return_port=...)``, the CLI flags or
  ``PYFLP_LIVE_PORT`` / ``PYFLP_LIVE_RETURN_PORT``, and everything else is an
  explicit argument. A fourth configuration layer would make a bug report
  harder to read, not easier.
* **Shell completion.** `argcomplete <https://kislyuk.github.io/argcomplete/>`_
  handles ``pyflp-live`` and ``flpdiff`` without PyFLP shipping generated
  completion scripts.
* **OS automation.** flcli could fire a keyboard shortcut to run its piano
  roll import script for you (``pynput`` on Windows, ``osascript`` on macOS,
  ``xdotool`` on Linux). Installing a global keyboard hook is more than a
  library should do behind an import, and the offline path
  (:func:`pyflp.tools.edit.add_notes`) doesn't need it.
* **Realtime piano roll recording.** flcli could play notes into FL Studio's
  own MIDI recorder, with everything that implies for timing and for
  accidentally recording into the wrong pattern. The two note paths above plus
  the offline editor cover the same ground deterministically.

