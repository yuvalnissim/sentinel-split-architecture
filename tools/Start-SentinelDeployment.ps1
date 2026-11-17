param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("BootstrapRole", "Deploy", "RemoveCniBootstrap", "RemoveInstallerAccess", "BootstrapTeardown", "Teardown", "FinishEips")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
$sentinelRepo = "yuvalnissim/sentinel-split-architecture"
$sentinelRoleArn = "arn:aws:iam::485378272094:role/sentinel-terraform-deployer"
if ($Mode -in @("Teardown", "FinishEips")) {
    $sentinelRoleArn = "arn:aws:iam::485378272094:role/sentinel-terraform-teardown"
}

# Authenticate locally; all infrastructure changes run inside GitHub Actions.
aws login --profile aws-lab
if ($LASTEXITCODE -ne 0) { throw "AWS login failed" }

$sentinelIdentityJson = aws sts get-caller-identity --profile aws-lab --output json --no-cli-pager
if ($LASTEXITCODE -ne 0) { throw "Could not verify AWS identity" }
$sentinelIdentity = $sentinelIdentityJson | ConvertFrom-Json
if ($sentinelIdentity.Account -ne "485378272094" -or
    $sentinelIdentity.Arn -notlike "arn:aws:sts::485378272094:assumed-role/AccountFullAccessRole/*") {
    throw "Unexpected bootstrap account or role"
}

if ($Mode -in @("BootstrapRole", "BootstrapTeardown")) {
    $sentinelSessionJson = aws configure export-credentials --profile aws-lab --format process
    if ($LASTEXITCODE -ne 0) { throw "Could not export bootstrap session" }
    $sentinelSession = $sentinelSessionJson | ConvertFrom-Json
    $sentinelMinimumSeconds = 600
} else {
    $sentinelSessionJson = aws sts assume-role --profile aws-lab `
        --role-arn $sentinelRoleArn `
        --role-session-name sentinel-github-deploy `
        --duration-seconds 3600 --output json --no-cli-pager
    if ($LASTEXITCODE -ne 0) { throw "AssumeRole failed; do not dispatch deploy" }
    $sentinelSession = ($sentinelSessionJson | ConvertFrom-Json).Credentials
    $sentinelMinimumSeconds = 3500
}

if (!$sentinelSession.AccessKeyId -or !$sentinelSession.SecretAccessKey -or !$sentinelSession.SessionToken) {
    throw "Incomplete AWS session"
}
$sentinelExpiry = [DateTimeOffset]::Parse($sentinelSession.Expiration)
if (($sentinelExpiry - [DateTimeOffset]::UtcNow).TotalSeconds -lt $sentinelMinimumSeconds) {
    throw "Insufficient session lifetime; authenticate again before dispatch"
}

$sentinelSecrets = @{
    AWS_ACCESS_KEY_ID = $sentinelSession.AccessKeyId
    AWS_SECRET_ACCESS_KEY = $sentinelSession.SecretAccessKey
    AWS_SESSION_TOKEN = $sentinelSession.SessionToken
}
foreach ($sentinelName in $sentinelSecrets.Keys) {
    $sentinelSecrets[$sentinelName] | gh secret set $sentinelName --env bootstrap --repo $sentinelRepo
    if ($LASTEXITCODE -ne 0) { throw "Failed to update $sentinelName; do not dispatch" }
}
gh variable set AWS_CREDENTIAL_EXPIRATION --env bootstrap --repo $sentinelRepo `
    --body ($sentinelExpiry.ToString("o"))
if ($LASTEXITCODE -ne 0) { throw "Failed to update session expiration; do not dispatch" }

if ($Mode -eq "BootstrapRole") {
    gh workflow run bootstrap-deploy-session.yml --repo $sentinelRepo --ref main `
        -f confirmation=CREATE-SENTINEL-DEPLOY-ROLE
} elseif ($Mode -eq "BootstrapTeardown") {
    gh workflow run bootstrap-teardown-session.yml --repo $sentinelRepo --ref main `
        -f confirmation=PREPARE-SENTINEL-TEARDOWN
} elseif ($Mode -eq "FinishEips") {
    gh workflow run finish-eip-teardown.yml --repo $sentinelRepo --ref main `
        -f confirmation=RELEASE-SENTINEL-EIPS
} elseif ($Mode -eq "Teardown") {
    gh workflow run cleanup.yml --repo $sentinelRepo --ref main `
        -f confirmation=DESTROY-SENTINEL
} else {
    $sentinelCniFlag = "true"
    $sentinelControllerFlag = "true"
    if ($Mode -in @("RemoveCniBootstrap", "RemoveInstallerAccess")) {
        $sentinelCniFlag = "false"
    }
    if ($Mode -eq "RemoveInstallerAccess") {
        $sentinelControllerFlag = "false"
    }
    gh workflow run terraform-plan.yml --repo $sentinelRepo --ref main `
        -f "enable_controller_bootstrap=$sentinelControllerFlag" `
        -f "enable_cni_bootstrap=$sentinelCniFlag"
}
if ($LASTEXITCODE -ne 0) { throw "Workflow dispatch failed" }
Write-Host "Workflow dispatched. Session expiration: $($sentinelExpiry.ToString('o'))"
Remove-Variable sentinelSession, sentinelSessionJson, sentinelSecrets -ErrorAction SilentlyContinue
