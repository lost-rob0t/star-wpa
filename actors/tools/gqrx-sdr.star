(actor wpa-tool-gqrx-sdr
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-gqrx-sdr"
   :accepts ()
   :produces ()
   :handler wpa-tool-gqrx-sdr-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-gqrx-sdr") (package "gqrx-sdr") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
