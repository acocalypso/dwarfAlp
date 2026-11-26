# Generates dwarfAlp-test-plan-3.json, a N.I.N.A. advanced-sequencer test plan for dwarfAlp.
# Run from this folder: python make_test_plan.py
# (Earlier plans 1 and 2 are kept as written by previous versions of this script.)
import itertools
import json

ids = itertools.count(1)
NS = "NINA.Sequencer"
COLL_ITEM = "System.Collections.ObjectModel.ObservableCollection`1[[NINA.Sequencer.SequenceItem.ISequenceItem, NINA.Sequencer]], System.ObjectModel"
COLL_COND = "System.Collections.ObjectModel.ObservableCollection`1[[NINA.Sequencer.Conditions.ISequenceCondition, NINA.Sequencer]], System.ObjectModel"
COLL_TRIG = "System.Collections.ObjectModel.ObservableCollection`1[[NINA.Sequencer.Trigger.ISequenceTrigger, NINA.Sequencer]], System.ObjectModel"


def container(cls, name, parent, items=(), conditions=(), extra=None):
    cid = str(next(ids))
    c = {
        "$id": cid,
        "$type": f"{NS}.Container.{cls}, {NS}",
        "Strategy": {"$type": f"{NS}.Container.ExecutionStrategy.SequentialStrategy, {NS}"},
        "Name": name,
    }
    if extra:
        c.update(extra)
    c["Conditions"] = {
        "$id": str(next(ids)),
        "$type": COLL_COND,
        "$values": [f(cid) for f in conditions],
    }
    c["IsExpanded"] = True
    c["Items"] = {
        "$id": str(next(ids)),
        "$type": COLL_ITEM,
        "$values": [f(cid) for f in items if f],
    }
    c["Triggers"] = {"$id": str(next(ids)), "$type": COLL_TRIG, "$values": []}
    if parent:
        c["Parent"] = {"$ref": parent}
    c["ErrorBehavior"] = 0
    c["Attempts"] = 1
    return c


def C(cls, name, items=(), conditions=(), extra=None):
    return lambda parent: container(cls, name, parent, items, conditions, extra)


def item(typ, **props):
    def f(parent):
        d = {"$id": str(next(ids)), "$type": f"{NS}.{typ}, {NS}"}
        d.update(props)
        d["Parent"] = {"$ref": parent}
        d["ErrorBehavior"] = 0
        d["Attempts"] = 1
        return d

    return f


def loop(n):
    def f(parent):
        return {
            "$id": str(next(ids)),
            "$type": f"{NS}.Conditions.LoopCondition, {NS}",
            "CompletedIterations": 0,
            "Iterations": n,
            "Parent": {"$ref": parent},
        }

    return f


def coords(rah, ram, ras, dd, dm, dsec, neg=False):
    return {
        "$id": str(next(ids)),
        "$type": "NINA.Astrometry.InputCoordinates, NINA.Astrometry",
        "RAHours": rah,
        "RAMinutes": ram,
        "RASeconds": ras,
        "NegativeDec": neg,
        "DecDegrees": dd,
        "DecMinutes": dm,
        "DecSeconds": dsec,
    }


def dso(title, target, c, items):
    def extra():
        return {
            "Target": {
                "$id": str(next(ids)),
                "$type": "NINA.Astrometry.InputTarget, NINA.Astrometry",
                "Expanded": True,
                "TargetName": target,
                "PositionAngle": 0.0,
                "InputCoordinates": c,
            },
            "ExposureInfoListExpanded": False,
        }

    return lambda parent: container("DeepSkyObjectContainer", title, parent, items, (), extra())


# Plan 3 runs without pauses: the checkpoint texts are kept as notes only.
PAUSES = False


def msg(text):
    return item("SequenceItem.Utility.MessageBox", Text=text) if PAUSES else None


def exposure(seconds, gain=-1):
    return item(
        "SequenceItem.Imaging.TakeExposure",
        ExposureTime=float(seconds),
        Gain=gain,
        Offset=-1,
        Binning={
            "$id": str(next(ids)),
            "$type": "NINA.Core.Model.Equipment.BinningMode, NINA.Core",
            "X": 1,
            "Y": 1,
        },
        ImageType="LIGHT",
        ExposureCount=0,
    )


def frames(n, seconds, name, gain=-1):
    return C("SequentialContainer", name, items=[exposure(seconds, gain)], conditions=[loop(n)])


FILTERS = {"VIS": ("VIS", 0), "Astro": ("Astro", 1), "HO": ("HO", 2)}


def filter_switch(key):
    name, position = FILTERS[key]

    def f(parent):
        bin_id = str(next(ids))
        return {
            "$id": str(next(ids)),
            "$type": f"{NS}.SequenceItem.FilterWheel.SwitchFilter, {NS}",
            "Filter": {
                "$id": str(next(ids)),
                "$type": "NINA.Core.Model.Equipment.FilterInfo, NINA.Core",
                "_name": name,
                "_focusOffset": 0,
                "_position": position,
                "_autoFocusExposureTime": -1.0,
                "_autoFocusFilter": False,
                "_autoFocusBinning": {
                    "$id": bin_id,
                    "$type": "NINA.Core.Model.Equipment.BinningMode, NINA.Core",
                    "X": 1,
                    "Y": 1,
                },
                "_autoFocusGain": -1,
                "_autoFocusOffset": -1,
            },
            "Parent": {"$ref": parent},
            "ErrorBehavior": 0,
            "Attempts": 1,
        }

    return f


