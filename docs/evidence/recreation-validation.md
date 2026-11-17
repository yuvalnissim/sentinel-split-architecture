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

This hostname belonged to the recreated environment and is no longer live.
Future recreations must read the new Ingress hostname instead of copying it.

## Final teardown and closure: 17 November

The main ordered teardown stopped at two Elastic IPs. AWS inventory showed
both allocations were unassociated; remote state contained only those two
managed instances. A separate guarded finishing workflow refreshed state and
applied a plan restricted to their deletion. It completed successfully and
verified zero managed state instances and absence of both allocations.

- [Successful EIP finishing run 44070436700](https://github.com/yuvalnissim/sentinel-split-architecture/actions/runs/44070436700)
- Follow-up project cluster query: `[]`.
- Follow-up query for both recreated VPC IDs: `[]`.
- Follow-up query for nonterminated project-tagged EC2 instances: `[]`.
- Both node roles had no attached `AmazonEKS_CNI_Policy`; installer-role lookup returned `NoSuchEntity` before teardown.
- Both temporary deployment/teardown roles and their inline policies were deleted successfully.
- GitHub bootstrap secrets and `AWS_CREDENTIAL_EXPIRATION` were deleted successfully.
- The remaining offline runner registration was identified; the operator subsequently confirmed its deletion and state-bucket cleanup, including versions.
- Terraform, backend, gateway and controller deployment workflows are disabled. Static validation is retained.

The state bucket was deleted only after infrastructure cleanup and empty-state
verification. State and credentials are not committed as evidence. The project
endpoint is no longer available. These checks do not constitute an account-wide
resource inventory or a final billing reconciliation.

## Validation limits

- Recreation completed after recovery and fixes; unattended first-pass
  recreation has not been demonstrated.
- This validation did not repeat the original direct-backend negative tests
  from the local client and runner. Historical failures are separate evidence.
- No load or controlled AZ-failure tests were performed.
- The node-role policy and installer-role checks supplement workflow results;
  a comprehensive audit of all Kubernetes access entries was not recorded.
