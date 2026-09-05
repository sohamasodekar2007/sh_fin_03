param(
  [string]$DemoName = "cloudcare-demo"
)

$ErrorActionPreference = "Stop"

function Import-DotEnvValue {
  param([string]$Key)
  $line = Get-Content ".env" | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
  if (-not $line) { return $null }
  return (($line -split "=", 2)[1]).Trim()
}

function AwsJson {
  param([string[]]$Arguments)
  $output = & aws @Arguments --output json
  if ($LASTEXITCODE -ne 0) {
    throw "aws $($Arguments -join ' ') failed"
  }
  if ([string]::IsNullOrWhiteSpace($output)) { return $null }
  return $output | ConvertFrom-Json
}

function AwsText {
  param([string[]]$Arguments)
  $output = & aws @Arguments --output text
  if ($LASTEXITCODE -ne 0) {
    throw "aws $($Arguments -join ' ') failed"
  }
  return "$output".Trim()
}

$env:AWS_ACCESS_KEY_ID = Import-DotEnvValue "AWS_ACCESS_KEY_ID"
$env:AWS_SECRET_ACCESS_KEY = Import-DotEnvValue "AWS_SECRET_ACCESS_KEY"
$env:AWS_REGION = Import-DotEnvValue "AWS_REGION"
$env:AWS_DEFAULT_REGION = $env:AWS_REGION

if (-not $env:AWS_ACCESS_KEY_ID -or -not $env:AWS_SECRET_ACCESS_KEY -or -not $env:AWS_REGION) {
  throw "Missing AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, or AWS_REGION in .env"
}

function DemoTagsJson {
  param([string]$Name = "")
  $items = @(
    @{ Key = "CloudCareDemo"; Value = "true" },
    @{ Key = "Environment"; Value = "development" },
    @{ Key = "Owner"; Value = "cloudcare" }
  )
  if ($Name) {
    $items += @{ Key = "Name"; Value = $Name }
  }
  return ($items | ConvertTo-Json -Compress)
}

function DemoTagsFile {
  param([string]$Name = "")
  $safeName = if ($Name) { $Name } else { "base" }
  $path = Join-Path $env:TEMP "$DemoName-tags-$safeName.json"
  DemoTagsJson $Name | Set-Content -Encoding ASCII $path
  return "file://$path"
}

function Ec2TagArgs {
  param([string]$Name)
  return @(
    "Key=CloudCareDemo,Value=true",
    "Key=Environment,Value=development",
    "Key=Owner,Value=cloudcare",
    "Key=Name,Value=$Name"
  )
}
$statePath = ".cloudcare-demo-resources.json"
$credentialPath = ".cloudcare-demo-rds-credentials.json"

$identity = AwsJson @("sts", "get-caller-identity")
$azs = AwsJson @("ec2", "describe-availability-zones", "--filters", "Name=state,Values=available", "--query", "AvailabilityZones[0:2].ZoneName")
if ($azs.Count -lt 2) {
  throw "Need at least two availability zones for an RDS DB subnet group."
}

$vpcId = AwsText @("ec2", "describe-vpcs", "--filters", "Name=tag:Name,Values=$DemoName-vpc", "Name=tag:CloudCareDemo,Values=true", "--query", "Vpcs[0].VpcId")
if ($vpcId -eq "None" -or -not $vpcId) {
  $vpc = AwsJson @("ec2", "create-vpc", "--cidr-block", "10.44.0.0/16", "--tag-specifications", "ResourceType=vpc,Tags=[{Key=Name,Value=$DemoName-vpc},{Key=CloudCareDemo,Value=true},{Key=Environment,Value=development},{Key=Owner,Value=cloudcare}]")
  $vpcId = $vpc.Vpc.VpcId
  & aws ec2 modify-vpc-attribute --vpc-id $vpcId --enable-dns-hostnames | Out-Null
  & aws ec2 modify-vpc-attribute --vpc-id $vpcId --enable-dns-support | Out-Null
}

