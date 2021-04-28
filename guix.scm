;;; PiGx SARS-CoV2 wastewater sequencing pipeline
;;; Copyright © 2021 Ricardo Wurmus <rekado@elephly.net>
;;;
;;; This file is part of PiGx SARS-CoV2 wastewater sequencing pipeline
;;;
;;; This is free software; see LICENSE file for details.

(use-modules
 (guix build-system gnu)
 (guix packages)
 (guix licenses)
 (gnu packages)
 (ice-9 match))

(include "manifest.scm")

(define (p name)
  `(,name ,(specification->package name)))

(define %version
  (symbol->string (with-input-from-file "VERSION" read)))

(define-public pigx-sars-cov2-ww-development
  (package
    (name "pigx-sars-cov2-ww")
    (version %version)
    (source
     (string-append (getcwd) "/pigx_sars-cov2-ww-" version ".tar.gz"))
    (build-system gnu-build-system)
    (inputs
     (map p %packages))
    (native-inputs
     (map p %native-packages))
    (home-page "http://bioinformatics.mdc-berlin.de/pigx/")
    (synopsis "SARS-CoV2 wastewater sequencing pipeline")
    (description "")
    (license gpl3+)))

pigx-sars-cov2-ww-development
