🎛️ ``pyflp.live``
==================

Controlling a running FL Studio. See :doc:`../guides/live-setup` for the
two-port setup and :doc:`../architecture/live-control` for the wire format.

Client
------

.. automodule:: pyflp.live
   :members: connect, ping, snapshot, Client

Commands
--------

.. automodule:: pyflp.live.commands
   :members: Command

The individual builders (``tempo``, ``mixer_volume_set``, ``play``, ...) are
documented by their :attr:`~pyflp.live.commands.Command` name; run
``flpdiff api`` for FL Studio's own scripting API instead.

Errors and envelopes
--------------------

.. automodule:: pyflp.live.errors
   :members: LiveError, MidiPortNotFound, ProtocolError, ResponseTimeout, exit_code_for

.. automodule:: pyflp.live.envelope
   :members: success, failure, failure_from, ok, result

Protocol and transports
-----------------------

.. automodule:: pyflp.live.protocol
   :members: pack_7bit, unpack_7bit, encode_frame, decode_frame, build_command, parse_response

.. automodule:: pyflp.live.transport
   :members: MemoryReturnPort, ReplayTransport, RecordingTransport, available_ports, resolve_port, load_trace

Device side
-----------

.. automodule:: pyflp.live.device
   :members: install, device_script_path, fl_studio_settings_dir, read_piano_roll_export, write_piano_roll_queue

Scripting API catalogue
-----------------------

.. automodule:: pyflp.live.api
   :members: modules, functions, function_names, signature, signatures, search, describe

Command line
------------

.. automodule:: pyflp.live.cli
   :members: main
