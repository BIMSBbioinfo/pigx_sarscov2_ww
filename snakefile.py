# PiGx SARS CoV2 wastewater sequencing pipeline
#
# Copyright © 2021 Akalin lab.
#
# This file is part of the PiGx SARS-CoV2 wastewater sequencing pipeline.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Snakefile for PiGx SARS CoV2 wastewater sequencing pipeline
"""

import os
import csv
import yaml
from itertools import chain
import re

SAMPLE_SHEET_CSV = config['locations']['sample-sheet']
READS_DIR        = config['locations']['reads-dir']
REFERENCE_FASTA  = config['locations']['reference-fasta']
AMPLICONS_BED    = config['locations']['amplicons-bed']
KRAKEN_DB        = config['locations']['kraken-db-dir']
KRONA_DB         = config['locations']['krona-db-dir']
SIGMUT_DB        = config['locations']['sigmut-db-dir']
VEP_DB           = config['locations']['vep-db-dir']
OUTPUT_DIR       = config['locations']['output-dir']

TRIMMED_READS_DIR = os.path.join(OUTPUT_DIR, 'trimmed_reads')
LOG_DIR           = os.path.join(OUTPUT_DIR, 'logs')
FASTQC_DIR        = os.path.join(OUTPUT_DIR, 'fastqc')
MULTIQC_DIR       = os.path.join(OUTPUT_DIR, 'multiqc')
MAPPED_READS_DIR  = os.path.join(OUTPUT_DIR, 'mapped_reads')
VARIANTS_DIR      = os.path.join(OUTPUT_DIR, 'variants')
KRAKEN_DIR        = os.path.join(OUTPUT_DIR, 'kraken')
COVERAGE_DIR      = os.path.join(OUTPUT_DIR, 'coverage')
REPORT_DIR        = os.path.join(OUTPUT_DIR, 'report')
SCRIPTS_DIR       = os.path.join(config['locations']['pkglibexecdir'], 'scripts/')

def toolArgs(name):
    if 'args' in config['tools'][name]:
        return config['tools'][name]['args']
    else:
        return ""

def tool(name):
    cmd = config['tools'][name]['executable']
    return cmd + " " + toolArgs(name)

BWA_EXEC             = tool("bwa")
FASTQC_EXEC          = tool("fastqc")
IMPORT_TAXONOMY_EXEC = tool("import_taxonomy")
KRAKEN2_EXEC         = tool("kraken2")
LOFREQ_EXEC          = tool("lofreq")
PRINSEQ_EXEC         = tool("prinseq")
PYTHON_EXEC          = tool("python")
RSCRIPT_EXEC         = tool("Rscript")
SAMTOOLS_EXEC        = tool("samtools")
VEP_EXEC             = tool("vep")

# Load sample sheet
with open(SAMPLE_SHEET_CSV, 'r') as fp:
  sample_sheet = list(csv.DictReader(fp))

SAMPLES = [row['name'] for row in sample_sheet]

targets = {
    'help': {
        'description': "Print all rules and their descriptions.",
        'files': []
    },
    'final_reports': {
        'description': "Produce a comprehensive report. This is the default target.",
        'files': (
            expand(os.path.join(REPORT_DIR, '{sample}.qc_report_per_sample.html'), sample=SAMPLES) +
            expand(os.path.join(REPORT_DIR, '{sample}.variantreport_p_sample.html'), sample=SAMPLES) +
            expand(os.path.join(REPORT_DIR, '{sample}.taxonomic_classification.html'), sample=SAMPLES) +
            expand(os.path.join(REPORT_DIR, '{sample}.Krona_report.html'), sample=SAMPLES)
        )
    },
    'lofreq': {
        'description': "Call variants and produce .vcf file and overview .csv file.",
        'files': (
            expand(os.path.join(VARIANTS_DIR, '{sample}_snv.csv'), sample=SAMPLES)
        )
    }
}
selected_targets = ['final_reports']
OUTPUT_FILES = list(chain.from_iterable([targets[name]['files'] for name in selected_targets]))


rule all:
    input: OUTPUT_FILES


# Record any existing output files, so that we can detect if they have
# changed.
expected_files = {}
onstart:
    if OUTPUT_FILES:
        for name in OUTPUT_FILES:
            if os.path.exists(name):
                expected_files[name] = os.path.getmtime(name)


# Print generated target files.
onsuccess:
    if OUTPUT_FILES:
        # check if any existing files have been modified
        generated = []
        for name in OUTPUT_FILES:
            if name not in expected_files or os.path.getmtime(name) != expected_files[name]:
                generated.append(name)
        if generated:
            print("The following files have been generated:")
            for name in generated:
                print("  - {}".format(name))


# TODO: get read length and specify cut off
rule prinseq:
    input:
        r1 = os.path.join(READS_DIR, "{sample}_R1.fastq"),
        r2 = os.path.join(READS_DIR, "{sample}_R2.fastq")
    output:
        r1 = os.path.join(TRIMMED_READS_DIR, "{sample}_1.fastq"),
        r2 = os.path.join(TRIMMED_READS_DIR, "{sample}_2.fastq")
    params:
        len_cutoff = int(150 * 0.8), # read length * pct_cutoff
        output = os.path.join(TRIMMED_READS_DIR, "{sample}")
    log: os.path.join(LOG_DIR, 'prinseq_{sample}.log')
    shell: "{PRINSEQ_EXEC} -fastq {input.r1} -fastq2 {input.r2} -ns_max_n 4 -min_qual_mean 30 -trim_qual_left 30 -trim_qual_right 30 -trim_qual_window 10 -out_good {params.output} -out_bad null -min_len {params.len_cutoff} >> {log} 2>&1"


rule bwa_index:
    input: REFERENCE_FASTA
    output: "{}.bwt".format(REFERENCE_FASTA)
    log: os.path.join(LOG_DIR, 'bwa_index.log')
    shell: "{BWA_EXEC} index {input} >> {log} 2>&1"


rule bwa_align:
    input:
        fastq = [os.path.join(TRIMMED_READS_DIR, "{sample}_1.fastq"), os.path.join(TRIMMED_READS_DIR, "{sample}_2.fastq")],
        ref = REFERENCE_FASTA,
        index = "{}.bwt".format(REFERENCE_FASTA)
    output: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_tmp.sam')
    params:
        threads = 4
    log: os.path.join(LOG_DIR, 'bwa_align_{sample}.log')
    shell: "{BWA_EXEC} mem -t {params.threads} {input.ref} {input.fastq} > {output} 2>> {log} 3>&2"


rule samtools_filter_aligned:
    input: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_tmp.sam')
    output: os.path.join(MAPPED_READS_DIR, '{sample}_aligned.bam')
    log: os.path.join(LOG_DIR, 'samtools_filter_aligned_{sample}.log')
    shell: "{SAMTOOLS_EXEC} view -bh -f 2 -F 2048 {input} > {output} 2>> {log} 3>&2"


# TODO: check command to get unaligned ones
rule samtools_filter_unaligned:
    input: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_tmp.sam')
    output: os.path.join(MAPPED_READS_DIR, '{sample}_unaligned.bam')
    log: os.path.join(LOG_DIR, 'samtools_filter_unaligned_{sample}.log')
    shell: "{SAMTOOLS_EXEC} view -bh -F 2 {input} > {output} 2>> {log} 3>&2"


rule samtools_sort:
    input: os.path.join(MAPPED_READS_DIR, '{sample}_aligned.bam')
    output: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bam')
    log: os.path.join(LOG_DIR, 'samtools_sort_{sample}.log')
    shell: "{SAMTOOLS_EXEC} sort -o {output} {input} >> {log} 2>&1"


rule samtools_index:
    input: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bam')
    output: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bai')
    log: os.path.join(LOG_DIR, 'samtools_index_{sample}.log')
    shell: "{SAMTOOLS_EXEC} index {input} {output} >> {log} 2>&1"


rule fastqc:
    input: os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bam')
    output: os.path.join(FASTQC_DIR, '{sample}_aligned_sorted_fastqc.zip')
    log: os.path.join(LOG_DIR, 'fastqc_{sample}.log')
    shell: "{FASTQC_EXEC} -o {FASTQC_DIR} -f bam {input} >> {log} 2>&1"


# TODO: check if --call-indels is needed?
rule lofreq:
    input:
        aligned_bam = os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bam'),
        aligned_bai = os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bai'),
        ref = REFERENCE_FASTA
    output: os.path.join(VARIANTS_DIR, '{sample}_snv.vcf')
    log: os.path.join(LOG_DIR, 'lofreq_{sample}.log')
    shell: "{LOFREQ_EXEC} call -f {input.ref} -o {output} --verbose {input.aligned_bam} >> {log} 2>&1"


rule vcf2csv:
    input: os.path.join(VARIANTS_DIR, '{sample}_snv.vcf')
    output: os.path.join(VARIANTS_DIR, '{sample}_snv.csv')
    params:
        script = os.path.join(SCRIPTS_DIR, 'vcfTocsv.py')
    log: os.path.join(LOG_DIR, 'vcf2csv_{sample}.log')
    shell: "{PYTHON_EXEC} {params.script} {input} >> {log} 2>&1"

rule vep:
    input: os.path.join(VARIANTS_DIR, '{sample}_snv.vcf')
    output: os.path.join(VARIANTS_DIR, '{sample}_vep_sarscov2.txt')
    params:
        species = "sars_cov_2"
    log: os.path.join(LOG_DIR, 'vep_{sample}.log')
    shell:
      """
      {VEP_EXEC} --verbose --offline --dir_cache {VEP_DB} --DB_VERSION 101 --appris --biotype --buffer_size 5000 --check_existing\
      --distance 5000 --mane --protein --species {params.species} --symbol --transcript_version --tsl\
      --input_file {input} --output_file {output} >> {log} 2>&1
      """

rule parse_vep:
    input: os.path.join(VARIANTS_DIR, '{sample}_vep_sarscov2.txt')
    output: os.path.join(VARIANTS_DIR, '{sample}_vep_sarscov2_parsed.txt')
    params:
        script = os.path.join(SCRIPTS_DIR, 'parse_vep.py')
    log: os.path.join(LOG_DIR, 'parse_vep_{sample}.log')
    shell: "{PYTHON_EXEC} {params.script} {input} {output} >> {log} 2>&1"


rule bam2fastq:
    input: os.path.join(MAPPED_READS_DIR, '{sample}_unaligned.bam')
    output: os.path.join(MAPPED_READS_DIR, '{sample}_unaligned.fastq')
    log: os.path.join(LOG_DIR, 'bam2fastq_{sample}.log')
    shell: "{SAMTOOLS_EXEC} fastq {input} > {output} 2>> {log} 3>&2"


rule kraken:
    input:
        unaligned_fastq = os.path.join(MAPPED_READS_DIR, '{sample}_unaligned.fastq'),
        database = KRAKEN_DB
    output: os.path.join(KRAKEN_DIR, '{sample}_classified_unaligned_reads.txt')
    log: os.path.join(LOG_DIR, 'kraken_{sample}.log')
    shell: "{KRAKEN2_EXEC} --report {output} --db {input.database} {input.unaligned_fastq} >> {log} 2>&1"


rule krona_report:
    input:
        kraken_output = os.path.join(KRAKEN_DIR, '{sample}_classified_unaligned_reads.txt'),
        database = KRONA_DB
    output: os.path.join(REPORT_DIR, '{sample}.Krona_report.html')
    log: os.path.join(LOG_DIR, 'krona_report_{sample}.log')
    shell: "{IMPORT_TAXONOMY_EXEC} -m 3 -t 5 {input.kraken_output} -tax {input.database} -o {output} >> {log} 2>&1"


rule samtools_bedcov:
    input:
        amplicons_bed = AMPLICONS_BED,
        aligned_bam = os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bam'),
        aligned_bai = os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bai')
    output: os.path.join(COVERAGE_DIR, '{sample}_amplicons.csv')
    log: os.path.join(LOG_DIR, 'samtools_bedcov_{sample}.log')
    shell: "{SAMTOOLS_EXEC} bedcov {input.amplicons_bed} {input.aligned_bam} > {output} 2>> {log} 3>&2"


rule samtools_coverage:
    input:
        aligned_bam = os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bam'),
        aligned_bai = os.path.join(MAPPED_READS_DIR, '{sample}_aligned_sorted.bai')
    output: os.path.join(COVERAGE_DIR, '{sample}_coverage.csv')
    log: os.path.join(LOG_DIR, 'samtools_coverage_{sample}.log')
    shell: "{SAMTOOLS_EXEC} coverage {input.aligned_bam} > {output} 2>> {log} 3>&2"


rule get_qc_table:
    input:
        coverage_csv = os.path.join(COVERAGE_DIR, '{sample}_coverage.csv'),
        amplicon_csv = os.path.join(COVERAGE_DIR, '{sample}_amplicons.csv')
    output: os.path.join(COVERAGE_DIR, '{sample}_merged_covs.csv')
    params:
        script = os.path.join(SCRIPTS_DIR, 'get_qc_table.py')
    log: os.path.join(LOG_DIR, 'get_qc_table_{sample}.log')
    shell: "{PYTHON_EXEC} {params.script} {input.coverage_csv} {input.amplicon_csv} {output} >> {log} 2>&1"


#TODO index.Rmd !
#TODO site_DiR - folder which contains the generated site as an extra folder/settings file?
#TODO check whether Site_dir should be REPORT dir
rule generate_site_files:
    input:
        expand(os.path.join(COVERAGE_DIR, '{sample}_merged_covs.csv'), sample = SAMPLES),
        expand(os.path.join(REPORT_DIR, '{sample}.Krona_report.html'), sample = SAMPLES),
        expand(os.path.join(KRAKEN_DIR, '{sample}_classified_unaligned_reads.txt'), sample = SAMPLES),
        expand(os.path.join(VARIANTS_DIR, '{sample}_vep_sarscov2_parsed.txt'), sample = SAMPLES),
        expand(os.path.join(VARIANTS_DIR, '{sample}_snv.csv'), sample = SAMPLES)
    output:
        os.path.join(REPORT_DIR, "_site.yml"),
        # os.path.join(REPORT_DIR, "index.Rmd"),
        os.path.join(REPORT_DIR, "config.yml"),
        expand(os.path.join(REPORT_DIR, "{sample}.taxonomic_classification.Rmd"), sample = SAMPLES),
        expand(os.path.join(REPORT_DIR, "{sample}.qc_report_per_sample.Rmd"), sample = SAMPLES),
        expand(os.path.join(REPORT_DIR, "{sample}.variantreport_p_sample.Rmd"), sample = SAMPLES)
    params:
        report_scripts_dir = os.path.join(SCRIPTS_DIR, "report_scripts"),
        script = os.path.join(SCRIPTS_DIR, "generateSiteFiles.R")
    log: os.path.join(LOG_DIR, "generate_site_files.log")
    shell: "{RSCRIPT_EXEC} {params.script} {params.report_scripts_dir} {SAMPLE_SHEET_CSV} {KRAKEN_DIR} {COVERAGE_DIR} {VARIANTS_DIR} {SIGMUT_DB} {REPORT_DIR} {RSCRIPT_EXEC} > {log} 2>&1"


rule render_kraken2_report:
    input: os.path.join(REPORT_DIR, "{sample}.taxonomic_classification.Rmd")
    output: os.path.join(REPORT_DIR, "{sample}.taxonomic_classification.html")
    log: os.path.join(LOG_DIR, "reports", "{sample}_taxonomic_classification.log")
    shell: "{RSCRIPT_EXEC} -e \"library(rmarkdown); rmarkdown::render_site(\'{input}\')\" > {log} 2>&1"


rule render_variant_report:
    input: os.path.join(REPORT_DIR, "{sample}.variantreport_p_sample.Rmd")
    output: os.path.join(REPORT_DIR, "{sample}.variantreport_p_sample.html")
    log: os.path.join(LOG_DIR, "reports", "{sample}_variant_report.log")
    shell: "{RSCRIPT_EXEC} -e \"library(rmarkdown); rmarkdown::render_site(\'{input}\')\" > {log} 2>&1"
        

rule render_qc_report:
    input: os.path.join(REPORT_DIR, "{sample}.qc_report_per_sample.Rmd")
    output: os.path.join(REPORT_DIR, "{sample}.qc_report_per_sample.html")
    log: os.path.join(LOG_DIR, "reports", "{sample}_qc_report.log")
    shell: "{RSCRIPT_EXEC} -e \"library(rmarkdown); rmarkdown::render_site(\'{input}\')\" > {log} 2>&1"


# renders the timecourse rmd once all other are done rendering (!!)
# not yet tested
rule render_timecourse:
    input:
        os.path.join(REPORT_DIR, "timecourse.Rmd"),
        os.path.join(REPORT_DIR, "{sample}.qc_report_per_sample.html"),
        os.path.join(REPORT_DIR, "{sample}.variantreport_p_sample.html"),
        os.path.join(REPORT_DIR, "{sample}.Krona_report.html"),
        os.path.join(REPORT_DIR, "{sample}.taxonomic_classification.html")
    output: os.path.join(REPORT_DIR, "timecourse.html")
    log: os.path.join(LOG_DIR, "reports", "timecourse.log")
    shell: "{RSCRIPT_EXEC} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[0]}\')\" > {log} 2>&1"#


# not yet tested
rule render_site:
    input:
        os.path.join(REPORT_DIR, "_site.yml"),
        os.path.join(REPORT_DIR, "index.Rmd"),
        os.path.join(REPORT_DIR, "config.yml"),
        expand(os.path.join(REPORT_DIR, "{sample}.taxonomic_classification.html"), sample = SAMPLES),
        expand(os.path.join(REPORT_DIR, "{sample}.Krona_report.html"), sample = SAMPLES),
        expand(os.path.join(REPORT_DIR, "{sample}.qc_report_per_sample.html"), sample = SAMPLES),
        expand(os.path.join(REPORT_DIR, "{sample}.variantreport_p_sample.html"), sample = SAMPLES),
    output: os.path.join(REPORT_DIR, "index.html")
    # params:
    #     report_scripts_dir = os.path.join(SCRIPTS_DIR, "report_scripts")
    log: os.path.join(LOG_DIR, "render_site.log")
    shell: "{RSCRIPT_EXEC} -e \"library(rmarkdown); rmarkdown::render_site(\'{input[1]}\')\" > {log} 2>&1"
