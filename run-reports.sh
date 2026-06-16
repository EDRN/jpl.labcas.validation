#!/bin/sh
#
# Run Lung_Team_Project_2 and Prostate_MRI through the validation pipeline
# and save the reports to the reports directory
#
# And all the other reports we're interested in

# Use a /tmp with a lot of space
TMPDIR=/labcas-data/tmp/validation
export TMPDIR
mkdir --parents $TMPDIR

# The base directory for the LabCAS archived data for EDRN
base=/labcas-data/labcas-backend/archive/edrn

# Where is Solr in all this?
solr=https://localhost:8984/solr/

# Sites for Lung_Team_Project_2
Lung_Team_Project_2="Images_Site_AvinPOWpghrek Images_Site_ldytNSGnHnrBQ Images_Site_NVRiRYzqspbvMw Images_Site_UB5yhu2StyPSLQ Images_Site_weRc6TUHvOru6A Images_Site_YGaeI0aN9IAeRA LTP2-Site6 LTP2-Site7"

# Sites for Prostate_MRI
Prostate_MRI="Images_Site_baiIJNZ2MBqvw Images_Site_c41ux70b3h6cow Images_Site_ElkuApuKkJXw2A Images_Site_ER13y8kBMpUKA Images_Site_kMBCjAelMw4Dw Images_Site_qfP7OH9pjawWGA Images_Site_rvIOs4uv8Rbfng Images_Site_uDUsCV9ikmtw Images_Site_x4xa7dK1fGEV8g PMRI-Site10"

# Sites for PDAC
PDAC="BCM UPMC"

# Clean temporary files from Python multiprocessing and Tesseract from any previous runs
clean_tmp() {
    rm -rf $TMPDIR/pymp-*
    rm -f $TMPDIR/tess_*
}
clean_tmp

# Create the reports directory
mkdir --parents reports

# Marker
date 1>&2

# The two sites of PDAC
echo "Running PDAC" 1>&2
for site in $PDAC; do
    echo "Running PDAC $site" 1>&2
    .venv/bin/validate-dicom-files --new-data --output reports/Pre-diagnostic_PDAC_Images \
        --site-id $site $base/Pre-diagnostic_PDAC_Images/$site
    echo "PDAC $site done" 1>&2
    clean_tmp
done

# Now Lung_Team_Project_2
echo "Running Lung_Team_Project_2" 1>&2
for site in $Lung_Team_Project_2; do
    echo "Running Lung_Team_Project_2 $site" 1>&2
    .venv/bin/validate-dicom-files --url $solr --output reports/Lung_Team_Project_2 \
	--subset $site $base/Lung_Team_Project_2
    echo "Lung_Team_Project_2 $site done" 1>&2
    clean_tmp
done

# Now Prostate_MRI
echo "Running Prostate_MRI" 1>&2
for site in $Prostate_MRI; do
    echo "Running Prostate_MRI $site" 1>&2
    .venv/bin/validate-dicom-files --url $solr --output reports/Prostate_MRI --subset $site $base/Prostate_MRI
    echo "Prostate_MRI $site done" 1>&2
    clean_tmp
done

# Summarize the reports
echo "Summarizing reports" 1>&2
.venv/bin/summarize-validation-reports --output reports/summary.csv reports
echo "All done" 1>&2

# Final cleanup
clean_tmp
date 1>&2

# All done
exit 0
