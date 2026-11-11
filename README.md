# Serverless CSV Data Pipeline on AWS (Terraform)

Drop a CSV file into S3 and it is validated, loaded into a database, and summarized by email, with no servers to manage. All infrastructure is written in **Terraform**.

```
                     ┌──────────────┐    ┌───────────────────────────┐
 CSV upload ───────► │  S3 bucket   │───►│  Lambda (Python 3.12)     │
 incoming/*.csv      │  incoming/   │    │  validate → save → move   │
                     │  processed/  │◄───┤                           │
                     │  failed/     │    └───────┬─────────────┬─────┘
                     └──────────────┘            │             │
                                                 ▼             ▼
                                          DynamoDB table   SNS topic ──► your email
                                          (valid orders)   (summary)
```

## How it works

1. You upload an orders CSV to `incoming/` in the bucket.
2. S3 triggers the Lambda function.
3. The function checks every row. Valid rows are saved to DynamoDB, and bad rows are counted and described.
4. The file moves to `processed/`. A file with missing columns or unreadable text moves to `failed/` instead.
5. An email summary is sent, such as "Rows saved: 4, Rows skipped: 2", with the first few problems listed.

Expected CSV columns: `order_id`, `customer`, `amount` (greater than 0), `order_date` (`YYYY-MM-DD`). See `sample-data/`.

## Project structure

```
.
├── main.tf                  # S3, DynamoDB, SNS, Lambda and the S3 trigger
├── iam.tf                   # Least-privilege role for the Lambda function
├── variables.tf
├── outputs.tf
├── versions.tf              # Terraform and provider versions
├── lambda/handler.py        # The processing code
├── tests/                   # pytest + moto (mocked AWS)
├── sample-data/             # Example CSVs to try it out
└── .github/workflows/ci.yml # Runs tests and Terraform checks
```

## Prerequisites

- An AWS account with the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) configured (`aws configure`)
- [Terraform](https://developer.hashicorp.com/terraform/install) 1.6 or newer
- Python 3.12 (only needed to run the tests)

## Run the tests

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Deploy

```bash
cp terraform.tfvars.example terraform.tfvars   # set your email and region
terraform init
terraform plan
terraform apply
```

If you set `alert_email`, AWS sends a confirmation email. **Click the link in it**, or no summaries will arrive.

After the first `terraform init`, commit the generated `.terraform.lock.hcl` file so everyone uses the same provider versions.

## Try it

```bash
BUCKET=$(terraform output -raw bucket_name)
TABLE=$(terraform output -raw table_name)

aws s3 cp sample-data/orders.csv "s3://$BUCKET/incoming/"
aws s3 cp sample-data/orders_with_errors.csv "s3://$BUCKET/incoming/"

aws dynamodb scan --table-name "$TABLE" --query "Items[].[order_id.S,customer.S,amount.N]" --output table
aws s3 ls "s3://$BUCKET/processed/"
aws logs tail "/aws/lambda/csv-pipeline-processor" --since 10m   # if you changed project_name, use that prefix
```

## CI

`.github/workflows/ci.yml` runs the unit tests and checks the Terraform code (`fmt`, `validate`) on every push and pull request. It does not deploy.

## Next steps

- Store Terraform state remotely (S3 backend with locking) before deploying from CI or sharing the project.
- Add a dead-letter queue to the Lambda function for unexpected failures.
- Add a lifecycle rule to delete old files in `processed/`.

## Clean up

```bash
terraform destroy
```

## Cost

All services are pay-per-use, so an idle pipeline costs close to nothing.

## License

MIT
