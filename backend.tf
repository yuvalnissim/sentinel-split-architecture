terraform {
  backend "s3" {
    bucket              = "sentinel-tfstate-485378272094-eu-north-1"
    key                 = "sentinel/terraform.tfstate"
    region              = "eu-north-1"
    encrypt             = true
    use_lockfile        = true
    allowed_account_ids = ["485378272094"]
  }
}