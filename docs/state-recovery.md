# Recover the interrupted 16 November creation

The creation run expired while EKS was provisioning. AWS created resources
that are absent from the latest S3 state. Do not run apply/destroy or recreate
those resources until state has been reconciled.

The exported `aws login` credentials last only 15 minutes. Local AWS tools
refresh them; static GitHub secrets cannot. Normal deployment now requires
`bootstrap` environment variable `AWS_CREDENTIAL_EXPIRATION` and checks at
least 55 minutes remain before starting, and 45 before apply. Obtain an
approved session of sufficient length before resuming provisioning. This
check depends on supplying the real expiration for the exact copied session;
it cannot infer the expiration from a successful STS identity call.

## Incident scope

Latest known state: version `vKltn3IEA7Ll5E3SIAjUo_bm7zZuu9LK`, modified
2026-11-16 10:06:04 UTC. Preserve this version. If `errored.tfstate` from the
original runner is available, inspect that preferred recovery source first.
It was not uploaded by the original workflow; a rerun gets a new hosted
runner and does not recover the old local file.

Known live but untracked resources include:

- `eks-gateway` in `vpc-00127c0d370f4e9b2` and `eks-backend` in
  `vpc-08829c8d48837184a`.
- Gateway NAT `nat-0ac478601d695daeb`.
- Runner `i-0138e5cfebfd91401`, SG `sg-0dc8d607af1fc0ec4` and HTTPS rule
  `sgr-0ee4ba5dda241838b`.
- Four private default routes created after the saved state snapshot.

`scripts/recover-sentinel-state.py` is deliberately restricted to this
incident. Do not reuse its resource inventory in another environment.

## Procedure

1. Keep Terraform deploy disabled. Confirm the failed run is finished and
   no Terraform operation is running locally, in another workflow or elsewhere.
2. Merge this recovery workflow through a PR. Validation can run without AWS.
   Do not enable ordinary deploy while merging this change.
3. Review the S3 lock at `sentinel/terraform.tfstate.tflock` using AWS CLI or
   the console. Record its `ID`, `Created` and `Operation`. Do not delete it
   directly. If there is no object, leave the workflow lock input empty.
4. Record the failed deployment's numeric Actions run ID from its URL:
   `.../actions/runs/NUMBER`. The script checks through GitHub that it is a
   completed failed Terraform deploy on main. This does not prove the lock's
   ownership; reviewing the lock and confirming no active operation is required.
5. Refresh all three bootstrap secrets from the same authorized session. For
   recovery, at least 10 minutes must remain when the import script starts.
   Longer-lived credentials are preferred. Provide the exact expiration in
   the workflow input. The script stops between imports if less than four
   minutes remain, so an interrupted recovery may need a subsequent fresh run.
6. Run **Recover interrupted Sentinel state** on `main`. Enter
   `RECOVER-SENTINEL`, the failed run ID, exact credential expiration, and
   the reviewed stale lock ID (or empty if no lock exists).
7. The script verifies account, VPCs, clusters, NATs, routes and runner
   inventory before changing state. It backs up the current state to the
   same protected, encrypted, versioned S3 bucket under
   `sentinel/recovery/RUN_ID/ATTEMPT/before.tfstate`. Backup failure aborts.
8. If a lock exists, the script requires an exact ID match before calling
   Terraform force-unlock. It never uses `-lock=false`. If lock state has
   changed, stop and inspect again.
9. Missing resources are imported through Actions. Matching existing
   bindings are skipped; conflicting bindings abort. Import changes Terraform
   tracking only, and does not run infrastructure apply. Each import uses
   ordinary backend locking.
10. It verifies the bindings and creates a review-only plan. No apply follows.
    Planned deletion or replacement fails the workflow for review. Read all
    proposed additions as well: the incident inventory is bounded, not an
    account-wide guarantee that every orphan has been found.

If a retry is needed, inspect the current state and lock first, refresh
credentials and supply the current lock input. Imports are restartable.
Do not push an older state with `-force` or remove state entries to suppress
conflicts. S3 versioning retains backup history; never commit state files
or expose them as public GitHub artifacts.

Only after successful recovery and plan review should ordinary provisioning
resume with both bootstrap flags true and a sufficiently long session. Nodes,
add-ons, application access and other not-yet-created resources are expected
additions. A green recovery run does not mean the application has deployed.

Recovery logic has local tests; the workflow itself has not yet been run
against this incident. The failure backup step attempts protected S3 upload
of an `errored.tfstate` if one exists, but cannot succeed with expired AWS
credentials. It is not a substitute for providing adequate credential lifetime.