$subnetAId = AwsText @("ec2", "describe-subnets", "--filters", "Name=tag:Name,Values=$DemoName-subnet-a", "Name=vpc-id,Values=$vpcId", "--query", "Subnets[0].SubnetId")
if ($subnetAId -eq "None" -or -not $subnetAId) {
  $subnetA = AwsJson @("ec2", "create-subnet", "--vpc-id", $vpcId, "--cidr-block", "10.44.1.0/24", "--availability-zone", $azs[0], "--tag-specifications", "ResourceType=subnet,Tags=[{Key=Name,Value=$DemoName-subnet-a},{Key=CloudCareDemo,Value=true},{Key=Environment,Value=development},{Key=Owner,Value=cloudcare}]")
  $subnetAId = $subnetA.Subnet.SubnetId
}

$subnetBId = AwsText @("ec2", "describe-subnets", "--filters", "Name=tag:Name,Values=$DemoName-subnet-b", "Name=vpc-id,Values=$vpcId", "--query", "Subnets[0].SubnetId")
if ($subnetBId -eq "None" -or -not $subnetBId) {
  $subnetB = AwsJson @("ec2", "create-subnet", "--vpc-id", $vpcId, "--cidr-block", "10.44.2.0/24", "--availability-zone", $azs[1], "--tag-specifications", "ResourceType=subnet,Tags=[{Key=Name,Value=$DemoName-subnet-b},{Key=CloudCareDemo,Value=true},{Key=Environment,Value=development},{Key=Owner,Value=cloudcare}]")
  $subnetBId = $subnetB.Subnet.SubnetId
}

$sgId = AwsText @("ec2", "describe-security-groups", "--filters", "Name=group-name,Values=$DemoName-rds-sg", "Name=vpc-id,Values=$vpcId", "--query", "SecurityGroups[0].GroupId")
if ($sgId -eq "None" -or -not $sgId) {
  $sgId = AwsText @("ec2", "create-security-group", "--group-name", "$DemoName-rds-sg", "--description", "CloudCare demo RDS security group with no public ingress", "--vpc-id", $vpcId, "--query", "GroupId")
  & aws ec2 create-tags --resources $sgId --tags (Ec2TagArgs "$DemoName-rds-sg") | Out-Null
}

$tableName = "$DemoName-orders"
try {
  AwsJson @("dynamodb", "describe-table", "--table-name", $tableName) | Out-Null
} catch {
  AwsJson @("dynamodb", "create-table", "--table-name", $tableName, "--billing-mode", "PAY_PER_REQUEST", "--attribute-definitions", "AttributeName=pk,AttributeType=S", "AttributeName=sk,AttributeType=S", "--key-schema", "AttributeName=pk,KeyType=HASH", "AttributeName=sk,KeyType=RANGE", "--tags", (DemoTagsFile $tableName)) | Out-Null
  & aws dynamodb wait table-exists --table-name $tableName
}
$sampleItemPath = Join-Path $env:TEMP "$DemoName-dynamodb-item.json"
'{"pk":{"S":"merchant#alpha"},"sk":{"S":"order#demo-001"},"amount":{"N":"1499"},"currency":{"S":"USD"},"cloudcare_demo":{"BOOL":true}}' | Set-Content -Encoding ASCII $sampleItemPath
AwsJson @("dynamodb", "put-item", "--table-name", $tableName, "--item", "file://$sampleItemPath") | Out-Null

$roleName = "$DemoName-lambda-role"
$roleArn = $null
try {
  $role = AwsJson @("iam", "get-role", "--role-name", $roleName)
  $roleArn = $role.Role.Arn
} catch {
  $trustPath = Join-Path $env:TEMP "$DemoName-lambda-trust.json"
  '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' | Set-Content -Encoding ASCII $trustPath
  $role = AwsJson @("iam", "create-role", "--role-name", $roleName, "--assume-role-policy-document", "file://$trustPath", "--tags", (DemoTagsFile))
  $roleArn = $role.Role.Arn
  & aws iam attach-role-policy --role-name $roleName --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole | Out-Null
  Start-Sleep -Seconds 12
}

