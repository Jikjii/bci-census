"""Decide whether a trial is an implanted BCI, and whether the implant is chronic or acute.

A trial is in scope when its record names a brain-computer interface AND describes an
implant in or on the brain (or in a brain blood vessel). Rules were calibrated on the
full ClinicalTrials.gov result set; the traps they avoid are listed in METHODOLOGY.md.
Every decision carries its reason, so a wrong call can be spotted on the site and fixed
in data/curated/trial_overrides.yaml.
"""

from __future__ import annotations

import re

_I = re.IGNORECASE
DASH = r"[\s‐-―−-]*"  # hyphens, en and em dashes, spaces
BCI_TERM = rf"(?:brain{DASH}(?:computer|machine|spine){DASH}interfaces?|\bi?BCIs?\b)"


def _any(patterns: list[re.Pattern], text: str) -> str | None:
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, _I) for p in patterns]


# A BCI must be named. Bare "intracortical" (a TMS measure), "neuroprosthesis" (often
# functional electrical stimulation) and "neural interface" (often a nerve) are not enough.
BCI_SIGNALS = _compile(
    [
        rf"brain{DASH}(?:computer|machine){DASH}interfaces?",
        rf"brain{DASH}spine{DASH}interfaces?",
        r"\bi?BCIs?\b",
        rf"brain{DASH}controlled",
        r"braingate",
        r"stentrode",
        r"neuralink",
        r"\bsynchron\b",
        r"connexus",
        r"layer 7",
        r"neuroport",
        r"wimagine",
        r"beinao",
        r"neuracle",
        r"\b(?:arc|stimo)-?bsi\b",
        r"(?:speech|communication|cortical) neuroprosthe\w*",
        r"neural interface system",
        r"(?:intra)?cortical (?:neural )?interface",
        r"speech decod\w*",
        r"decod\w* (?:of )?(?:the )?(?:attempted |intended |imagined |inner )?(?:speech|handwriting|movements?|motor intent\w*|intent\w*)",
    ]
)

# The implant must be in or on the brain, or in a brain blood vessel.
BRAIN_IMPLANT = _compile(
    [
        r"\biBCIs?\b",
        r"intracortical (?:micro)?electrode",
        r"intracortical (?:brain|neural|recording|interface|implant|array|BCI|BMI|microstimulation|signal)",
        r"micro-?electrode arrays?",
        r"utah (?:electrode )?arrays?",
        r"neuroport",
        r"stentrode",
        r"wimagine",
        r"connexus",
        r"layer 7",
        r"neuralink",
        r"braingate",
        r"beinao",
        r"\bN1 implant",
        r"electrocorticogra\w*",
        r"\bECoG\b",
        r"subdural (?:electrode|grid|strip|array|implant)",
        r"epidural (?:ECoG|electrocorticogra\w*|cortical|brain)",
        r"(?:cortical|brain|cortex) (?:surface )?(?:electrodes?|arrays?|implant\w*|sensors?)\b",  # not "cortical sensorimotor"
        r"implantable neural (?:signal )?(?:acquisit\w*|recording)",  # Neuracle NEO's registry wording
        r"surface of the (?:brain|cortex)",
        r"endovascular (?:brain|BCI|neural|electrode|array|stent|motor neuroprosthe|neuroprosthe|recording)",
        rf"stent{DASH}electrode",
        r"stereo-?EEG",
        r"\bSEEG\b",
        r"intracranial (?:EEG|electrode|recording|monitoring|implant|array|neural|sensor)",
        r"depth electrode",
        r"brain implant",
        r"cortical implant",
        r"neural probe",
        r"implant\w* (?:in|into|on|over|within|under) (?:the )?(?:\w+[\s-]+){0,3}?(?:cortex|brain|cortical|skull|dura)",
        # "placed on the cortex" means contact with the brain; EEG papers say "over" the cortex, which is not matched.
        r"(?:placed|positioned|laid|inserted) (?:directly )?(?:on|onto|into|in) (?:the )?(?:\w+[\s-]+){0,2}?(?:cortex|brain)\b(?! regions?| areas?| activity| signals?)",
        r"(?:semi|minimally)[\s-]*invasive (?:\w+ ){0,2}(?:brain|BCI|neural|cortical)",
        r"(?<!non)(?<!non-)(?<!non )\binvasive (?:brain|BCI|BMI|neural interface)",
    ]
)

# Weaker evidence: an implant word right next to a BCI term.
BRAIN_IMPLANT_NEAR_BCI = _compile(
    [
        rf"implant\w*(?:\W+\w+){{0,3}}?\W+{BCI_TERM}",
        rf"{BCI_TERM}(?:\W+\w+){{0,2}}?\W+implant",
    ]
)

