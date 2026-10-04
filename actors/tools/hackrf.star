(actor wpa-tool-hackrf
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-hackrf"
   :accepts ()
   :produces ()
   :handler wpa-tool-hackrf-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-hackrf") (package "hackrf") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
