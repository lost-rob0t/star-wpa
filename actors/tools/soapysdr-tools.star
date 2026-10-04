(actor wpa-tool-soapysdr-tools
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-soapysdr-tools"
   :accepts ()
   :produces ()
   :handler wpa-tool-soapysdr-tools-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-soapysdr-tools") (package "soapysdr-tools") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
