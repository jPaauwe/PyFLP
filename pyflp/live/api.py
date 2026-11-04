# PyFLP - An FL Studio project file (.flp) parser
# Copyright (C) 2022 demberto
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
# Public License for more details. You should have received a copy of the
# GNU General Public License along with this program. If not, see
# <https://www.gnu.org/licenses/>.

"""Catalogue of FL Studio's Python scripting API, for introspection.

FL Studio exposes its scripting API as plain Python modules which only exist
*inside* FL Studio's embedded interpreter, so PyFLP can neither import them
nor discover them at runtime. This module carries the API surface as data:
every module and the name and parameters of every function, so tooling can
answer "what can a controller script call?" without FL Studio running.

    >>> from pyflp.live import api
    >>> len(api.functions())
    422
    >>> api.signature("mixer.setTrackVolume")
    'index: int, volume: float, pickupMode: int = midi.PIM_None'

The parameter text is reproduced verbatim from Image-Line's published
reference (see ``docs/architecture/fl-scripting-api.rst``); the function
names, module names and parameter lists are facts about a public API, while
the prose descriptions are deliberately *not* copied.

.. versionadded:: 2.3.0
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Tuple

__all__ = [
    "API",
    "MODULES",
    "function_names",
    "functions",
    "has_function",
    "module_of",
    "modules",
    "search",
    "signature",
    "signatures",
]

API: Dict[str, Dict[str, str]] = {
    'arrangement': {
        'addAutoTimeMarker': 'time: int, name: str',
        'currentTime': 'snap: int',
        'currentTimeHint': 'mode: int, time: int, setRecPPB: int = 0, isLength: int = 0',
        'getMarkerName': 'index: int',
        'jumpToMarker': 'delta: int, select: bool',
        'liveSelection': 'time: int, stop: bool',
        'liveSelectionStart': '',
        'selectionEnd': '',
        'selectionStart': '',
    },
    'callbacks': {
        'OnChannelPressure': 'msg: FlMidiMsg',
        'OnControlChange': 'msg: FlMidiMsg',
        'OnDeInit': '',
        'OnDirtyChannel': 'index: int',
        'OnDirtyMixerTrack': 'index: int',
        'OnDisplayZone': '',
        'OnDoFullRefresh': '',
        'OnFirstConnect': '',
        'OnIdle': '',
        'OnInit': '',
        'OnKeyPressure': 'msg: FlMidiMsg',
        'OnMidiIn': 'msg: FlMidiMsg',
        'OnMidiMsg': 'msg: FlMidiMsg',
        'OnMidiOutMsg': 'msg: FlMidiMsg',
        'OnNoteOff': 'msg: FlMidiMsg',
        'OnNoteOn': 'msg: FlMidiMsg',
        'OnPitchBend': 'msg: FlMidiMsg',
        'OnProgramChange': 'msg: FlMidiMsg',
        'OnProjectLoad': 'status: Literal[0, 100, 101]',
        'OnRefresh': 'flags: int',
        'OnSendTempMsg': 'message: str, duration: int',
        'OnSysEx': 'msg: FlMidiMsg',
        'OnUpdateBeatIndicator': 'value: Literal[0, 1, 2]',
        'OnUpdateLiveMode': 'lastTrack: int',
        'OnUpdateMeters': '',
        'OnWaitingForInput': '',
    },
    'channels': {
        'channelCount': 'globalCount: bool = False',
        'channelNumber': 'canBeNone: bool = False, offset: int = 0',
        'closeGraphEditor': 'index: int, /',
        'deselectAll': '',
        'focusEditor': 'index: int, useGlobalIndex: bool = False',
        'getActivityLevel': 'index: int, useGlobalIndex: bool = False',
        'getChannelColor': 'index: int, useGlobalIndex: bool = False',
        'getChannelIndex': 'index: int',
        'getChannelMidiInPort': 'index: int, useGlobalIndex: bool = False',
        'getChannelName': 'index: int, useGlobalIndex: bool = False',
        'getChannelPan': 'index: int, useGlobalIndex: bool = False',
        'getChannelPitch': 'index: int, mode: Literal[1, 2], useGlobalIndex: bool = False',
        'getChannelType': 'index: int, useGlobalIndex: bool = False',
        'getChannelVolume': 'index: int, mode: bool = False, useGlobalIndex: bool = False',
        'getCurrentStepParam': 'index: int, step: int, param: int, useGlobalIndex: bool = False',
        'getGridBit': 'index: int, position: int, useGlobalIndex: bool = False',
        'getGridBitWithLoop': 'index: int, position: int, useGlobalIndex: bool = False',
        'getRecEventId': 'index: int, useGlobalIndex: bool = False',
        'getStepParam': 'step: int, param: int, index: int, startPos: int, padsStride: int = 16, useGlobalIndex: bool = False',
        'getTargetFxTrack': 'index: int, useGlobalIndex: bool = False',
        'incEventValue': 'eventId: int, step: int, res: float = 1 / 24',
        'isChannelMuted': 'index: int, useGlobalIndex: bool = False',
        'isChannelSelected': 'index: int, useGlobalIndex: bool = False',
        'isChannelSolo': 'index: int, useGlobalIndex: bool = False',
        'isGraphEditorVisible': '',
        'isGridBitAssigned': 'index: int, useGlobalIndex: bool = False',
        'isHighLighted': '',
        'midiNoteOn': 'indexGlobal: int, note: int, velocity: int, channel: int = -1',
        'muteChannel': 'index: int, value: int = -1, useGlobalIndex: bool = False',
        'processRECEvent': 'eventId: int, value: int, flags: int, /',
        'quickQuantize': 'index: int, startOnly: int = 1, useGlobalIndex: bool = False',
        'selectAll': '',
        'selectChannel': 'index: int, value: int = -1, useGlobalIndex: bool = False',
        'selectOneChannel': 'index: int, useGlobalIndex: bool = False',
        'selectedChannel': 'canBeNone: bool = False, offset: int = 0, indexGlobal: bool = False',
        'setChannelColor': 'index: int, color: int, useGlobalIndex: bool = False',
        'setChannelName': 'index: int, name: str, useGlobalIndex: bool = False',
        'setChannelPan': 'index: int, pan: float, pickupMode: int = midi.PIM_None, useGlobalIndex: bool = False',
        'setChannelPitch': 'index: int, value: float, mode: int = 0, pickupMode: int = midi.PIM_None, useGlobalIndex: bool = False',
        'setChannelVolume': 'index: int, volume: float, pickupMode: int = midi.PIM_None, useGlobalIndex: bool = False',
        'setGridBit': 'index: int, position: int, value: bool, useGlobalIndex: bool = False',
        'setStepParameterByIndex': 'index: int, patNum: int, step: int, param: int, value: int, useGlobalIndex: bool = False',
        'setTargetFxTrack': 'channelIndex: int, mixerIndex: int, useGlobalIndex: bool = False',
        'showCSForm': 'index: int, state: int = 1, useGlobalIndex: bool = False',
        'showEditor': 'index: int, value: int = -1, useGlobalIndex: bool = False',
        'showGraphEditor': 'temporary: bool, param: int, step: int, index: int, useGlobalIndex: bool = True',
        'soloChannel': 'index: int, useGlobalIndex: bool = False',
        'updateGraphEditor': '',
    },
    'device': {
        'baseTrackSelect': 'index: int, step: int',
        'createRefreshThread': '',
        'destroyRefreshThread': '',
        'directFeedback': 'eventData: FlMidiMsg, /',
        'dispatch': 'ctrlIndex: int, message: Literal[0xF0], sysex: bytes',
        'dispatchGetReceiverPortNumber': 'ctrlIndex: int',
        'dispatchReceiverCount': '',
        'findEventID': 'controlId: int, flags: int = 0',
        'forwardMIDICC': 'message: int, mode: int = 1',
        'fullRefresh': '',
        'getDeviceID': '',
        'getIdleElapsed': '',
        'getLinkedChannel': 'eventId: int',
        'getLinkedInfo': 'eventID: int',
        'getLinkedParamName': 'eventID: int',
        'getLinkedValue': 'eventID: int',
        'getLinkedValueString': 'eventID: int',
        'getMasterSync': '',
        'getName': '',
        'getPortNumber': '',
        'hardwareRefreshMixerTrack': 'index: int',
        'isAssigned': '',
        'isDoubleClick': 'index: int',
        'isMidiOutAssigned': '',
        'linkToLastTweaked': 'controlIndex: int, channel: int, global_link: bool = False, eventId: int = midi.REC_None',
        'midiOutMsg': 'message: int',
        'midiOutNewMsg': 'slotIndex: int, message: int',
        'midiOutSysex': 'message: bytes',
        'processMIDICC': 'eventData: FlMidiMsg',
        'repeatMidiEvent': 'eventData: FlMidiMsg, delay: int = 300, rate: int = 300',
        'sendMsgGeneric': 'id: int, message: str, lastMsg: str, offset: int = 0, /',
        'setHasMeters': '',
        'setMasterSync': 'value: bool',
        'stopRepeatMidiEvent': '',
    },
    'general': {
        'clearLog': '',
        'dumpScoreLog': 'time: int, silent: bool = False',
        'getChangedFlag': '',
        'getPrecount': '',
        'getRecPPB': '',
        'getRecPPQ': '',
        'getUndoHistoryCount': '',
        'getUndoHistoryLast': '',
        'getUndoHistoryPos': '',
        'getUndoLevelHint': '',
        'getUseMetronome': '',
        'getVersion': '',
        'processRECEvent': 'eventId: int, value: int, flags: int',
        'restoreUndo': '',
        'restoreUndoLevel': 'level: int',
        'safeToEdit': '',
        'saveUndo': 'undoName: str, flags: int, update: bool = True',
        'setUndoHistoryCount': 'value: int',
        'setUndoHistoryLast': 'index: int, /',
        'setUndoHistoryPos': 'index: int',
        'undo': '',
        'undoDown': '',
        'undoUp': '',
        'undoUpDown': 'value: int',
    },
    'launchMapPages': {
        'checkMapForHiddenItem': '',
        'createOverlayMap': 'offColor: int, onColor: int, width: int, height: int',
        'getMapCount': 'index: int',
        'getMapItemAftertouch': 'index: int, itemIndex: int',
        'getMapItemChannel': 'index: int, itemIndex: int',
        'getMapItemColor': 'index: int, itemIndex: int',
        'init': 'deviceName: str, width: int, height: int',
        'length': '',
        'processMapItem': 'eventData: FlMidiMsg, index: int, itemIndex: int, velocity: int',
        'releaseMapItem': 'eventData: FlMidiMsg, index: int',
        'setMapItemTarget': 'index: int, itemIndex: int, target: int',
        'updateMap': 'index: int',
    },
    'mixer': {
        'afterRoutingChanged': '',
        'armTrack': 'index: int',
        'automateEvent': 'index: int, value: int, flags: int, speed: int = 0, isIncrement: int = 0, res: float = midi.EKRes',
        'deselectAll': '',
        'enableTrack': 'index: int',
        'enableTrackSlots': 'index: int, value: bool = False',
        'focusEditor': 'index: int, plugIndex: int',
        'getActiveEffectIndex': '',
        'getAutoSmoothEventValue': 'index: int, locked: int = 1',
        'getCurrentTempo': 'asInt: Literal[True]',
        'getEqBandCount': '',
        'getEqBandwidth': 'index: int, band: int',
        'getEqFrequency': 'index: int, band: int, mode: int = 0',
        'getEqGain': 'index: int, band: int, mode: int = 0',
        'getEventIDName': 'index: int, shortname: int = 0',
        'getEventIDValueString': 'index: int, value: int',
        'getEventValue': 'index: int, value: int = midi.MaxInt, smoothTarget: int = 1',
        'getLastPeakVol': 'section: int',
        'getRecPPS': '',
        'getRouteSendActive': 'index: int, destIndex: int',
        'getRouteToLevel': 'index: int, destIndex: int',
        'getSlotColor': 'index: int, slot: int',
        'getSongStepPos': '',
        'getSongTickPos': 'mode: Literal[0] = 0',
        'getTrackColor': 'index: int',
        'getTrackDockSide': 'index: int',
        'getTrackInfo': 'mode: int',
        'getTrackName': 'index: int',
        'getTrackPan': 'index: int',
        'getTrackPeaks': 'index: int, mode: int',
        'getTrackPluginId': 'index: int, plugIndex: int',
        'getTrackRecordingFileName': 'index: int',
        'getTrackStereoSep': 'index: int',
        'getTrackVolume': 'index: int, mode: int = 0',
        'isTrackArmed': 'index: int',
        'isTrackAutomationEnabled': 'index: int, plugIndex: int',
        'isTrackEnabled': 'index: int',
        'isTrackMuteLock': 'index: int',
        'isTrackMuted': 'index: int',
        'isTrackPluginValid': 'index: int, plugIndex: int',
        'isTrackRevPolarity': 'index: int',
        'isTrackSelected': 'index: int',
        'isTrackSlotsEnabled': 'index: int',
        'isTrackSolo': 'index: int',
        'isTrackSwapChannels': 'index: int',
        'linkChannelToTrack': 'channel: int, track: int, select: bool = False',
        'linkTrackToChannel': 'mode: int',
        'muteTrack': 'index: int, value: int = -1',
        'remoteFindEventValue': 'index: int, flags: int = 0, /',
        'revTrackPolarity': 'index: int, value: bool = False',
        'selectAll': '',
        'selectTrack': 'index: int',
        'setActiveTrack': 'index: int',
        'setEqBandwidth': 'index: int, band: int, value: float',
        'setEqFrequency': 'index: int, band: int, value: float',
        'setEqGain': 'index: int, band: int, value: float',
        'setRouteTo': 'index: int, destIndex: int, value: bool, updateUI: bool = False',
        'setRouteToLevel': 'index: int, destIndex: int, level: float',
        'setSlotColor': 'index: int, slot: int, color: int',
        'setTrackColor': 'index: int, color: int',
        'setTrackName': 'index: int, name: str',
        'setTrackNumber': 'trackNumber: int, flags: int = 0',
        'setTrackPan': 'index: int, pan: float, pickupMode: int = midi.PIM_None',
        'setTrackStereoSep': 'index: int, pan: float, pickupMode: int = midi.PIM_None',
        'setTrackVolume': 'index: int, volume: float, pickupMode: int = midi.PIM_None',
        'soloTrack': 'index: int, value: int = -1, mode: int = -1',
        'swapTrackChannels': 'index: int, value: bool = False',
        'trackCount': '',
        'trackNumber': '',
    },
    'patterns': {
        'burnLoop': 'index: int, storeUndo: int = 1, updateUi: int = 1',
        'clonePattern': 'index: int | None = None',
        'deselectAll': '',
        'ensureValidNoteRecord': 'index: int, playNow: int = 0, /',
        'findFirstNextEmptyPat': 'flags: int, x: int = -1, y: int = -1',
        'getActivePatternGroup': '',
        'getBlockSetStatus': 'left: int, top: int, right: int, bottom: int',
        'getChannelLoopStyle': 'pattern: int, channel: int, /',
        'getPatternColor': 'index: int',
        'getPatternGroupCount': '',
        'getPatternGroupName': 'index: int, /',
        'getPatternLength': 'index: int',
        'getPatternName': 'index: int',
        'getPatternsInGroup': 'index: int, /',
        'isPatternDefault': 'index: int',
        'isPatternSelected': 'index: int',
        'jumpToPattern': 'index: int',
        'patternCount': '',
        'patternMax': '',
        'patternNumber': '',
        'selectAll': '',
        'selectPattern': 'index: int, value: int = -1, preview: bool = False',
        'setChannelLoop': 'channel: int, loopPoint: int, /',
        'setPatternColor': 'index: int, color: int',
        'setPatternName': 'index: int, name: str',
    },
    'playlist': {
        'deselectAll': '',
        'getDisplayZone': '',
        'getLiveBlockColor': 'index: int, blockNum: int',
        'getLiveBlockStatus': 'index: int, blockNum: int, mode: int = midi.LB_Status_Default',
        'getLiveLoopMode': 'index: int',
        'getLivePosSnap': 'index: int',
        'getLiveStatus': 'index: int, mode: int = midi.LB_Status_Default',
        'getLiveTrigSnap': 'index: int',
        'getLiveTriggerMode': 'index: int',
        'getPerformanceModeState': '',
        'getSongStartTickPos': '',
        'getTrackActivityLevel': 'index: int',
        'getTrackActivityLevelVis': 'index: int',
        'getTrackColor': 'index: int',
        'getTrackName': 'index: int',
        'getVisTimeBar': '',
        'getVisTimeStep': '',
        'getVisTimeTick': '',
        'incLiveLoopMode': 'index: int, value: int',
        'incLivePosSnap': 'index: int, value: int',
        'incLiveTrigMode': 'index: int, value: int',
        'incLiveTrigSnap': 'index: int, value: int',
        'isTrackMuteLock': 'index: int',
        'isTrackMuted': 'index: int',
        'isTrackSelected': 'index: int',
        'isTrackSolo': 'index: int',
        'liveBlockNumToTime': 'index: int',
        'liveDisplayZone': 'left: int, top: int, right: int, bottom: int, duration: int = 0',
        'liveTimeToBlockNum': 'time: int',
        'lockDisplayZone': 'index: int, value: int',
        'muteTrack': 'index: int, value: int = -1',
        'muteTrackLock': 'index: int',
        'refreshLiveClips': '*args',
        'scrollTo': 'a: int, b: int, c: int, d: int',
        'selectAll': '',
        'selectTrack': 'index: int',
        'setTrackColor': 'index: int, color: int',
        'setTrackName': 'index: int, name: str',
        'soloTrack': 'index: int, value: int = -1, inGroup: bool = False',
        'trackCount': '',
        'triggerLiveClip': 'index: int, subNum: int, flags: int, velocity: int = -1',
    },
    'plugins': {
        'getColor': 'index: int, slotIndex: int = -1, flag: int = midi.GC_BackgroundColor, useGlobalIndex: bool = False',
        'getName': 'index: int, slotIndex: int = -1, flag: int = midi.FPN_Param, paramIndex: int = 0, useGlobalIndex: bool = False',
        'getPadInfo': 'chanIndex: int, slotIndex: int = -1, paramOption: int = 0, paramIndex: int = -1, useGlobalIndex: bool = False',
        'getParamCount': 'index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'getParamName': 'paramIndex: int, index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'getParamValue': 'paramIndex: int, index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'getParamValueString': 'paramIndex: int, index: int, slotIndex: int = -1, pickupMode: int = midi.PIM_None, useGlobalIndex: bool = False',
        'getPluginName': 'index: int, slotIndex: int = -1, userName: bool = False, useGlobalIndex: bool = False',
        'getPresetCount': 'index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'isValid': 'index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'nextPreset': 'index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'prevPreset': 'index: int, slotIndex: int = -1, useGlobalIndex: bool = False',
        'setParamValue': 'value: float, paramIndex: int, index: int, slotIndex: int = -1, pickupMode: int = 0, useGlobalIndex: bool = False',
    },
    'screen': {
        'addMeter': '*args',
        'animateText': '*args',
        'deInit': '',
        'displayText': 'font: int, justification: int, text_row: int, text: str, check_if_same: bool, display_time: int',
        'displayTimedText': 'text: str, text_row: int',
        'drawRect': '*args',
        'init': 'display_width: int, display_height: int, text_row_height: int, font_size: int, value_a: int, value_b: int, /',
        'setup': 'sysex_header: int, screen_active_timeout: int, screen_auto_timeout: int, text_scroll_pause: int, text_scroll_speed: int, text_display_time: int, /',
        'update': '',
    },
    'transport': {
        'continuousMove': 'speed: int, startStop: int',
        'continuousMovePos': 'speed: int, startStop: int',
        'fastForward': 'startStop: int, flags: int = midi.GT_All',
        'getHWBeatLEDState': '',
        'getLoopMode': '',
        'getSongLength': 'mode: int',
        'getSongPos': 'mode: Literal[-1] = -1',
        'getSongPosHint': '',
        'globalTransport': 'command: int, value: int, pmeflags: int = midi.PME_System, flags=midi.GT_All',
        'isPlaying': '',
        'isRecording': '',
        'markerJumpJog': 'value: int, flags: int = midi.GT_All',
        'markerSelJog': 'value: int, flags: int = midi.GT_All',
        'record': '',
        'rewind': 'startStop: int, flags: int = midi.GT_All',
        'setLoopMode': '',
        'setPlaybackSpeed': 'speedMultiplier: float',
        'setSongPos': 'position: float, mode: Literal[-1] = -1',
        'start': '',
        'stop': '',
    },
    'ui': {
        'closeActivePopupMenu': '',
        'closeAllMenu': '',
        'copy': '',
        'crDisplayRect': 'left: int, top: int, right: int, bottom: int, duration: int, flags: int = 0',
        'cut': '',
        'delete': '',
        'down': 'value: int = 1',
        'enter': '',
        'escape': '',
        'getFocused': 'index: int',
        'getFocusedFormCaption': '',
        'getFocusedFormID': '',
        'getFocusedNodeCaption': '',
        'getFocusedNodeFileType': '',
        'getFocusedPluginName': '',
        'getHintMsg': '',
        'getHintValue': 'value: int, max: int',
        'getProgTitle': '',
        'getSnapMode': '',
        'getStepEditMode': '',
        'getTimeDispMin': '',
        'getVersion': 'mode: Literal[0, 1, 2, 3]',
        'getVisible': 'index: int',
        'hideWindow': 'index: int',
        'horZoom': 'value: int',
        'insert': '',
        'isBrowserAutoHide': '',
        'isClosing': '',
        'isInPopupMenu': '',
        'isLoopRecEnabled': '',
        'isMetronomeEnabled': '',
        'isPrecountEnabled': '',
        'isStartOnInputEnabled': '',
        'jog': 'value: int',
        'jog2': 'value: int',
        'launchAudioEditor': 'reuse: int, filename: str, index: int, preset: str, presetGUID: str',
        'left': 'value: int = 1',
        'miDisplayDockRect': 'start: int, length: int, dock_side: int, time: int',
        'miDisplayRect': 'start: int, end: int, duration: int, flags: int = 0',
        'moveJog': 'value: int',
        'navigateBrowser': 'direction: int, shiftHeld: bool',
        'navigateBrowserMenu': 'direction: int, shiftHeld: bool',
        'navigateBrowserTabs': 'direction: int',
        'next': '',
        'nextWindow': '',
        'no': '',
        'openEventEditor': 'eventId: int, mode: int, newWindow: bool = False',
        'paste': '',
        'previewBrowserMenuItem': '',
        'previous': '',
        'right': 'value: int = 1',
        'scrollWindow': 'index: int, value: int, directionFlag: int = 0',
        'selectBrowserMenuItem': '',
        'selectWindow': 'shift: bool',
        'setBrowserAutoHide': 'value: bool',
        'setFocused': 'index: int',
        'setHintMsg': 'msg: str',
        'setSnapMode': 'value: int',
        'setStepEditMode': 'newValue: bool',
        'setTimeDispMin': '',
        'showNotification': 'notificationId: int',
        'showWindow': 'index: int',
        'snapMode': 'value: int',
        'snapOnOff': '',
        'strip': 'value: int',
        'stripHold': 'value: int',
        'stripJog': 'value: int',
        'toggleBrowserNode': 'value: int = -1',
        'up': 'value: int = 1',
        'verZoom': 'value: int',
        'yes': '',
    },
    'utils': {
        'ColorToRGB': 'Color: int',
        'DivModU': 'A: int, B: int',
        'FadeColor': 'StartColor: int, EndColor: int, Value: float',
        'GetNoteName': 'NoteNum: int',
        'HSVtoRGB': 'H: float, S: float, V: float',
        'InterNoSwap': 'X, A, B',
        'KnobAccelToRes2': 'Value',
        'LightenColor': 'Color: int, Value: float',
        'Limited': 'Value: float, Min: float, Max: float',
        'OffsetRect': 'R: TRect, dx: int, dy: int',
        'RGBToColor': 'R: int, G: int, B: int',
        'RGBToHSV': 'R: float, G: float, B: float',
        'RGBToHSVColor': 'Color: int',
        'RectOverlap': 'R1: TRect, R2: TRect',
        'RectOverlapEqual': 'R1: TRect, R2: TRect',
        'Sign': "value: 'float | int'",
        'SignOf': "value: 'float | int'",
        'SwapInt': 'A, B',
        'VolTodB': 'Value: float',
        'Zeros': "value, nChars, c='0'",
        'Zeros_Strict': "value, nChars, c='0'",
    },
}

MODULES: Tuple[str, ...] = tuple(sorted(API))
"""Every scripting module FL Studio exposes."""


def modules() -> Tuple[str, ...]:
    """Returns the names of every scripting module."""
    return MODULES


def functions(module: Optional[str] = None) -> Dict[str, str]:
    """Returns ``{qualified name: parameter text}``.

    Args:
        module: Limit the result to one module.
    """
    if module is not None:
        if module not in API:
            raise KeyError(module)
        return {f"{module}.{name}": params for name, params in API[module].items()}
    out: Dict[str, str] = {}
    for name, entries in API.items():
        for function, params in entries.items():
            out[f"{name}.{function}"] = params
    return out


def function_names(module: Optional[str] = None) -> Dict[str, List[str]]:
    """Returns ``{module: [function, ...]}``, with sorted function names."""
    if module is not None:
        if module not in API:
            raise KeyError(module)
        return {module: sorted(API[module])}
    return {name: sorted(entries) for name, entries in API.items()}


def has_function(dotted: str) -> bool:
    """Whether ``"module.function"`` exists in the catalogue."""
    try:
        module_of(dotted)
    except KeyError:
        return False
    return True


def module_of(dotted: str) -> Tuple[str, str]:
    """Splits ``"module.function"``, validating both halves.

    Raises:
        KeyError: The module or the function isn't in the catalogue.
    """
    module, _, function = dotted.partition(".")
    if not function:
        raise KeyError(f"{dotted!r} isn't 'module.function'")
    if module not in API:
        raise KeyError(f"unknown FL Studio scripting module {module!r}")
    if function not in API[module]:
        raise KeyError(f"{module!r} has no function {function!r}")
    return module, function


def signature(dotted: str) -> str:
    """Returns the parameter text of one function, e.g. ``"index: int"``."""
    module, function = module_of(dotted)
    return API[module][function]


def signatures(module: Optional[str] = None) -> Dict[str, str]:
    """Returns ``{qualified name: "name(params)"}`` for one or every module."""
    out: Dict[str, str] = {}
    for dotted, params in functions(module).items():
        out[dotted] = f"{dotted.split('.', 1)[1]}({params})"
    return out


def search(pattern: str, module: Optional[str] = None) -> Dict[str, str]:
    """Case insensitive substring search over function names.

    Returns ``{qualified name: parameter text}`` of every match.
    """
    needle = pattern.casefold()
    return {
        dotted: params
        for dotted, params in functions(module).items()
        if needle in dotted.casefold()
    }


def describe(dotted: str) -> Mapping[str, str]:
    """Returns a small report about one function."""
    module, function = module_of(dotted)
    return {
        "module": module,
        "function": function,
        "signature": f"{function}({API[module][function]})",
        "call": f"{module}.{function}(...)",
    }
