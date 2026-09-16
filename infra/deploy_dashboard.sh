#!/usr/bin/env bash
#
# Deploy the dashboard and print the ready-to-open URL:
#   1. upload intersection_map.html to the dashboard S3 bucket
#   2. invalidate the CloudFront cache for it
#   3. print the wired URL (counts + replay endpoints attached)
#
# Optional first argument --rebuild-names also refreshes the counts dropdown's
# id -> name index (a one-off / occasional step, not needed on every deploy).
#
#   ./infra/deploy_dashboard.sh
#   ./infra/deploy_dashboard.sh --rebuild-names
#
# Runnable from anywhere; it cd's into its own infra/ directory.
set -euo pipefail
cd "$(dirname "$0")"

html="../smart_city_digital_twin/2D_simulation/scripts/intersection_map.html"
[[ -f "$html" ]] || { echo "dashboard not found: $html" >&2; exit 1; }

# --- optional: refresh the intersection id -> name index --------------------
if [[ "${1:-}" == "--rebuild-names" ]]; then
  fn=$(aws lambda list-functions \
        --query "Functions[?ends_with(FunctionName, '-etl-traffic-counts')].FunctionName | [0]" \
        --output text)
  if [[ -z "$fn" || "$fn" == "None" ]]; then
    echo "could not find the etl-traffic-counts function; skipping name rebuild" >&2
  else
    echo "rebuilding intersection names via $fn ..."
    aws lambda invoke --cli-read-timeout 360 --function-name "$fn" \
      --payload '{"rebuild_names": true}' --cli-binary-format raw-in-base64-out /dev/stdout
    echo
  fi
fi

# --- upload + invalidate -----------------------------------------------------
bucket=$(terraform output -raw dashboard_bucket_name)
domain=$(terraform output -raw dashboard_url | sed 's#https://##')

echo "uploading intersection_map.html -> s3://$bucket/ ..."
aws s3 cp "$html" "s3://$bucket/intersection_map.html" --content-type "text/html"

dist=$(aws cloudfront list-distributions \
        --query "DistributionList.Items[?DomainName=='$domain'].Id | [0]" --output text)
echo "invalidating CloudFront ($dist) ..."
inv=$(aws cloudfront create-invalidation --distribution-id "$dist" \
        --paths "/intersection_map.html" --query "Invalidation.Id" --output text)
echo "invalidation $inv started (usually completes in ~1-2 min)"

# --- the URL to open ---------------------------------------------------------
counts=$(terraform output -raw counts_api_url)
replay=$(terraform output -raw replay_api_url)
echo
echo "open once the invalidation completes:"
printf 'https://%s/intersection_map.html?counts=%s&replay=%s\n' "$domain" "$counts" "$replay"
