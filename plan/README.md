# Planning documents

Plans are archived when their scoped code changes are implemented. Test and
runtime acceptance can remain open and is tracked in the active register.

## Active plans

- [Core roadmap](PROJECT_PLAN.md)
- [Implementation, test/runtime status and open backlog](ROADMAP_STATUS_AND_BACKLOG.md)
- [Remediation plan](Remediation_Plan_19-10-2026.md)
- [Linux runtime Phase 5](Phase_5_Linux_Container_Runtime_Verification.md)
- [Round 2 review](Review%20Round%202%20By%20GPT%206.1%20Sol%2014-10-2026.md)
- [Security review](Review%20Security%2014-10-2026.md)
- [Right Active Checks panel and responsive progress](Dashboard_Right_Active_Checks_Plan_20-10-2026.md)
- [Left Overview panel and status shortcuts](Dashboard_Left_Overview_Plan_20-10-2026.md)
- [Existing progress popover — remaining feature acceptance](Run_Check_Progress_Popover_Plan_20-10-2026.md)

Implement the right-panel layout first. The left Overview is a separate delivery
using the same responsive frame. Both new plans are Not started / Not run / Not
verified; this documentation update does not implement either panel.

## Archived on 2026-10-20 because scoped code implementation is complete

- [Run Check Progress Popover — four-defect remediation](archive/implemented-20261020/Run_Check_Progress_Popover_Remediation_Plan_20-10-2026.md)

Only the scoped remediation plan moved. The popover feature plan remains active
with Partial implementation/acceptance and unverified browser/Linux runtime.
Other active security/remediation/runtime plans retain open work and were not
archived. Existing test failures and runtime exclusions remain unchanged.

## Archived on 2026-10-19 because code implementation is complete

- [Member Management](archive/implemented-20261019/MEMBER_MANAGEMENT_PLAN.md)
- [Focus flicker fix](archive/implemented-20261019/Page-Flicker-On-Window-Focus-Fix%20By%20Argon.md)
- [OK target scheduling fix](archive/implemented-20261019/Review%20issue%20by%20Argon%20Edit%20by%20Sol.md)
- [First review remediations](archive/implemented-20261019/Review%20By%20GPT%206.1%20Sol%2014-10-2026.md)

Original reports and requirements are retained. Archiving does not establish a
test pass or verified deployment; follow remaining acceptance in the active register.

## Documentation verification — 2026-10-20

Windows checkout, Asia/Bangkok; source `06adbb6923713acf327da7798591da58462fe229`
plus local planning changes. A local Python link/whitespace check inspected the
two new plans, archived remediation plan, existing popover plan, this index and
the status register: six documents, 57 local links, zero errors. `git diff
--check` passed. The old remediation path is absent and its archived destination
exists. No application tests or browser/runtime checks were run for this
documentation-only update; no previous verification status was upgraded.
