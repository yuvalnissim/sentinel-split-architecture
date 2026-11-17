# Completing the recovered environment with a one-hour session

This is an incident-specific bridge for the environment recovered on 2026-11-16.
It is not the general recreation or teardown identity.

`aws login` refreshes local credentials every 15 minutes. Exporting its three
credential values to Actions secrets does not transfer automatic refresh.
Instead, an operator uses their authenticated local CLI to assume the dedicated
`sentinel-terraform-deployer` role for 3600 seconds. Role chaining is limited to
one hour. Terraform plan and apply still execute only in GitHub Actions.

## Bootstrap the role

Merge the workflow and scripts into main. Leave Terraform deploy disabled.
From the repository root in Windows PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode BootstrapRole
```

This opens AWS login, checks the account and source role, updates the bootstrap
secrets, and dispatches **Bootstrap completion deploy role**. It uses short-lived
bootstrap credentials for a short job. ExecutionPolicy Bypass applies only to
this PowerShell process; it does not change AWS permissions or account policies.

The workflow creates only `sentinel-terraform-deployer`, trusts only the existing
`AccountFullAccessRole`, and installs one project-specific inline policy.
It refuses to overwrite an existing role with unexpected trust, ownership tags,
or additional policies. If an organization policy denies creation, attaching
permissions, or assumption, stop and report that denial. Do not change the
source role, create an OIDC provider, or substitute AdministratorAccess.

## Complete deployment

Review the bootstrap run and its policy before proceeding. Enable only Terraform
deploy when ready to perform infrastructure changes. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode Deploy
```

The helper requests a new one-hour role session, writes all three secrets and
the expiration from that same session, and immediately dispatches Terraform
deploy with both bootstrap flags enabled. It does not print credentials.
If dispatch waits for an environment approval or runner for several minutes,
the workflow lifetime guard may reject the credentials; resolve the delay and
request a new session. Never alter the expiration to bypass the guard.

The existing deployment timeout is 45 minutes. Its initial guard requires 55
minutes remaining, and its pre-apply guard requires 45 minutes remaining.
A one-hour session supports that budget only if dispatch and setup are prompt.
If AWS provisioning takes longer, stop and inspect the state rather than
repeatedly applying with expired credentials.

## Permission boundaries and limitations

The role can read project IAM/EKS/ECR configuration, regional EC2 inventory,
and the public AMI parameter. It can read/write the exact Terraform state and
lock objects, list their prefix, and delete only the lock object.

Mutation permissions cover additions from the reviewed recovery plan:

- EKS node groups, add-ons, access entries, access-policy associations, Pod
  Identity associations, and tags, within the two named clusters.
- Passing only the existing six node/CNI/controller roles to EKS/Pod Identity.
- Reading the exact existing EKS Nodegroup service-linked role with `iam:GetRole`,
  without permission to create, change, or pass that AWS-managed role.
- Adding rules to the two cluster security groups and the backend ALB group,
  whose IDs are discovered and validated during bootstrap. Tagged creation also
  authorizes the new regional rule resource with the project request tag; the
  separate parent-group authorization remains limited to those three groups.
- Updating inline policies on the existing private runner role, as required for
  its missing cluster-discovery policy. IAM scopes this permission to the role,
  not to an individual inline-policy name; this is a documented trust boundary.
- Reconciling only the two imported root-volume tags shown in the recovery plan.

It cannot create/delete clusters, provision VPCs, create IAM roles, modify its
own trust/permissions, or perform general teardown. Access-entry management and
runner-policy updates are security-sensitive and deliberately restricted to the
existing project resources; this is an operator role, not an untrusted PR role.
Account SCPs continue to apply. Permission sufficiency has not yet been tested
against the live AWS APIs. Stop on AccessDenied and review the exact missing
action rather than adding wildcard write permissions.

After successful completion, verify CNI Pod Identity before removing temporary
node CNI permissions. The completion role also supports two narrowly scoped cleanup stages after
re-running BootstrapRole to discover the existing installer access-entry ARNs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode RemoveCniBootstrap
```

Wait for success, then restart aws-node and verify ready nodes, new Pods and the
public-to-private request path. Only after those checks pass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\Start-SentinelDeployment.ps1 -Mode RemoveInstallerAccess
```

Stage one detaches only AmazonEKS_CNI_Policy from the two exact node roles.
Stage two removes only the discovered installer access entries and their policy
associations, the exact installer IAM role, and its inline assume-role link on
the runner. IAM cannot restrict DeleteRolePolicy to one inline-policy name;
this permission is scoped to the runner role and is used by reviewed Terraform.
Do not use Deploy mode after these cleanup stages: it re-enables both temporary
flags. Other infrastructure destruction remains outside this role's scope.
The role is bootstrapped outside the root Terraform state, like state storage.
At the end of the exercise, delete its inline policy and role through a reviewed
Actions cleanup step using the bootstrap identity, and delete the bootstrap
secrets and expiration variable. Do not delete root Terraform state prematurely.

For destruction of the recreated environment, use the separate
[scoped teardown session guide](teardown-session.md). The completion role
remains insufficient for general teardown.
