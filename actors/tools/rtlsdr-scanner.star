(actor wpa-tool-rtlsdr-scanner
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-rtlsdr-scanner"
   :accepts ()
   :produces ()
   :handler wpa-tool-rtlsdr-scanner-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-rtlsdr-scanner") (package "rtlsdr-scanner") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
