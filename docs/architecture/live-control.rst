🔌 The live wire protocol
=========================

:mod:`pyflp.live` sends commands to FL Studio as MIDI system exclusive
messages and receives one answer per command. This page describes the bytes,
so a different client (or a different device script) can interoperate.

Frame layout
------------

Every frame is a single SysEx message:

.. code::

    F0 7D 02 <rid0> <rid1> <rid2> <rid3> <packed payload...> F7

``F0`` / ``F7``
    SysEx start and end. FL Studio sometimes delivers ``event.sysex`` without
    them, so the device side re-adds them if they're missing.

``7D``
    The non-commercial / educational manufacturer ID.

``02``
    Protocol version. The device rejects any other value with a
    ``ProtocolMismatch``, so an old client can't corrupt a session.

``rid0..3``
    A 28 bit request id, most significant bit first, each byte ``<= 0x7F``.
    The response repeats it, which is how a reply is matched to its request.

``packed payload``
    UTF-8 JSON encoded 8 bits to 7 bits (below), so no byte of the payload has
    its high bit set and the frame survives any MIDI transport.

7 bit packing
-------------

Every seven source bytes become one "most significant bits" byte followed by
the seven payload bytes with their high bit cleared:

.. code:: py

    >>> from pyflp.live.protocol import pack_7bit, unpack_7bit
    >>> pack_7bit(b"\xff")
    b'\x01\x7f'
    >>> unpack_7bit(b'\x01\x7f')
    b'\xff'

Messages
--------

A request is a JSON object with a command name and its arguments:

.. code:: json

    {"cmd": "tempo", "args": {"bpm": 140.5}}

A response repeats the request id and reports success or a stable error code:

.. code:: json

    {"request_id": 42, "ok": true, "command": "tempo",
     "result": {"bpm": 140.5}, "error": null}

.. code:: json

    {"request_id": 43, "ok": false, "command": "mixer_volume_set",
     "result": null,
     "error": {"code": "INVALID_ARGUMENT", "message": "missing argument: value"}}

The error codes - ``INVALID_ARGUMENT``, ``NOT_FOUND``, ``TIMEOUT``,
``PORT_NOT_FOUND``, ``UNKNOWN_COMMAND``, ``PROTOCOL_ERROR``,
``AUTOMATION_FAILED``, ``IO_ERROR`` and ``INTERNAL`` - are listed in
:mod:`pyflp.live.errors`, together with the POSIX exit status each maps to so
a shell script can branch without parsing JSON.

Two implementations
-------------------

FL Studio's embedded interpreter can't import PyFLP, so the protocol helpers
exist twice: in :mod:`pyflp.live.protocol` (typed, exceptions) and inside
:data:`pyflp.live.device.DEVICE_SCRIPT` (dependency free, plain ``ValueError``).
``tests/test_live.py`` imports the device script with stubbed FL Studio
modules and compares both byte for byte on a shared set of vectors, so any
drift fails a test rather than a session.

Ports and threading
-------------------

There are two ports because a MIDI output can't receive. The command port
(``PyFLP``) carries requests, the return port (``PyFLP-rx``) carries
responses, and FL Studio's MIDI scripting API only lets a script *send* on the
output it is assigned to.

On the Python side each in-flight request owns a ``threading.Event``; the
``mido`` input callback resolves it and the calling thread waits. Responses
which arrive for an unknown request id are dropped, and closing the port fails
every waiter instead of hanging them.