slew = item("SequenceItem.Telescope.SlewScopeToRaDec", Inherited=True)
center = item("SequenceItem.Platesolving.Center", Inherited=True)


def tracking_stopped():
    return item("SequenceItem.Telescope.SetTracking", TrackingMode=5)  # Stopped


def wait(s):
    return item("SequenceItem.Utility.WaitForTimeSpan", Time=float(s))


root_id = str(next(ids))
root = {
    "$id": root_id,
    "$type": f"{NS}.Container.SequenceRootContainer, {NS}",
    "Strategy": {"$type": f"{NS}.Container.ExecutionStrategy.SequentialStrategy, {NS}"},
    "Name": "dwarfAlp DWARF 3 test plan 3",
    "Conditions": {"$id": str(next(ids)), "$type": COLL_COND, "$values": []},
    "IsExpanded": True,
}
start = C(
    "StartAreaContainer",
    "Start",
    items=[
        msg(
            "dwarfAlp test plan 3 (Astro and HO filters, gains, firmware V1.5.5.1). Before you continue: the Capture tab warning in dwarfAlp "
            "says 'V1.5.4.1 and V1.5.5.1' (current build), filters named Astro and HO, NINA Camera Timeout 180 s, telescope focal length 150 mm and "
            "focal ratio 4.3, ASTAP D50, plate solving exposure 10 s. Keep the dwarfAlp Activity tab in view."
        ),
    ],
)
targets = C(
    "TargetAreaContainer",
    "Targets",
    items=[
        dso(
            "Test 1 - M31: GOTO, Astro 10 s gain 60, HO 13 s gain 100",
            "M31",
            coords(0, 42, 44.3, 41, 16, 9.0),
            [
                slew,
                filter_switch("Astro"),
                frames(3, 10, "Astro 3 x 10 s gain 60", gain=60),
                filter_switch("HO"),
                frames(3, 13, "HO 3 x 13 s gain 100", gain=100),
                msg(
                    "Test 1 done. Activity should show: GOTO completed; Filter Astro, DWARF set to 10 s gain 60, 3 frames; "
                    "session ended (filter changed); Filter HO, DWARF set to 13 s gain 100, 3 frames. These pairs are not "
                    "DWARF presets: before the fix they never started. OK to continue."
                ),
            ],
        ),
        dso(
            "Test 2 - M81: Slew and Center, HO 30 s, Astro 15 s gain 130",
            "M81",
            coords(9, 55, 33.2, 69, 3, 55.0),
            [
                center,
                filter_switch("HO"),
                frames(3, 30, "HO 3 x 30 s gain 60", gain=60),
                filter_switch("Astro"),
                frames(3, 15, "Astro 3 x 15 s gain 130", gain=130),
                msg(
                    "Test 2 done. NINA should report M81 centred (the 10 s plate-solve frame failed before the fix). Activity: "
                    "HO 30 s gain 60, 3 frames; Astro 15 s gain 130, 3 frames. OK to continue."
                ),
            ],
        ),
        C(
            "SequentialContainer",
            "Test 3 - Exposure the DWARF cannot take (20 s)",
            items=[
                frames(1, 20, "1 x 20 s (expected to fail)", gain=60),
                msg(
                    "Test 3 done. NINA should report an error and Activity should show 'Exposure could not start: No exact "
                    "firmware exposure value ... 20s (supported: ...)'. OK to continue."
                ),
            ],
        ),
        C(
            "SequentialContainer",
            "Test 4 - Tracking off",
            items=[
                tracking_stopped(),
                wait(5),
                msg("Test 4 done. Activity should show: Tracking stopped by NINA. OK to continue."),
            ],
        ),
        dso(
            "Test 5 - M31: GOTO after tracking off, HO 4 x 45 s",
            "M31",
            coords(0, 42, 44.3, 41, 16, 9.0),
            [
                slew,
                filter_switch("HO"),
                msg(
                    "Test 5: during the next 45 s exposures press Stop in NINA, wait a few seconds and press Start again. "
                    "Activity should show the session ending (exposure aborted) and a new session starting, with no "
                    "'NINA stopped waiting' warning."
                ),
                frames(4, 45, "HO 4 x 45 s", gain=60),
            ],
        ),
    ],
)
end = C(
    "EndAreaContainer",
    "End",
    items=[
        tracking_stopped(),
        msg("Test plan 3 finished. Please send the Activity and Technical logs from dwarfAlp."),
    ],
)
root["Items"] = {
    "$id": str(next(ids)),
    "$type": COLL_ITEM,
    "$values": [start(root_id), targets(root_id), end(root_id)],
}
root["Triggers"] = {"$id": str(next(ids)), "$type": COLL_TRIG, "$values": []}
root["Parent"] = None
root["ErrorBehavior"] = 0
root["Attempts"] = 1
json.dump(
    root, open("dwarfAlp-test-plan-3.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False
)
print("ok")