$functionName = "$DemoName-optimizer-sample"
try {
  AwsJson @("lambda", "get-function", "--function-name", $functionName) | Out-Null
} catch {
  $lambdaDir = Join-Path $env:TEMP "$DemoName-lambda"
  $zipPath = Join-Path $env:TEMP "$DemoName-lambda.zip"
  New-Item -ItemType Directory -Force -Path $lambdaDir | Out-Null
  @'
import json
import os
from datetime import datetime, timezone

def handler(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "CloudCare demo Lambda is alive",
            "table": os.environ.get("DEMO_TABLE_NAME"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    }
'@ | Set-Content -Encoding ASCII (Join-Path $lambdaDir "index.py")
  if (Test-Path $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
  Compress-Archive -Path (Join-Path $lambdaDir "index.py") -DestinationPath $zipPath
  AwsJson @("lambda", "create-function", "--function-name", $functionName, "--runtime", "python3.12", "--handler", "index.handler", "--role", $roleArn, "--zip-file", "fileb://$zipPath", "--timeout", "10", "--memory-size", "128", "--environment", "Variables={CLOUDCARE_DEMO=true,DEMO_TABLE_NAME=$tableName}", "--tags", "CloudCareDemo=true,Environment=development,Owner=cloudcare,Name=$functionName") | Out-Null
}

$invokeOut = Join-Path $env:TEMP "$DemoName-lambda-response.json"
& aws lambda wait function-active --function-name $functionName
AwsJson @("lambda", "invoke", "--function-name", $functionName, $invokeOut) | Out-Null

$subnetGroupName = "$DemoName-db-subnets"
try {
  AwsJson @("rds", "describe-db-subnet-groups", "--db-subnet-group-name", $subnetGroupName) | Out-Null
} catch {
  AwsJson @("rds", "create-db-subnet-group", "--db-subnet-group-name", $subnetGroupName, "--db-subnet-group-description", "CloudCare demo private DB subnet group", "--subnet-ids", $subnetAId, $subnetBId, "--tags", (DemoTagsFile $subnetGroupName)) | Out-Null
}

$dbIdentifier = "$DemoName-postgres"
$dbPassword = $null
if (Test-Path $credentialPath) {
  $dbPassword = (Get-Content -Raw $credentialPath | ConvertFrom-Json).rds_password
}
if (-not $dbPassword) {
  $dbPassword = -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
}

try {
  AwsJson @("rds", "describe-db-instances", "--db-instance-identifier", $dbIdentifier) | Out-Null
} catch {
  AwsJson @("rds", "create-db-instance", "--db-instance-identifier", $dbIdentifier, "--engine", "postgres", "--db-instance-class", "db.t4g.micro", "--allocated-storage", "20", "--storage-type", "gp3", "--master-username", "cloudcare_admin", "--master-user-password", $dbPassword, "--db-subnet-group-name", $subnetGroupName, "--vpc-security-group-ids", $sgId, "--no-publicly-accessible", "--no-multi-az", "--backup-retention-period", "0", "--auto-minor-version-upgrade", "--no-deletion-protection", "--tags", (DemoTagsFile $dbIdentifier)) | Out-Null
}

$db = AwsJson @("rds", "describe-db-instances", "--db-instance-identifier", $dbIdentifier, "--query", "DBInstances[0]")

$state = [ordered]@{
  created_by = $identity.Arn
  region = $env:AWS_REGION
  tag = "CloudCareDemo=true"
  vpc_id = $vpcId
  subnet_ids = @($subnetAId, $subnetBId)
  security_group_id = $sgId
  dynamodb_table = $tableName
  lambda_function = $functionName
  lambda_role = $roleName
  rds_instance = $dbIdentifier
  rds_status = $db.DBInstanceStatus
  rds_endpoint = $db.Endpoint.Address
}
$state | ConvertTo-Json | Set-Content -Encoding UTF8 $statePath

$credentials = [ordered]@{
  region = $env:AWS_REGION
  rds_identifier = $dbIdentifier
  rds_username = "cloudcare_admin"
  rds_password = $dbPassword
  rds_endpoint = $db.Endpoint.Address
  note = "RDS is private inside $vpcId and may not be reachable from your laptop without network access into the VPC."
}
$credentials | ConvertTo-Json | Set-Content -Encoding UTF8 $credentialPath

$state | ConvertTo-Json
