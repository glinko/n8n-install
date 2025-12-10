#!/bin/bash

# Improved n8n import script that handles errors better
# This script imports workflows using n8n CLI but continues on errors

set +e  # Don't exit on errors

echo "=========================================="
echo "n8n Workflow Import Script (Improved)"
echo "=========================================="
echo ""

# Check if RUN_N8N_IMPORT is set to true
if [ "$RUN_N8N_IMPORT" != "true" ]; then
  echo 'Skipping n8n import based on RUN_N8N_IMPORT environment variable.'
  exit 0
fi

# Import credentials first
echo "Step 1: Importing credentials..."
CRED_COUNT=0
CRED_SUCCESS=0
CRED_FAILED=0

if [ -d "/backup/credentials" ]; then
  for cred_file in /backup/credentials/*.json; do
    if [ -f "$cred_file" ]; then
      CRED_COUNT=$((CRED_COUNT + 1))
      echo "  Importing: $(basename "$cred_file")"
      if n8n import:credentials --input="$cred_file" 2>&1; then
        CRED_SUCCESS=$((CRED_SUCCESS + 1))
        echo "    ✓ Success"
      else
        CRED_FAILED=$((CRED_FAILED + 1))
        echo "    ✗ Failed (continuing...)"
      fi
    fi
  done
  echo "Credentials: $CRED_SUCCESS/$CRED_COUNT imported successfully"
else
  echo "  No credentials directory found, skipping..."
fi

echo ""
echo "Step 2: Importing workflows..."
WORKFLOW_COUNT=0
WORKFLOW_SUCCESS=0
WORKFLOW_FAILED=0

if [ -d "/backup/workflows" ]; then
  # Count total workflows first
  TOTAL_WORKFLOWS=$(find /backup/workflows -maxdepth 1 -type f -name "*.json" | wc -l)
  echo "  Found $TOTAL_WORKFLOWS workflow files"
  echo ""
  
  # Import each workflow
  for workflow_file in /backup/workflows/*.json; do
    if [ -f "$workflow_file" ]; then
      WORKFLOW_COUNT=$((WORKFLOW_COUNT + 1))
      filename=$(basename "$workflow_file")
      echo "[$WORKFLOW_COUNT/$TOTAL_WORKFLOWS] Importing: $filename"
      
      # Try to import with error handling
      if n8n import:workflow --input="$workflow_file" 2>&1 | grep -v "Could not find workflow" | grep -v "null value in column" > /dev/null 2>&1; then
        WORKFLOW_SUCCESS=$((WORKFLOW_SUCCESS + 1))
        echo "    ✓ Success"
      else
        # Even if there are warnings, check if workflow was imported
        # Try a different approach - import with --skip-credentials flag
        if n8n import:workflow --input="$workflow_file" --skip-credentials 2>&1 | grep -v "Could not find workflow" | grep -v "null value in column" > /dev/null 2>&1; then
          WORKFLOW_SUCCESS=$((WORKFLOW_SUCCESS + 1))
          echo "    ✓ Success (with skip-credentials)"
        else
          WORKFLOW_FAILED=$((WORKFLOW_FAILED + 1))
          echo "    ✗ Failed (continuing...)"
        fi
      fi
      
      # Show progress every 10 workflows
      if [ $((WORKFLOW_COUNT % 10)) -eq 0 ]; then
        echo ""
        echo "  Progress: $WORKFLOW_COUNT/$TOTAL_WORKFLOWS workflows processed"
        echo "  Success: $WORKFLOW_SUCCESS, Failed: $WORKFLOW_FAILED"
        echo ""
      fi
    fi
  done
else
  echo "  No workflows directory found, skipping..."
fi

echo ""
echo "=========================================="
echo "Import Summary:"
echo "=========================================="
echo "Credentials: $CRED_SUCCESS/$CRED_COUNT imported"
echo "Workflows: $WORKFLOW_SUCCESS/$WORKFLOW_COUNT imported"
echo "Failed: $WORKFLOW_FAILED workflows"
echo ""
echo "Import process finished."
echo ""

# Exit with success even if some workflows failed
exit 0

