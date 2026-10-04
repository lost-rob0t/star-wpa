(actor wpa-tool-rfcat
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-rfcat"
   :accepts ()
   :produces ()
   :handler wpa-tool-rfcat-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-rfcat") (package "rfcat") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
