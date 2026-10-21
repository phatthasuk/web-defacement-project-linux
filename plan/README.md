# Planning documents

Delivered or superseded feature plans may be archived at the user's request.
Archiving does not mark incomplete implementation, tests or runtime acceptance
complete; remaining work stays in the active register.

## Active plans

- [Core roadmap](PROJECT_PLAN.md)
- [Implementation, test/runtime status and open backlog](ROADMAP_STATUS_AND_BACKLOG.md)
- [Remediation plan](Remediation_Plan_19-10-2026.md)
- [Linux runtime Phase 5](Phase_5_Linux_Container_Runtime_Verification.md)
- [Round 2 review](Review%20Round%202%20By%20GPT%206.1%20Sol%2014-10-2026.md)
- [Security review](Review%20Security%2014-10-2026.md)
- [Run Check Popover removal](Run_Check_Popover_Removal_Plan_20-10-2026.md)
- [Left Overview panel and status shortcuts](Dashboard_Left_Overview_Plan_20-10-2026.md)

The left Overview is a separate delivery using the right panel's responsive
frame. The right panel and inline card follow-up have
partial implementation and verification; the left Overview is Not started / Not
run / Not verified. Browser and production acceptance remain open.

The user requested execution of the [Popover removal plan](Run_Check_Popover_Removal_Plan_20-10-2026.md).
Its scoped frontend implementation is complete; tests are Partial and browser,
Node 20 and Linux/runtime acceptance remain open. See the
[execution record](../refinement/10-20-2026/Run-Check-Popover-Removal-20-10-2026.md).
Completed-card retention remains unchanged.

## Audit reports

- [Code cleanliness audit 2026-10-21](Code_Cleanliness_Audit_21-10-2026.md)
  records eight proposed cleanup items and the checks actually run. Remediation
  implemented and verified in
  [execution record](../refinement/10-21-2026/Code-Cleanliness-Audit-Remediation-21-10-2026.md).

## Archived UI deliveries on 2026-10-20

- [Right Active Checks panel](archive/delivered-ui-20261020/Dashboard_Right_Active_Checks_Plan_20-10-2026.md)
- [Active Checks inline card progress](archive/delivered-ui-20261020/Active_Checks_Inline_Card_Progress_Plan_20-10-2026.md)
- [Original Run Check Progress Popover](archive/delivered-ui-20261020/Run_Check_Progress_Popover_Plan_20-10-2026.md)

These documents retain their Partial statuses and historical results. The
[active remaining-work register](ROADMAP_STATUS_AND_BACKLOG.md#archived-ui-deliveries-and-remaining-work)
owns their unfinished implementation and acceptance. The new Popover removal
plan and unimplemented left Overview remain active; archiving is not a test or
production sign-off.

## Archived on 2026-10-20 because scoped code implementation is complete

- [Run Check Progress Popover — four-defect remediation](archive/implemented-20261020/Run_Check_Progress_Popover_Remediation_Plan_20-10-2026.md)

The earlier operation moved only the scoped remediation plan. The original
Popover feature plan is now in the delivered-UI archive with its Partial
implementation/acceptance and unverified browser/Linux runtime unchanged.
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

**Later archive update:** Windows checkout, Asia/Bangkok; source
`6b260c407548ccae0b12042c24db70435d22dc52` plus local documentation changes.
Moved three delivered/superseded UI plans to `archive/delivered-ui-20261020/`;
rebased their local links and updated inbound references. A local Python check
verified nine related documents and 79 local links with zero errors; old source
paths are absent and all three archive destinations exist. `git diff --check`
passed. No application test, code change or production operation was performed;
recorded Partial statuses and remaining requirements were preserved.

Windows checkout, Asia/Bangkok; source `06adbb6923713acf327da7798591da58462fe229`
plus local planning changes. A local Python link/whitespace check inspected the
two new plans, archived remediation plan, existing popover plan, this index and
the status register: six documents, 57 local links, zero errors. `git diff
--check` passed. The old remediation path is absent and its archived destination
exists. No application tests or browser/runtime checks were run for this
documentation-only update; no previous verification status was upgraded.
