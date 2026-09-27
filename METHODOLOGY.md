# BCI Census methodology

The BCI Census answers one question with receipts: how many people are living with an implanted brain-computer interface right now?

## What counts

An **implanted brain-computer interface** is a device placed in the brain, on its surface (above or below the dura), or in a blood vessel of the brain that records neural signals to restore communication or movement.

In scope for version 1:

- Intracortical arrays (for example Neuralink, Paradromics, Blackrock/Utah arrays used by BrainGate)
- Endovascular electrodes (for example Synchron's Stentrode)
- Surface and epidural electrode arrays used as BCIs (for example Precision, Neuracle, NeuCyber)

Out of scope for version 1:

- Non-invasive devices (EEG, EMG, fNIRS, ultrasound, MEG)
- Stimulation-only therapies (deep brain stimulation for Parkinson's, responsive neurostimulation for epilepsy, closed-loop depression stimulators)
- Vision prostheses (retinal or cortical) and cochlear implants

## Three counts, never mixed

| Count | Meaning | In the headline? |
|---|---|---|
| Chronic implants | People with a BCI intended to stay implanted (30 days or more) | Yes |
| Acute procedures | Temporary implants, such as during tumor or epilepsy surgery, or up to 30 days | No, reported separately |
| Planned enrollment | Trial targets on ClinicalTrials.gov | Never counted as implants |

Published counts disagree (from about 50 to about 250) mostly because they mix these three, include or exclude China, treat trial enrollment as implants, and don't subtract removals.

## The verified floor

For each program, the floor is the larger of:

1. the most recent sourced count at tier A, B or C, or
2. the registry count: the sum of **actual** enrollment on ClinicalTrials.gov across its chronic implant trials that are still following participants (recruiting, active, enrolling by invitation or suspended) or that ended within the last five years.

We take the larger, not the sum, because company counts already include trial participants. The census headline is the sum of program floors. It is a floor: the true number is probably higher, and the site says so.

Details that keep the floor honest:

- **Targets never count.** Estimated enrollment is what a trial plans, not who was implanted.
- **Old trials drop out.** Participants of a trial that ended more than five years ago may have had devices removed, so the trial is listed but not counted. Records ClinicalTrials.gov marks as "unknown status" are not counted either.
- **Enrolled is not always implanted.** When a paper or the sponsor gives the number actually implanted, `data/curated/trial_overrides.yaml` records it with its source and it replaces the enrollment count. Example: SWITCH (NCT03834857) lists 5 enrolled; its paper reports 4 implanted.
- **"Living with" means implanted and not reported removed or dead.** Removals and deaths are subtracted when a source reports them.

## Verification tiers

| Tier | Source type | Counted? |
|---|---|---|
| A | Registry or peer review: ClinicalTrials.gov actual enrollment, FDA or NMPA records, peer-reviewed papers | Yes |
| B | Company primary statement: press release, filing, official post | Yes |
| C | Credible press citing the company or a regulator | Yes |
| D | Aggregators and unsourced claims | Shown for context, never counted |

Every fact carries a value, an as-of date, a tier, a source URL and the date it was last checked. Items without a usable source sit in `data/curated/verify_queue.yaml` until someone finds one.

## Sources pulled every week

- **ClinicalTrials.gov API v2:** trials, status, enrollment (actual or estimated), countries.
- **openFDA:** 510(k) and PMA decisions by applicant and device name. A curated event that already covers a decision (for example Precision's K242618) replaces the raw record.
- **SEC EDGAR:** Form D filings (private offerings) for tracked companies: amount sold, date of first sale, number of investors. Companies are matched by their EDGAR CIK, never by a name that could belong to an investment vehicle (for example an SPV named after the company).
- **Curated facts** in `data/curated/*.yaml` for everything the databases don't hold: implant counts, Breakthrough designations, IDE approvals, foreign approvals and announced rounds.

The trial classifier is rules-based (`census/scope.py`) and every decision is published with its reason in `trials_all.csv`. Wrong calls are fixed in `data/curated/trial_overrides.yaml`.

## How a trial gets in

The weekly search returns several hundred ClinicalTrials.gov records. A record is an implanted BCI trial when it:

1. **names a BCI**: "brain-computer interface", "brain-machine interface", "brain-spine interface", BCI or iBCI, or a device such as BrainGate, Stentrode, Connexus, Layer 7, NeuroPort or WIMAGINE; and
2. **describes an implant in or on the brain**, or in a brain blood vessel: intracortical electrodes or arrays, Utah arrays, electrocorticography (ECoG), subdural or epidural cortical electrodes, endovascular electrodes, intracranial or stereo-EEG electrodes, or an implant explicitly placed on or in the cortex; and
3. for a permanent implant, **implants someone**: an interventional study with a device or procedure (or an implant named in its title). Observational follow-ups of people already implanted are left out so no one is counted twice.

Traps the rules avoid, each found in the real result set:

| Looks like a BCI trial | Why it is out |
|---|---|
| TMS studies of "intracortical inhibition" | A magnetic-stimulation measure, not an implant |
| Implanted "neuroprostheses" for hand grasp or standing | Functional electrical stimulation of muscles or nerves, not a brain interface |
| EEG-based BCI paired with an implanted spinal cord stimulator | The implant is in the spine; the BCI is a scalp headset |
| Nerve-cuff and myoneural interfaces | Peripheral nerves, not the brain |
| Closed-loop deep brain stimulation for Parkinson's or epilepsy | Stimulation therapy, unless the record describes communication or movement for paralysis |
| Retinal and cochlear implants | Sensory prostheses, out of scope for version 1 |

A trial is **temporary (acute)** when the record says the electrodes are placed during surgery or clinical epilepsy monitoring, or stay in for a set number of days (for example "up to 29 days"). The detailed description is checked for this too.

**Calibration.** On September 26, 2026 the rules were run against all 628 records the weekly search returned. 64 were kept (56 permanent implants, 8 temporary). Before calibration, a first version kept 160, mostly TMS studies and muscle-stimulation neuroprostheses; each of those traps is now a regression test in `tests/test_scope.py`.

## Personal data

None. The census never lists participants' names, even when they are public. Counts only.

## Removals and deaths

Removed devices are subtracted when a source reports them. Version 1 has little data on removals; this is a known gap.

## Corrections

Open an issue with a source link. Accepted corrections are credited in the weekly changelog.
