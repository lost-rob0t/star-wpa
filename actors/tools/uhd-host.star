(actor wpa-tool-uhd-host
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-uhd-host"
   :accepts ()
   :produces ()
   :handler wpa-tool-uhd-host-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-uhd-host") (package "uhd-host") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
