# Teardown of the recovered environment

Use this guide after recording recreation evidence and verifying temporary
node CNI and installer permissions have been removed. The existing completion
role cannot perform full teardown. Do not dispatch cleanup with its credentials.

## Prepare the separate role

Keep Terraform deploy disabled; avoid application deployments during teardown.
Merge the teardown changes into main, pull them locally, and run in Windows
PowerShell from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode BootstrapTeardown
```

This authenticates the local operator, updates bootstrap secrets from that
session, and dispatches the short **Prepare scoped teardown role** workflow.
It does not delete workloads or Terraform-managed infrastructure.

The workflow reads the private remote state without publishing it. It verifies
the two recovered VPC IDs and cluster names, refuses unreviewed managed resource
types or IAM names outside the approved prefixes, and creates
`sentinel-terraform-teardown`. Its trust is restricted to the full reviewed
`/managed/AccountFullAccessRole` ARN. Existing roles with unexpected ownership,
trust or additional policies are not overwritten.

IAM, EC2 and ECR deletion targets are derived from state. EKS operations are
limited to the two named clusters and their subresources. Controller backend
security groups are discovered by project VPC and controller tags; rule
revocation is restricted to the project's state/controller/cluster groups.
There is no permission to create infrastructure, pass roles, mutate the
teardown identity itself, delete the state object, or delete the state bucket.
The only deletable S3 object is the state lock. A separate SSE-AES256-protected
recovery prefix permits emergency state uploads. SCP restrictions still apply.

## Execute ordered cleanup

Only after role preparation succeeds, verify the private runner is online.
Enable the cleanup workflow if disabled. Then explicitly run:

```powershell
gh workflow enable cleanup.yml --repo yuvalnissim/sentinel-split-architecture
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode Teardown
```

**Teardown deletes the two application environments and their ECR images.**
The helper assumes the separate role for one hour, writes its three credentials
and exact expiration to the bootstrap environment, and dispatches cleanup with
`DESTROY-SENTINEL`. Terraform plan/apply execute in Actions only.

Cleanup keeps the existing order:

1. Verify account, credentials and at least 55 minutes of remaining lifetime.
2. Use the private runner EC2 role to delete both Ingress resources, wait for
   controller cleanup, and remove the application Deployments and Services.
3. Check load balancers and target groups are gone; clean validated controller
   rule references and backend security groups.
4. Plan destruction, reject any managed-resource creation/update/replacement,
   require at least 45 minutes of credential lifetime, and apply the saved plan.
5. Verify Terraform state is empty.

The infrastructure job has a 45-minute budget. Apply receives an interrupt
after 35 minutes and up to 120 seconds to stop, reserving time to save state
before the one-hour credentials expire. This reduces risk; it does not
promise that a stuck provider will always persist state. If Terraform emits
`errored.tfstate`, cleanup attempts to preserve it in the private recovery
prefix. Do not publish state in a PR, log or artifact.

If workload cleanup, an approval queue or ALB cleanup consumes the session
budget, infrastructure deletion is blocked before apply. Do not fake the
expiration or disable guards. Refresh credentials and review the failed stage
before retrying. After a partial destroy, the original two-cluster inventory
assumptions may no longer hold; do not rerun role bootstrap or force cleanup
without reviewing the remaining state and AWS resources.

This is an incident-scoped permission policy, locally tested but not yet
verified against the live teardown API sequence. On AccessDenied, inspect the
specific action and resource rather than adding wildcard write permissions.

## Final closure after destruction

An empty Terraform state alone is not proof of an empty account. Check the two
project VPCs, clusters, NATs, load balancers, target groups, instances and ECR
repositories. Preserve the state bucket until all managed resources are gone.

The state bucket and the two separately bootstrapped IAM roles are outside the
root state. Remove the completion and teardown inline policies/roles using an
authorized bootstrap identity after recording deletion evidence. Remove the
GitHub runner registration, disable mutating workflows, and remove bootstrap
secrets and the expiration variable. Delete all state bucket versions and
delete markers only after final inventory verification. Existing unrelated
account resources are outside the project's cleanup scope.

## Finish the two remaining unassociated EIPs (17 November incident)

The first destroy removed both VPCs and NAT gateways, but failed while trying
to disassociate the NAT EIPs using association IDs captured before NAT removal.
Subsequent live inventory showed both addresses unassociated; remote state
contained only the two managed aws_eip objects. Do not rerun the full workflow
or bootstrap the teardown role again: their cluster/VPC prerequisites no
longer exist.

The manual **Finish remaining EIP teardown** workflow uses the existing teardown
role's ReleaseAddress permission. It verifies the exact two managed bindings
and unassociated AWS addresses, refreshes during plan, and rejects any other
managed action or any remaining association in the refreshed plan. No new
DisassociateAddress permission is added. A successful run verifies both
allocations are gone and managed state is empty.

After merging the targeted recovery and reviewing its guards, use local
PowerShell to refresh credentials and dispatch it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode FinishEips
```

This mode releases only eipalloc-025f4933c6b09de75 and
eipalloc-0565f9a2884255c73 through Terraform in Actions. State storage,
bootstrap IAM roles and GitHub runner registration still need final closure.
