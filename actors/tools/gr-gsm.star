(actor wpa-tool-gr-gsm
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-gr-gsm"
   :accepts ()
   :produces ()
   :handler wpa-tool-gr-gsm-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-gr-gsm") (package "gr-gsm") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