# When the only implant evidence is weak, these show the implant is elsewhere.
SPINAL_OR_PERIPHERAL = _compile(
    [
        r"spinal cord stimulat",
        r"epidural (?:electrical )?stimulat",
        r"\bSCS\b",
        r"\bEES\b",
        r"peripheral nerve",
        r"nerve cuff",
        r"functional electrical stimulat",
        r"\bFES\b",
        r"targeted muscle reinnervation",
        r"osseointegrat",
        r"\bRPNI\b",
        r"(?:median|ulnar|sciatic|radial) nerve",
    ]
)

IMPLANT_ANY = _compile([r"implant", r"surgically"])

SENSORY_PROSTHESES = _compile([r"cochlear", r"auditory brainstem"])

NON_INVASIVE = _compile(
    [
        r"non-?invasive",
        r"electroencephalogra",
        r"(?<!stereo-)(?<!stereo)\bEEG\b",
        r"\bEMG\b",
        r"electromyogra",
        r"\bfNIRS\b",
        r"near-?infrared",
        r"transcranial",
        r"\bTMS\b",
        r"\btDCS\b",
        r"headset",
        r"\bMEG\b",
        r"ultrasound",
        r"\bfMRI\b",
    ]
)

STIMULATION_THERAPY = _compile(
    [
        r"deep brain stimulation",
        r"\bDBS\b",
        r"responsive neurostimulat",
        r"\bRNS\b",
        r"vagus nerve",
        r"spinal cord stimulat",
        r"closed-?loop (?:neuro)?stimulat",
    ]
)

THERAPY_CONDITIONS = _compile(
    [
        r"parkinson",
        r"essential tremor",
        r"dystonia",
        r"epilep",
        r"seizure",
        r"depress",
        r"obsessive",
        r"\bOCD\b",
        r"chronic pain",
        r"tourette",
        r"alzheimer",
    ]
)

# What BCIs in scope are for: communication or movement for people with paralysis.
BCI_PURPOSE = _compile(
    [
        r"(?:restor\w*|augmentative|alternative|assistive) (?:\w+ ){0,2}communicat",
        r"communicat\w* (?:device|aid|system|interface|neuroprosthe\w*|BCI)",
        r"speech (?:neuroprosthe|decod|restor|synthes|BCI|brain)",
        r"(?:restor\w*|decod\w*|synthes\w*) (?:of )?(?:\w+ )?speech",
        r"\btyping\b",
        r"cursor",
        r"spell(?:ing|er)",
        r"control (?:of )?(?:an? |the )?(?:\w+ )?(?:computer|robot\w*|prosthe\w*|arm|hand|device|tablet|wheelchair|exoskeleton|assistive)",
        r"tetrapleg",
        r"quadripleg",
        r"paraly",
        r"amyotrophic",
        r"\bALS\b",
        r"locked-?in",
        r"spinal cord injur",
        r"brainstem stroke",
        r"anarthria",
    ]
)

VISION = _compile(
    [
        r"retina",
        r"visual prosthe",
        r"\borion\b",
        r"cortical visual",
        r"blindsight",
        r"\bblindness\b",
        r"restor\w* (?:of )?(?:sight|vision)",
    ]
)

# Temporary implants: placed during surgery or clinical monitoring, then removed.
ACUTE = _compile(
    [
        r"intra-?operative",
        r"awake craniotomy",
        r"epilepsy monitoring",
        r"stereo-?EEG",
        r"\bSEEG\b",
        r"subdural grid",
        r"intracranial (?:EEG|monitoring|recording)",
        r"clinically[\s-]*indicated",
        r"already[\s-]*(?:scheduled|planned)",
        r"(?:scheduled|planned|standard[\s-]*of[\s-]*care) (?:\w+[\s-]+){0,4}?(?:resection|craniotomy|monitoring)",
        r"undergoing (?:\w+[\s-]+){0,4}?(?:resection|craniotomy|epilepsy surgery|tumou?r surgery|monitoring)",
        r"(?:epilep\w*|tumou?r|glioma) (?:\w+ ){0,2}(?:surgery|surgeries|resection)",
        r"temporar\w* (?:\w+ ){0,2}(?:implant\w*|placement|electrode|use|recording|array|device)",
        r"up to (?:\d+|thirty|twenty[\s-]*nine) days",
        r"\bacute(?:ly)? (?:implant\w*|recording|stimulation|intracranial|study|experiment)",
        r"(?:removed|explant\w*) (?:\w+ ){0,2}(?:after|at|within) (?:\d+|thirty) (?:days|weeks)",
    ]
)

# Weak hint of a temporary implant; used only when nothing says the implant is long-term.
ACUTE_WEAK = _compile([r"during (?:\w+ ){0,3}?(?:neurosurg\w*|resection|craniotomy|brain surgery|DBS surgery)"])

