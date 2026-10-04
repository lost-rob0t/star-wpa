(actor wpa-tool-gr-osmosdr
  (:runtime native
   :service-uri "star://wpa:localhost:wpa-tool-gr-osmosdr"
   :accepts ()
   :produces ()
   :handler wpa-tool-gr-osmosdr-handler
   :restart temporary
   :mailbox (bounded 32)
   :metadata ((domain "wireless") (schemaVersion "0.10.1")
              (adapter "tool-gr-osmosdr") (package "gr-osmosdr") (family "sdr")
              (commandBoundary "operator-local-json-file"))))
