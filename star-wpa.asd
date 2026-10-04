(asdf:defsystem "star-wpa"
  :description "StarLang wireless actors consuming canonical StarIntel 0.10.1"
  :version "0.1.0"
  :license "AGPL-3.0-only"
  :depends-on ("starlang-compiler" "starlang-runtime" "star-process-port")
  :serial t
  :components ((:file "lisp/package") (:file "lisp/actors")))
