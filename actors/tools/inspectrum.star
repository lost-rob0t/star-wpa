(actor wpa-tool-inspectrum
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-inspectrum"
   :accepts ()
   :produces ()
   :handler wpa-tool-inspectrum-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-inspectrum") (package "inspectrum") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
