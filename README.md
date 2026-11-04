# PyFLP

PyFLP is an unofficial parser for [FL Studio](https://www.image-line.com/fl-studio/)
project and preset files written in Python.

<!-- SHIELDS -->
<!-- markdownlint-disable -->
<table>
  <colgroup>
    <col style="width: 10%;"/>
    <col style="width: 90%;"/>
  </colgroup>
  <tbody>
    <tr>
      <th>CI</th>
      <td>
        <a href="https://pyflp.readthedocs.io/en/latest/">
          <img alt="Documentation Build Status" src="https://img.shields.io/readthedocs/pyflp/latest?logo=read-the-docs"/>
        </a>
        <a href="https://results.pre-commit.ci/latest/github/demberto/PyFLP/master">
          <img alt="pre-commit-ci" src="https://results.pre-commit.ci/badge/github/demberto/PyFLP/master.svg"/>
        </a>
      </td>
    </tr>
    <tr>
      <th>PyPI</th>
      <td>
        <a href="https://pypi.org/project/PyFLP">
          <img alt="PyPI - Package Version" src="https://img.shields.io/pypi/v/PyFLP"/>
        </a>
        <a href="https://pypi.org/project/PyFLP">
          <img alt="PyPI - Supported Python Versions" src="https://img.shields.io/pypi/pyversions/PyFLP?logo=python&amp;logoColor=white"/>
        </a>
        <a href="https://pypi.org/project/PyFLP">
          <img alt="PyPI - Supported Implementations" src="https://img.shields.io/pypi/implementation/PyFLP"/>
        </a>
        <a href="https://pypi.org/project/PyFLP">
          <img alt="PyPI - Wheel" src="https://img.shields.io/pypi/wheel/PyFLP"/>
        </a>
      </td>
    </tr>
    <tr>
      <th>Activity</th>
      <td>
        <img alt="Maintenance" src="https://img.shields.io/maintenance/yes/2023"/>
        <a href="https://pypistats.org/packages/pyflp">
          <img alt="PyPI - Downloads" src="https://img.shields.io/pypi/dm/PyFLP"/>
        </a>
      </td>
    </tr>
    <tr>
      <th>QA</th>
      <td>
        <a href="https://codecov.io/gh/demberto/PyFLP">
          <img alt="codecov" src="https://codecov.io/gh/demberto/PyFLP/branch/master/graph/badge.svg?token=RGSRMMF8PF"/>
        </a>
        <a href="https://codefactor.io/repository/github/demberto/PyFLP">
          <img alt="CodeFactor Grade" src="https://img.shields.io/codefactor/grade/github/demberto/PyFLP?logo=codefactor"/>
        </a>
        <a href="http://mypy-lang.org/">
          <img alt="Checked with mypy" src="http://www.mypy-lang.org/static/mypy_badge.svg">
        </a>
        <a href="https://github.com/pre-commit/pre-commit">
          <img alt="pre-commit" src="https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&amp;logoColor=white"/>
        </a>
        <a href="https://github.com/PyCQA/bandit">
          <img alt="Security Status" src="https://img.shields.io/badge/security-bandit-yellow.svg"/>
        </a>
      </td>
    </tr>
    <tr>
      <th>Other</th>
      <td>
        <a href="https://github.com/demberto/PyFLP/blob/master/LICENSE">
          <img alt="License" src="https://img.shields.io/github/license/demberto/PyFLP"/>
        </a>
        <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/demberto/PyFLP"/>
        <a href="https://github.com/psf/black">
          <img alt="Code Style: Black" src="https://img.shields.io/badge/code%20style-black-black"/>
        </a>
        <a href="https://github.com/demberto/PyFLP/blob/master/CODE_OF_CONDUCT.md">
          <img alt="covenant" src="https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg"/>
        </a>
      </td>
    </tr>
  </tbody>
</table>
<!-- markdownlint-restore -->

From a very general point-of-view, this is the state of what is currently
implemented. Click on a link to go to the documentation for that feature.

<!-- FEATURE TABLE -->
<!-- markdownlint-disable -->
<table>
  <tr>
    <th>Group</th>
    <th>Feature</th>
    <th>Issues</th>
  </tr>
  <tr>
    <td rowspan="3">
      <a href="https://pyflp.readthedocs.io/en/latest/reference/arrangements.html">Arrangements</a><br/>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Aarrangement-general">
        <img alt="open arrangement-general issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/arrangement-general?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Aarrangement-general">
        <img alt="closed arrangement-general issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/arrangement-general?label=closed&style=flat-square"/>
      </a>
    </td>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/arrangements.html#playlist">🎼 Playlist</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Aarrangement-playlist">
        <img alt="open arrangement-playlist issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/arrangement-playlist?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Aarrangement-playlist">
        <img alt="closed arrangement-playlist issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/arrangement-playlist?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr></tr> <!-- only for formatting --->
  <tr>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/arrangements.html#track">🎞️ Tracks</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Aarrangement-track">
        <img alt="open arrangement-track issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/arrangement-track?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Aarrangement-track">
        <img alt="closed arrangement-track issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/arrangement-track?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td rowspan="4">
      <a href="https://pyflp.readthedocs.io/en/latest/reference/channels.html">Channel Rack</a><br/>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Achannel-general">
        <img alt="open channel-general issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/channel-general?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Achannel-general">
        <img alt="closed channel-general issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/channel-general?label=closed&style=flat-square"/>
      </a>
    </td>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/channels.html#pyflp.channel.Automation">📈 Automations</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%channel-automation">
        <img alt="open channel-automation issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/channel-automation?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Achannel-automation">
        <img alt="closed channel-automation issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/channel-automation?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/channels.html#pyflp.channel.Instrument">🎹 Instruments</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Achannel-instrument">
        <img alt="channel-instrument issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/channel-instrument?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Achannel-instrument">
        <img alt="closed channel-instrument issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/channel-instrument?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/channels.html#pyflp.channel.Layer">📚 Layer</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Achannel-layer">
        <img alt="open channel-layer issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/channel-layer?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Achannel-layer">
        <img alt="closed channel-layer issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/channel-layer?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/channels.html#pyflp.channel.Sampler">📁 Sampler</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Achannel-sampler">
        <img alt="open channel-sampler issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/channel-sampler?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Achannel-sampler">
        <img alt="closed channel-sampler issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/channel-sampler?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td rowspan="2">
      <a href="https://pyflp.readthedocs.io/en/latest/reference/mixer.html">Mixer</a><br/>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Amixer-general">
        <img alt="open mixer-general issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/mixer-general?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Amixer-general">
        <img alt="closed mixer-general issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/mixer-general?label=closed&style=flat-square"/>
      </a>
    </td>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/mixer.html#pyflp.mixer.Insert">🎚️ Inserts</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Amixer-insert">
        <img alt="open mixer-insert issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/mixer-insert?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Amixer-insert">
        <img alt="closed mixer-insert issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/mixer-insert?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
    <tr>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/mixer.html#pyflp.mixer.Slot">🎰 Effect slots</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Amixer-slot">
        <img alt="open mixer-slot issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/mixer-slot?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Amixer-slot">
        <img alt="closed mixer-slot issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/mixer-slot?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td rowspan="3">
      <a href="https://pyflp.readthedocs.io/en/latest/reference/patterns.html">🎶 Patterns</a><br/>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Apattern-general">
        <img alt="open pattern-general issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/pattern-general?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Apattern-general">
        <img alt="closed pattern-general issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/pattern-general?label=closed&style=flat-square"/>
      </a>
    </td>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/patterns.html#pyflp.pattern.Controller">🎛 Controllers</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Apattern-controller">
        <img alt="open pattern-controller issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/pattern-controller?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Apattern-controller">
        <img alt="closed pattern-controller issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/pattern-controller?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
    <tr>
    <td><a href="https://pyflp.readthedocs.io/en/latest/reference/patterns.html#pyflp.pattern.Note">🎵 Notes</a></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Apattern-note">
        <img alt="open pattern-note issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/pattern-note?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Apattern-note">
        <img alt="closed pattern-note issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/pattern-note?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr></tr> <!-- for formatting --->
  <tr>
    <td>
      <a href="https://pyflp.readthedocs.io/en/latest/reference/timemarkers.html">🚩 Timemarkers</a>
    </td>
    <td></td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Atimemarker">
        <img alt="open timemarker issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/timemarker?label=open&style=flat-square"/>
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Atimemarker">
        <img alt="closed timemarker issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/timemarker?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td rowspan="2">
      <a href="https://pyflp.readthedocs.io/en/latest/reference/plugins.html">Plugins</a>
    </td>
    <td>
      Native -
      8 <a href="https://pyflp.readthedocs.io/en/latest/reference/plugins.html#effects">effects</a>,
      1 <a href="https://pyflp.readthedocs.io/en/latest/reference/plugins.html#generators">synth</a>
    </td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Aplugin-native">
        <img alt="open plugin-native issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/plugin-native?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Aplugin-native">
        <img alt="closed plugin-native issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/plugin-native?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td>
      <a href="https://pyflp.readthedocs.io/en/latest/reference/plugins.html#pyflp.plugin.VSTPlugin">VST 2/3</a>
    </td>
    <td>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Aplugin-3rdparty">
        <img alt="plugin-3rdparty issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/plugin-3rdparty?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Aplugin-3rdparty">
        <img alt="closed plugin-3rdparty issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/plugin-3rdparty?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
  <tr>
    <td rowspan="2" colspan="2">
      <a href="https://pyflp.readthedocs.io/en/latest/reference/project.html">Project</a>
      - Settings and song metadata
    </td>
    <td colspan="2">
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aopen+is%3Aissue+label%3Aproject-general">
        <img alt="open project-general issues" src="https://img.shields.io/github/issues-raw/demberto/PyFLP/project-general?label=open&style=flat-square">
      </a>
      <a href="https://github.com/demberto/PyFLP/issues?q=is%3Aclosed+is%3Aissue+label%3Aproject-general">
        <img alt="closed project-general issues" src="https://img.shields.io/github/issues-closed-raw/demberto/PyFLP/project-general?label=closed&style=flat-square"/>
      </a>
    </td>
  </tr>
</table>
<!-- markdownlint-restore -->

## ⏬ Installation

CPython 3.8+ / PyPy 3.8+ required.

```none
python -m pip install -U pyflp
```

To control a *running* FL Studio over virtual MIDI ports, install the `live`
extra as well (it pulls in [`mido`](https://mido.readthedocs.io/)):

```none
python -m pip install -U "pyflp[live]"
```

## ▶ Usage

[Load](https://pyflp.readthedocs.io/en/latest/reference.html#pyflp.parse) a project file:

```py
import pyflp
project = pyflp.parse("/path/to/parse.flp")
```

> On Windows, use a raw string for paths, e.g. `pyflp.parse(r"C:\Users\me\song.flp")`,
> otherwise Python fails with a `unicodeescape` `SyntaxError`.

> If you get any sort of errors or warnings while doing this, please open an
> [issue](https://github.com/demberto/PyFLP/issues).

[Save](https://pyflp.readthedocs.io/en/latest/reference.html#pyflp.save) the project:

```py
pyflp.save(project, "/path/to/save.flp")
```

> It is advised to do a backup of your projects before doing any changes.
> It is also recommended to open the modified project in FL Studio to ensure
> that it works as intended.

Check the [reference](https://pyflp.rtfd.io/en/latest/reference.html) for a
complete list of useable features.

## 🎛 Controlling a running FL Studio

`pyflp.live` is the other half of PyFLP: instead of editing a `.flp` file it
talks to FL Studio while it is open, over two virtual MIDI ports. Use it for
what only FL Studio can do - creating patterns, selecting channels, moving the
playhead, driving plugins - and the file API for everything a file is better
at.

```py
from pyflp.live import Client

with Client.connect() as fl:
    fl.tempo(174.0)
    fl.mixer_volume_set(1, 0.75)
    fl.new_pattern("Chorus")
    fl.play()
    state = fl.snapshot()
```

Every method returns the device's result or raises
`pyflp.live.errors.LiveError` with a stable code (`NOT_FOUND`, `TIMEOUT`,
`PORT_NOT_FOUND`, ...), and `Client.send()` hands back the raw JSON envelope.
`Client.batch()` runs a list of steps in one session.

### One-time setup

```console
$ pyflp-live device-install     # copies the device script into FL Studio's settings
$ pyflp-live ports              # lists the MIDI ports pyflp can see
$ pyflp-live ping               # proves FL Studio answers
{"ok": true, "command": "ping", "args": {}, "result": {"ok": true, "latency_ms": 3.9, "tempo": 120.0}, "error": null}
```

1. Create two virtual MIDI ports named `PyFLP` and `PyFLP-rx` (loopMIDI on
   Windows, the IAC driver on macOS).
2. Run `pyflp-live device-install` (or
   `pyflp.live.device.install()`), which writes `fl_device.py` and the piano
   roll helper scripts into FL Studio's `Settings` folder.
3. In FL Studio: *Options > MIDI Settings*, enable `PyFLP` as an **input** and
   set its controller type to `PyFLP`; enable `PyFLP-rx` as an **output** with
   the same port number. Restart FL Studio.

`pyflp-live doctor` checks every step of the above. Ports are matched by
case-insensitive substring and can be overridden with `--port` /
`--return-port`, `Client.connect(port=..., return_port=...)` or the
`PYFLP_LIVE_PORT` / `PYFLP_LIVE_RETURN_PORT` environment variables.

### Command line

Every `pyflp-live` command prints one JSON envelope, so the output pipes into
anything:

```console
$ pyflp-live tempo 174
$ pyflp-live state --field mixer.tracks.1.volume
$ pyflp-live snapshot --out before.json
$ pyflp-live send mixer_volume_set --args '{"track": 1, "value": 0.75}'
$ pyflp-live batch --continue-on-error song.jsonl
$ pyflp-live api mixer --search TrackVolume
```

Exit codes follow the error codes (`0` success, `2` bad arguments, `3` not
found, `10` port missing, `12` timeout, ...).

> The live side needs FL Studio's own audio engine; it can't run headless, and
> it only reaches what FL Studio's scripting API exposes. Anything the API
> doesn't have - playlist clip placement, creating a pattern from scratch,
> loading samples - is available offline through `pyflp.tools.edit`.

## 🧰 Tools: `flpdiff`

PyFLP installs an `flpdiff` command (also `python -m pyflp`), a port of
[flpdiff](https://github.com/dawhubapp/flpdiff):

```console
$ flpdiff v1.flp v2.flp
FLP Diff: v1.flp vs v2.flp
──────────────────────────
Summary: 4 changes (1 metadata, 1 patterns, 1 mixer, 1 arrangements, 1 tracks, 2 notes)

Metadata:
  ~ Tempo decreased from 174.0 to 172.0 BPM

Patterns:
  ~ Pattern 'Bass #1' modified (2 changes)
      - Removed G#3 on channel 9 at beat 0
      + Added A#3 on channel 9 at beat 0

Mixer:
  ~ Insert 13 (Bass) modified (1 changes)
      ~ Fruity Parametric EQ 2 in slot 3: frequencies[0] 19661 → 45875

Arrangements:
  ~ Arrangement 'Arrangement' modified (0 arrangement changes, 1 track changes)
      ~ Track 'Bass' modified (14 changes)
          ~ 14 clips of pattern 'Bass #1' moved 1/2 beat later (beats 4→4.5 … 60→60.5)
```

- `flpdiff A.flp B.flp [--format json] [--verbose] [--plugin-state]` - semantic
  diff; exits with 0 if identical, 1 if different, 2 on errors.
- `flpdiff info song.flp [--format text|json|canonical]` - inspect a project.
- `flpdiff snapshot song.flp [--out state.json]` - write a JSON state snapshot.
- `flpdiff assert song.flp --checks checks.json` - verify expectations against
  a project *or* a snapshot; exits with 1 when an assertion fails.
- `flpdiff reorganize in.flp out.flp [--dry-run]` - sort playlist clips into
  tracks grouped by instrument family, with automation clips nested under the
  track they control.
- `flpdiff git-setup [--global] [--textconv] [--lfs]` and `flpdiff git-verify` -
  make `git diff`, `git log -p`, etc. show `*.flp` changes semantically.
- `flpdiff midi riff.mid [--track N] [--ppq N]` - read a Standard MIDI File,
  optionally as note specs ready for `pyflp.tools.edit`.
- `flpdiff api [MODULE] [--search TEXT]` - FL Studio's own scripting API
  (422 functions across 14 modules), as data.
- `flpdiff bridge` - JSON lines in / out, for other programs like MCP servers.

The same features are available as Python APIs in `pyflp.tools`; offline
editing operations (notes, patterns, playlist clips, mixer, channels,
plugins) are in `pyflp.tools.edit`:

```py
from pyflp.tools import edit

project = pyflp.parse("song.flp")
edit.set_tempo(project, 174)
bass = edit.create_pattern(project, "Bass", [{"key": "C3", "position": 0, "length": 192}])
edit.arrange_song(project, [{"bars": 8, "patterns": ["Drums", bass]}])
pyflp.save(project, "song (edited).flp")
```

### Finding things, comparing state, moving notes

Three smaller modules cover the bookkeeping around editing:

```py
from pyflp.tools import edit, midi, refs, snapshot

# Address a channel, pattern or insert by index, exact name or substring;
# an ambiguous match is an error instead of a coin flip.
kick = refs.resolve_channel(project, refs.channel_ref(query="kick"))

# Read a MIDI file and drop it into a pattern (times converted to ticks).
notes = midi.read_notes("riff.mid")
edit.add_notes(project, 1, midi.to_note_specs(notes, project.ppq))

# Move / stretch / poke individual notes.
edit.shift_notes(project, 1, project.ppq)      # one beat later
edit.stretch_notes(project, 1, 0.5)            # staccato
edit.update_note(project, 1, 0, velocity=120)  # the first note

# Snapshots are plain dicts: diff them, and assert what changed.
before = snapshot.snapshot_from_project(project)
...
after = snapshot.snapshot_from_project(pyflp.parse("edited.flp"))
print(snapshot.render_diff(snapshot.diff_snapshots(before, after)))
snapshot.assert_snapshot(after, [{"path": "tempo", "op": "eq", "value": 174.0}])
```

The assertion operators are `eq`, `ne`, `gt`, `gte`, `lt`, `lte` and
`contains`, and the same dictionaries work on a live snapshot, so a script can
assert that FL Studio did what it was told:

```py
from pyflp.live import Client
from pyflp.tools import snapshot

with Client.connect() as fl:
    fl.tempo(174.0)
    snapshot.assert_snapshot(fl.snapshot(throttle=False),
                             [{"path": "tempo", "op": "eq", "value": 174.0}])
```

## 🙏 Acknowledgements

- Monad.FLParser: <https://github.com/monadgroup/FLParser>
- flpdiff: <https://github.com/dawhubapp/flpdiff> (MIT), the basis of `pyflp.tools`
  and the source of the FL Studio 2025 test fixtures
- flcli: <https://github.com/s4k10503/flcli> (MIT), the basis of `pyflp.live`,
  `pyflp.tools.refs`, `pyflp.tools.snapshot` and `pyflp.tools.midi`, and the
  source of the bundled FL Studio device script
- delorenj/skills: <https://github.com/delorenj/skills> (`flstudio-scripting`),
  the source of the FL Studio scripting API catalogue in `pyflp.live.api`
- FLPEdit (repo deleted by [author](https://github.com/roadcrewworker))

## ✨ Contributors

<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
![All Contributors](https://img.shields.io/badge/all_contributors-3-orange.svg?style=flat-square)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

Thanks goes to these wonderful people:

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center"><a href="https://github.com/nickberry17"><img src="https://avatars.githubusercontent.com/u/18670565?v=4?s=50" width="50px;" alt=""/><br /><sub><b>nickberry17</b></sub></a><br /><a href="https://github.com/demberto/PyFLP/commits?author=nickberry17" title="Code">💻</a></td>
      <td align="center"><a href="https://github.com/zacanger"><img src="https://avatars.githubusercontent.com/u/12520493?v=4?s=50" width="50px;" alt=""/><br /><sub><b>zacanger</b></sub></a><br /><a href="https://github.com/demberto/PyFLP/issues?q=author%3Azacanger" title="Bug reports">🐛</a> <a href="https://github.com/demberto/PyFLP/commits?author=zacanger" title="Documentation">📖</a></td>
      <td align="center"><a href="https://github.com/ttaschke"><img src="https://avatars.githubusercontent.com/u/7067750?v=4?s=50" width="50px;" alt=""/><br /><sub><b>Tim</b></sub></a><br /><a href="https://github.com/demberto/PyFLP/commits?author=ttaschke" title="Documentation">📖</a> <a href="https://github.com/demberto/PyFLP/commits?author=ttaschke" title="Code">💻</a> <a href="#maintenance-ttaschke" title="Maintenance">🚧</a></td>
    </tr>
  </tbody>
</table>
<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://allcontributors.org/) specification.
Contributions of any kind are welcome!

Please see the [contributor's guide](https://pyflp.rtfd.io/en/latest/contributing.html)
for more information about contributing.

## 📧 Contact

You can contact me either via [issues](https://github.com/demberto/PyFLP/issues)
and [discussions](https://github.com/demberto/PyFLP/discussions) or through
email via ``demberto(at)proton(dot)me``.

## © License

The code in this project has been licensed under the
[GNU Public License v3](https://www.gnu.org/licenses/gpl-3.0.en.html).
