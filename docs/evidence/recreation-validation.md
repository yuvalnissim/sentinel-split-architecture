# Recreation validation: 16-17 November 2026

This record summarizes the workflow results and terminal outputs observed
during recreation. Existing PNGs in this directory describe the original lab;
they were not replaced or relabeled as new evidence. No state or credentials
are included in this record.

## Scope and recovery

The original environment and state bucket had been deleted on 12 November.
A new provisioning attempt began on 16 November. Exported `aws login`
credentials expired during apply, leaving resources missing from remote state.
The manual recovery workflow verified AWS inventory, backed up the state,
imported missing bindings, and generated a review-only plan.

The provider's imported default for the creation-only EKS bootstrap-admin field
caused planned cluster replacement. A narrowly scoped lifecycle exception
removed that imported-field difference; new clusters still request false.
Existing creator access is not proven absent by that exception or by the
DescribeCluster response. A separate access-entry audit remains appropriate.

Recovery confirmed zero missing incident bindings and a plan with no deletion
or replacement. The full deployment subsequently passed using the dedicated
completion role and a one-hour assumed-role session. Its policy and trust were
corrected for the source IAM role's `/managed/` path, tagged network-rule
creation and read-only access to the existing Nodegroup service-linked role.
The account SCP was not changed.

## Observed checks

| Check | Observed result |
|---|---|
| Terraform deployment | Successful Actions run, Terraform deploy #28 |
| Private runner | Registered; runner identity check passed |
| Tooling and Docker | Installation workflows passed |
| Load balancer controllers | Installation workflow passed in both clusters |
| Backend application | Build-and-deploy workflow passed |
| Gateway application | Build-and-deploy workflow passed |
| CNI credential delivery | Diagnostic Pods using aws-node received each dedicated CNI role, with EC2 metadata fallback disabled |
| Node CNI fallback removal | Terraform workflow passed |
| aws-node after removal | Restart and rollout passed in both clusters |
| Node readiness | All four nodes Ready |
| New application Pods | Both Deployments restarted and rolled out successfully after fallback removal |
| Installer access removal | Terraform workflow passed |
| Final external request | Returned `Hello from backend` after installer removal |

Dedicated identities observed:

- `sentinel-eks-gateway-cni`
- `sentinel-eks-backend-cni`

The public endpoint used for the final check was:

```powershell
curl.exe --fail-with-body --connect-timeout 5 --max-time 20 "http://k8s-default-sentinel-7d2048db35-1015061543.eu-north-1.elb.amazonaws.com/"
```

Response:

```text
Hello from backend
```

This hostname belongs to the recreated environment; future recreations must
read the new Ingress hostname instead of copying it.

## Limits and remaining closure

- Recreation completed after recovery and fixes; unattended first-pass
  recreation has not been demonstrated.
- This validation did not repeat the original direct-backend negative tests
  from the local client and runner. Historical failures are separate evidence.
- No load or controlled AZ-failure tests were performed.
- Successful cleanup workflows are the recorded evidence of permission
  removal; a separate AWS IAM/access-entry inventory audit is not included.
- The environment was active at the final request on 17 November. Teardown of
  this environment has not yet been recorded. The completion role cannot
  perform general teardown; an authorized teardown identity is required.
- Preserve remote state until all managed resources are verified removed.
  The separately bootstrapped completion role, its inline policy and GitHub
  runner registration also require explicit final cleanup.