CHRONIC = _compile(
    [
        r"chronic(?:ally)? (?:implant\w*|recording|use|BCI|brain|intracortical)",
        r"long[\s-]*term (?:implant\w*|use|safety|recording|study|follow)",
        r"permanent(?:ly)?",
        r"fully[\s-]*implant\w*",
        r"(?:at[\s-]*|in[\s-]*)?home use",
        r"use at home",
    ]
)

IMPLANTING_INTERVENTIONS = {"DEVICE", "PROCEDURE", "COMBINATION_PRODUCT"}
# Some implant trials type the intervention as "Other" but still say so in the title.
IMPLANT_IN_TITLE = _compile([r"implant", r"(?<!non)(?<!non-)(?<!non )\binvasive"])


def _title_text(trial: dict) -> str:
    names = " ".join(i.get("name", "") for i in trial.get("interventions") or [])
    return " \n ".join(p for p in (trial.get("title", ""), trial.get("official_title", ""), names) if p)


def trial_text(trial: dict) -> str:
    """Text used to decide scope: titles, summary, conditions, keywords, interventions."""
    parts = [
        trial.get("title", ""),
        trial.get("official_title", ""),
        trial.get("summary", ""),
        " ".join(trial.get("conditions") or []),
        " ".join(trial.get("keywords") or []),
    ]
    for item in trial.get("interventions") or []:
        parts.append(item.get("name", ""))
        parts.append(item.get("description", ""))
    return " \n ".join(p for p in parts if p)


def _duration(text: str) -> tuple[str, str]:
    acute = _any(ACUTE, text)
    if acute:
        return "acute", acute
    weak = _any(ACUTE_WEAK, text)
    if weak and not _any(CHRONIC, text):
        return "acute", weak
    return "chronic", ""


def classify(trial: dict, overrides: dict | None = None) -> dict:
    """Return {"in_scope", "duration", "reason"} for one normalized trial."""
    overrides = overrides or {}
    manual = overrides.get(trial.get("nct_id", "")) or {}
    if "in_scope" in manual:
        return {
            "in_scope": bool(manual["in_scope"]),
            "duration": manual.get("duration", "chronic") if manual["in_scope"] else "",
            "reason": "Manual override: " + (manual.get("reason") or "see trial_overrides.yaml"),
        }

    text = trial_text(trial)

    def out(reason: str) -> dict:
        return {"in_scope": False, "duration": "", "reason": reason}

    purpose = _any(BCI_PURPOSE, text)
    vision = _any(VISION, text)
    if vision and not purpose:
        return out(f"Vision prosthesis, out of v1 scope ('{vision}')")
    sensory = _any(SENSORY_PROSTHESES, text)
    if sensory:
        return out(f"Sensory prosthesis, out of v1 scope ('{sensory}')")
    bci = _any(BCI_SIGNALS, text)
    if not bci:
        return out("No BCI named in the record")
    stim, therapy = _any(STIMULATION_THERAPY, text), _any(THERAPY_CONDITIONS, text)
    if stim and therapy and not purpose:
        return out(f"Stimulation therapy for {therapy}, not a BCI for communication or movement")

    brain = _any(BRAIN_IMPLANT, text)
    if not brain:
        near = _any(BRAIN_IMPLANT_NEAR_BCI, text)
        elsewhere = _any(SPINAL_OR_PERIPHERAL, text)
        if near and elsewhere:
            return out(f"The implant is spinal or peripheral, not in the brain ('{elsewhere}')")
        if not near:
            non_invasive = _any(NON_INVASIVE, text)
            if non_invasive:
                return out(f"Non-invasive ('{non_invasive}')")
            if _any(IMPLANT_ANY, text):
                return out("An implant is described, but not in the brain")
            return out("BCI without a brain implant described")
        brain = near

    duration, why = _duration(text + " \n " + (trial.get("details") or ""))
    if duration == "chronic":
        if (trial.get("study_type") or "").upper() == "OBSERVATIONAL":
            return out("Observational study of an implanted BCI; it does not implant anyone")
        types = {(i.get("type") or "").upper() for i in trial.get("interventions") or []}
        if not types & IMPLANTING_INTERVENTIONS and not _any(IMPLANT_IN_TITLE, _title_text(trial)):
            return out("No device or procedure intervention; the study does not implant anyone")
        reason = f"Implanted BCI ('{bci}', '{brain}')"
    else:
        reason = f"Implanted BCI, temporary ('{why}')"
    manual_duration = manual.get("duration")
    if manual_duration in ("acute", "chronic") and manual_duration != duration:
        return {"in_scope": True, "duration": manual_duration, "reason": f"{reason}; duration set by override"}
    return {"in_scope": True, "duration": duration, "reason": reason}
