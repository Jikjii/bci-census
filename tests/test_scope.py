import pytest

from census.link import link_trial
from census.scope import classify

EXPECTED = {
    "NCT90000001": (True, "chronic"),   # intracortical, company trial
    "NCT90000002": (True, "chronic"),   # endovascular
    "NCT90000003": (False, ""),         # scalp EEG
    "NCT90000004": (False, ""),         # sensing DBS for Parkinson's
    "NCT90000005": (True, "acute"),     # ECoG during epilepsy monitoring
    "NCT90000006": (False, ""),         # retinal prosthesis
    "NCT90000007": (False, ""),         # peripheral nerve interface
    "NCT90000008": (True, "chronic"),   # BrainGate-style arrays
}


@pytest.mark.parametrize("nct,expected", EXPECTED.items())
def test_classifier(trials, nct, expected):
    trial = next(t for t in trials if t["nct_id"] == nct)
    result = classify(trial)
    assert (result["in_scope"], result["duration"]) == expected, result["reason"]
    assert result["reason"]


def test_override_wins(trials):
    trial = next(t for t in trials if t["nct_id"] == "NCT90000003")
    result = classify(trial, {"NCT90000003": {"in_scope": True, "duration": "chronic", "reason": "test"}})
    assert result["in_scope"] is True
    assert result["reason"].startswith("Manual override")


def test_program_linking(trials, bundle):
    by_id = {t["nct_id"]: t for t in trials}
    programs = bundle["programs"]
    assert link_trial(by_id["NCT90000001"], programs) == "neuralink"
    assert link_trial(by_id["NCT90000002"], programs) == "synchron"
    assert link_trial(by_id["NCT90000008"], programs) == "braingate"
    assert link_trial(by_id["NCT90000005"], programs) == "academic-other"


def _t(nct, title, summary="", itype="DEVICE", iname="Device", details="", study_type="INTERVENTIONAL", sponsor="Example University"):
    return {
        "nct_id": nct, "title": title, "official_title": "", "summary": summary, "details": details,
        "conditions": [], "keywords": [], "interventions": [{"type": itype, "name": iname, "description": ""}],
        "study_type": study_type, "sponsor": sponsor, "collaborators": [],
    }


# Traps found in the full ClinicalTrials.gov result set (628 studies, Sep 2026). Wording follows the real records.
REAL_WORLD = [
    (_t("R01", "TMS Studies of Dystonia", "We measure short-interval intracortical inhibition with TMS."), (False, "")),
    (_t("R02", "Implantable Functional Neuromuscular Stimulation System for Hand Grasp",
        "An implanted neuroprosthesis restores grasp in tetraplegia."), (False, "")),
    (_t("R03", "Spinal Cord Stimulation Combined With Motor Imagery Brain-Computer Interface",
        "A brain-computer interface and an implanted spinal cord stimulator."), (False, "")),
    (_t("R04", "DiSCIoser: Improving Arm Function After Spinal Cord Injury Via Brain-Computer Interface",
        "EEG-based BCI training to promote cortical sensorimotor plasticity.", itype="OTHER"), (False, "")),
    (_t("R05", "Agonist-Antagonist Myoneural Interface for Functional Limb Restoration", "Surgically created muscle pairs."), (False, "")),
    (_t("R06", "Understanding Motor Function in Stroke Patients (BrainSync)", "Prepares future WIMAGINE implant studies.",
        itype="OTHER", iname="Functional MRI (fMRI) Acquisition"), (False, "")),
    (_t("R07", "Clinical Outcome Assessment for BCI users", "People with an implanted brain-computer interface.",
        study_type="OBSERVATIONAL"), (False, "")),
    (_t("R08", "First-In-human Trial of a Soft and Stretchable Neural probE",
        "Insert the soft neural probe into brain tissue during their already scheduled brain tumor or epileptic "
        "tissue resection. Brain-computer interface research.", iname="Soft Neural Probe", sponsor="Axoft, Inc."), (True, "acute")),
    (_t("R09", "ECoG Direct Brain Interface for Individuals With Upper Limb Paralysis",
        "Direct brain control using an electrocorticography (ECoG)-based brain computer interface system.",
        details="Each participant will undergo testing of the ECoG direct brain interface for up to 29 days."), (True, "acute")),
    (_t("R10", "A Prospective Clinical Trial of an Implantable Neural Acquisitor & Stimulator System in Patients With "
        "Motor Disability", "Through brain-computer interface technology, patients control external equipment.",
        iname="NEO", sponsor="Neuracle Medical Technology(Shanghai) Co.,Ltd."), (True, "chronic")),
    (_t("R11", "Safety and Efficacy of High-Channel Implanted BCI for Motor Function", "An invasive BCI study.",
        itype="OTHER", iname="Invasive BCI"), (True, "chronic")),
    (_t("R12", "Brain–computer interface for ALS", "A brain–computer interface with electrodes implanted on the cortex."),
     (True, "chronic")),
    (_t("R13", "iBCI Optimization for Veterans With Paralysis", "Participants use an iBCI."), (True, "chronic")),
    (_t("R14", "Adaptive DBS for Parkinson's disease",
        "A closed-loop brain-computer interface adjusts deep brain stimulation; speech outcomes are measured.",
        iname="Implanted sensing DBS"), (False, "")),
]


@pytest.mark.parametrize("trial,expected", REAL_WORLD, ids=[t["nct_id"] for t, _ in REAL_WORLD])
def test_real_world_traps(trial, expected):
    result = classify(trial)
    assert (result["in_scope"], result["duration"]) == expected, result["reason"]


def test_linking_uses_whole_words(bundle):
    programs = bundle["programs"]
    synchronous = _t("L1", "Synchronous cueing with an implanted brain-computer interface", sponsor="Synchronous Labs")
    assert link_trial(synchronous, programs) == "academic-other"
    bsi = _t("L2", "Brain-controlled Spinal Cord Stimulation", iname="ARC-BSI Lumbar System",
             sponsor="Ecole Polytechnique Fédérale de Lausanne")
    assert link_trial(bsi, programs) == "onward"
    neo = _t("L3", "Implantable Neural Acquisitor", iname="NEO", sponsor="Neuracle Medical Technology(Shanghai) Co.,Ltd.")
    assert link_trial(neo, programs) == "neuracle"


def test_duration_override_keeps_scope():
    trial = _t("D1", "Chronic intracortical BCI", "Utah arrays implanted in motor cortex for a brain-computer interface.")
    result = classify(trial, {"D1": {"duration": "acute", "reason": "test"}})
    assert result["in_scope"] and result["duration"] == "acute"
